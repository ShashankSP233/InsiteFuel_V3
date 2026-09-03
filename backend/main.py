from fastapi import FastAPI

# ROUTES IMPORTS
from backend.routes.auth import router as auth_router
from backend.routes.users import router as users_router
from backend.routes.projects import router as projects_router
from backend.routes.vessels import router as vessels_router
from backend.routes.equipment import router as equipment_router
from backend.routes.fuel import router as fuel_router


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



@app.get("/api/health")
def health():
    return {"status": "ok", "service": "insitefuel-v3"}
