from fastapi import FastAPI

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


app = FastAPI(
    title="InsiteFuel V3",
    version="0.1.0",
    description="Fuel management backend rebuilt with Python/FastAPI.",
)


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


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "insitefuel-v3"}
