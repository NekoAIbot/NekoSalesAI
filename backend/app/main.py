from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.ai.scheduler.autonomous_scheduler import AutonomousScheduler
from app.api.v1.api import api_router


scheduler = AutonomousScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):

    scheduler.start()

    yield

    scheduler.stop()


app = FastAPI(
    title="NekoSalesAI API",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(api_router)


@app.get("/")
def root():
    return {
        "message": "Welcome to NekoSalesAI API",
        "status": "running",
    }
