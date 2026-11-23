from fastapi import FastAPI

from app.api.routes.generation import router as generation_router
from app.api.routes.health import router as health_router


app = FastAPI(
    title="Model Gateway",
    description="Учебный шлюз для работы с языковыми моделями",
)


app.include_router(health_router)
app.include_router(generation_router)