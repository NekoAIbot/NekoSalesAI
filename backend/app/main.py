from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.config.logging import configure_logging, get_logger
from app.config.settings import settings
from app.web.routes import router as web_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info(
        "%s v%s starting (env=%s, db=%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
        "sqlite" if settings.is_sqlite else "postgres",
    )

    if settings.SECRET_KEY.startswith("dev-only"):
        logger.warning(
            "SECRET_KEY is the insecure development default. "
            "Set SECRET_KEY in .env before deploying."
        )

    yield

    logger.info("%s shutting down", settings.APP_NAME)


app = FastAPI(
    title="NekoSalesAI API",
    version=settings.APP_VERSION,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Return a generic 500 rather than leaking SQL and schema to clients."""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)

    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


app.include_router(api_router)
app.include_router(web_router)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "web" / "static")),
    name="static",
)
