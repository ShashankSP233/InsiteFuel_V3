# InsiteFuel V3

Python/FastAPI rebuild of the InsiteFuel backend.

## Initial stack

- Python
- FastAPI
- SQLAlchemy
- Alembic
- PostgreSQL

## Development startup

Create and activate a virtual environment, install `requirements.txt`, copy
`.env.example` to `.env`, configure `DATABASE_URL`, then run:

    uvicorn backend.main:app --reload

Health check:

    GET /api/health

The existing Node.js application remains the reference/fallback implementation.
Do not modify it as part of the V3 rebuild.
