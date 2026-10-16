"""
IoT integration routes.

* ``POST /api/iot/shift-data`` is called by the vendor's system, authenticated
  with the shared ``X-API-Key`` (not a user session).
* Everything else is for our own administrators / managers.
"""
import hmac

from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Response, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.config import settings
from backend.dependencies import db_session, require_roles
from backend.models.equipment import Equipment
from backend.models.iot import IotPayload, IotPayloadStatus
from backend.models.user import User, UserRole
from backend.models.vessel import Vessel
from backend.schemas.iot import (
    AutoCloseResponse,
    EquipmentIotMapping,
    IotIngestResponse,
    IotItemResult,
    IotPayloadDetail,
    IotPayloadSummary,
    VesselIotMapping,
)
from backend.services.audit_service import AuditService
from backend.services.iot_service import AWAITING_MAPPING, DUPLICATE, PROCESSED, REJECTED, IotService

router = APIRouter(prefix="/api/iot", tags=["IoT"])


def require_iot_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if not settings.iot_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="IoT ingestion is not configured on this server.",
        )
    if not x_api_key or not hmac.compare_digest(
        x_api_key.encode("utf-8"), settings.iot_api_key.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key.",
            headers={"WWW-Authenticate": "ApiKey"},
        )


def _result(index: int, outcome) -> IotItemResult:
    return IotItemResult(
        index=index,
        status=outcome.status,
        payload_id=outcome.payload_id,
        shift_id=outcome.shift_id,
        errors=outcome.errors,
        warnings=outcome.warnings,
        result=outcome.result,
    )


# ----------------------------------------------------------------------
# vendor endpoint
# ----------------------------------------------------------------------
@router.post(
    "/shift-data",
    response_model=IotIngestResponse,
    dependencies=[Depends(require_iot_api_key)],
)
def receive_shift_data(
    response: Response,
    body: dict | list = Body(...),
    db: Session = Depends(db_session),
):
    """
    Accepts one payload object or an array of them (as in the vendor's sample
    file).  Items are processed oldest window first, each in its own
    transaction.  Status codes: 200 when everything was processed or already
    known, 422 when at least one item was rejected (details in ``results``),
    500 when an item hit an unexpected server error.  Rejected payloads are
    kept and can be re-processed once the cause is fixed.
    """
    items = body if isinstance(body, list) else [body]
    if not items:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Payload is empty.")

    order = sorted(
        range(len(items)),
        key=lambda i: str(items[i].get("startTime", "")) if isinstance(items[i], dict) else "",
    )
    results: list[IotItemResult] = []
    internal_error = False
    for index in order:
        outcome = IotService.ingest(db, items[index])
        internal_error = internal_error or outcome.internal_error
        results.append(_result(index, outcome))
    results.sort(key=lambda r: r.index)

    counts = {s: sum(1 for r in results if r.status == s) for s in (PROCESSED, DUPLICATE, REJECTED, AWAITING_MAPPING)}
    if internal_error:
        response.status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    elif counts[REJECTED]:
        response.status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    return IotIngestResponse(
        received=len(items),
        processed=counts[PROCESSED],
        duplicates=counts[DUPLICATE],
        rejected=counts[REJECTED],
        awaiting_mapping=counts[AWAITING_MAPPING],
        results=results,
    )


# ----------------------------------------------------------------------
# inbox (our side)
# ----------------------------------------------------------------------
@router.get("/payloads", response_model=list[IotPayloadSummary])
def list_payloads(
    status_filter: str | None = Query(default=None, alias="status"),
    vessel_id: int | None = None,
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(db_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    query = select(IotPayload).order_by(IotPayload.id.desc()).limit(limit).offset(offset)
    if status_filter:
        query = query.where(IotPayload.status == status_filter.upper())
    if vessel_id is not None:
        query = query.where(IotPayload.vessel_id == vessel_id)
    return list(db.scalars(query).all())


@router.get("/payloads/{payload_id}", response_model=IotPayloadDetail)
def get_payload(
    payload_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    row = db.get(IotPayload, payload_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payload not found.")
    return row


@router.post("/payloads/process-ready", response_model=list[IotItemResult])
def process_ready_payloads(
    db: Session = Depends(db_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Automatically apply any validated, mapped payloads waiting in READY."""
    return [_result(index, outcome) for index, outcome in enumerate(IotService.process_ready_payloads(db))]


@router.post("/payloads/{payload_id}/reprocess", response_model=IotItemResult)
def reprocess_payload(
    payload_id: int,
    db: Session = Depends(db_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Re-run a REJECTED payload after fixing its cause (e.g. a missing mapping)."""
    row = db.get(IotPayload, payload_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Payload not found.")
    if row.status not in (IotPayloadStatus.REJECTED, IotPayloadStatus.AWAITING_MAPPING, IotPayloadStatus.READY):
        raise HTTPException(status.HTTP_409_CONFLICT, "Only pending or rejected payloads can be re-processed.")
    outcome = IotService.ingest(db, row.raw_payload, existing=row)
    return _result(0, outcome)


@router.get("/mapping-options")
def get_mapping_options(
    db: Session = Depends(db_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Return real active vessels and their active equipment for inbox mapping."""
    vessel_rows = db.scalars(select(Vessel).where(Vessel.is_active.is_(True)).order_by(Vessel.name)).all()
    equipment_rows = db.scalars(select(Equipment).where(Equipment.is_active.is_(True)).order_by(Equipment.name)).all()
    return {
        "vessels": [{"id": v.id, "name": v.name, "iot_vessel_id": v.iot_vessel_id} for v in vessel_rows],
        "equipment": [{"id": e.id, "vessel_id": e.vessel_id, "name": e.name,
                       "iot_engine_name": e.iot_engine_name} for e in equipment_rows],
    }


@router.post("/auto-close/run", response_model=AutoCloseResponse)
def run_auto_close_now(
    db: Session = Depends(db_session),
    _: User = Depends(require_roles(UserRole.ADMIN)),
):
    """Run the auto-close sweep immediately (it also runs on a timer)."""
    return IotService.close_due_shifts(db)


# ----------------------------------------------------------------------
# mapping setup (administrators)
# ----------------------------------------------------------------------
@router.put("/vessels/{vessel_id}/mapping")
def set_vessel_mapping(
    vessel_id: int,
    data: VesselIotMapping,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    vessel = db.get(Vessel, vessel_id)
    if vessel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Vessel not found.")
    new_id = data.iot_vessel_id.strip() if data.iot_vessel_id else None
    if new_id:
        clash = db.scalar(
            select(Vessel).where(Vessel.iot_vessel_id == new_id, Vessel.id != vessel_id)
        )
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"IoT vesselId '{new_id}' is already mapped to vessel '{clash.name}'.",
            )
    old = vessel.iot_vessel_id
    vessel.iot_vessel_id = new_id
    AuditService.log(
        db=db,
        user_id=current_user.id,
        action="SET_VESSEL_IOT_MAPPING",
        entity="vessels",
        entity_id=vessel.id,
        old_values={"iot_vessel_id": old},
        new_values={"iot_vessel_id": new_id},
    )
    db.commit()
    IotService.refresh_mapping_status(db)
    return {"vessel_id": vessel.id, "iot_vessel_id": vessel.iot_vessel_id}


@router.put("/equipment/{equipment_id}/mapping")
def set_equipment_mapping(
    equipment_id: int,
    data: EquipmentIotMapping,
    db: Session = Depends(db_session),
    current_user: User = Depends(require_roles(UserRole.ADMIN)),
):
    equipment = db.get(Equipment, equipment_id)
    if equipment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Equipment not found.")
    new_name = data.iot_engine_name.strip() if data.iot_engine_name else None
    if new_name:
        clash = db.scalar(
            select(Equipment).where(
                Equipment.vessel_id == equipment.vessel_id,
                Equipment.id != equipment_id,
                func.lower(Equipment.iot_engine_name) == new_name.lower(),
            )
        )
        if clash is not None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"IoT engine name '{new_name}' is already mapped to '{clash.name}' on this vessel.",
            )
    old = equipment.iot_engine_name
    equipment.iot_engine_name = new_name
    AuditService.log(
        db=db,
        user_id=current_user.id,
        action="SET_EQUIPMENT_IOT_MAPPING",
        entity="equipment",
        entity_id=equipment.id,
        old_values={"iot_engine_name": old},
        new_values={"iot_engine_name": new_name},
    )
    db.commit()
    IotService.refresh_mapping_status(db)
    return {"equipment_id": equipment.id, "iot_engine_name": equipment.iot_engine_name}
