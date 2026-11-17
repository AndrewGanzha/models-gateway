from fastapi import FastAPI

from app.api.routes.health import router as health_router


app = FastAPI(
    title="Model Gateway",
    description="Шлюз для работы с языковыми моделями",
)

app.include_router(health_router)