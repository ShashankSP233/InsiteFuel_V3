import asyncio
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# ROUTES IMPORTS
from backend.routes.auth import router as auth_router
from backend.routes.users import router as users_router
from backend.routes.projects import router as projects_router
from backend.routes.vessels import router as vessels_router
from backend.routes.equipment import router as equipment_router
from backend.routes.fuel import router as fuel_router
from backend.routes import engine
from backend.routes.transfer import router as transfer_router
from backend.routes.audit import router as audit_router
from backend.routes.attachments import router as attachments_router
from backend.routes.soundings import router as soundings_router
from backend.routes.production import router as production_router
from backend.routes.dashboard import router as dashboard_router
from backend.routes import export
from backend.routes.backup import router as backup_router

from backend.database import SessionLocal
from backend.services.bootstrap_service  import BootstrapService
from backend.config import settings
from backend.routes.shift_attachments import router as shift_attachments_router
from backend.routes.site import router as site_router
from backend.routes.iot import router as iot_router
from backend.services.iot_service import IotService

logger = logging.getLogger(__name__)

app = FastAPI(
    title="InsiteFuel V3",
    version="0.1.0",
    description="Fuel management backend rebuilt with Python/FastAPI.",
)

# The browser UI is deliberately served from the same origin as the API.  This
# keeps the session token handling simple and avoids a separate CORS setup.
frontend_directory = Path(__file__).resolve().parent.parent / "frontend"


@app.on_event("startup")
def bootstrap_database():
    db = SessionLocal()

    try:
        if BootstrapService.initialize(db):
            print("InsiteFuel V3 initial bootstrap completed.")
            print(
                f"Initial administrator: "
                f"{settings.bootstrap_admin_username}"
            )
        else:
            print("InsiteFuel V3 database already initialized.")

    finally:
        db.close()

def _run_iot_auto_close() -> None:
    db = SessionLocal()
    try:
        outcome = IotService.close_due_shifts(db)
        if outcome["closed"]:
            logger.info("IoT auto-close closed shifts: %s", outcome["closed"])
    finally:
        db.close()


async def _iot_auto_close_loop() -> None:
    """Closes IoT shifts 11 hours (configurable) after their data arrived."""
    interval = max(30, settings.iot_auto_close_check_seconds)
    while True:
        try:
            await asyncio.to_thread(_run_iot_auto_close)
        except Exception:  # noqa: BLE001 - the sweeper must keep running
            logger.exception("IoT auto-close sweep failed")
        await asyncio.sleep(interval)


@app.on_event("startup")
async def start_iot_auto_close():
    app.state.iot_auto_close_task = asyncio.create_task(_iot_auto_close_loop())


@app.on_event("shutdown")
async def stop_iot_auto_close():
    task = getattr(app.state, "iot_auto_close_task", None)
    if task is not None:
        task.cancel()


app.include_router(auth_router)

app.include_router(users_router)

app.include_router(projects_router)

app.include_router(site_router)

app.include_router(vessels_router)

app.include_router(equipment_router)

app.include_router(fuel_router)

app.include_router(engine.router)

app.include_router(transfer_router)

app.include_router(audit_router)

app.include_router(attachments_router)

app.include_router(soundings_router)

app.include_router(production_router)

app.include_router(dashboard_router)
app.include_router(export.router)


app.include_router(backup_router)

app.include_router(shift_attachments_router)

app.include_router(iot_router)

app.mount("/ui", StaticFiles(directory=frontend_directory, html=True), name="ui")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "insitefuel-v3"}
