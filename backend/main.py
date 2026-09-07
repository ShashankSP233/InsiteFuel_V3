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

app.include_router(auth_router)

app.include_router(users_router)

app.include_router(projects_router)

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

app.mount("/ui", StaticFiles(directory=frontend_directory, html=True), name="ui")

@app.get("/api/health")
def health():
    return {"status": "ok", "service": "insitefuel-v3"}
