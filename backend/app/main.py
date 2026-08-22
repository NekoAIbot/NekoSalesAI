from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
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

# Path the embeddable widget's API lives under. Kept as a constant because the
# middleware below grants it a policy nothing else on the server gets.
WIDGET_PATH = "/api/v1/widget"


@app.middleware("http")
async def widget_cors(request: Request, call_next):
    """Cross-origin access for the widget, and for nothing else.

    The widget runs on domains we cannot know in advance — every customer's own
    website — so its routes have to answer any origin. A second CORSMiddleware
    cannot express that: Starlette's applies to every request regardless of path,
    so adding a permissive one would hand wildcard CORS to the authenticated API
    as well. Hence a path check.

    Safe for these routes specifically, because of what the widget token is:

      * It is public by construction. It ships in the customer's page source, so
        treating its origin as a security boundary would be pretending a
        published string is a secret.
      * No credentials are allowed through. Access-Control-Allow-Credentials is
        never set here, so no cookie or Authorization header rides along — the
        wildcard-plus-credentials combination browsers forbid outright.
      * Nothing under this prefix can change a workspace. It starts
        conversations and reads branding.

    The authenticated API keeps the narrow allow-list configured above.
    """
    if not request.url.path.startswith(WIDGET_PATH):
        return await call_next(request)

    # Preflight is answered here rather than routed: OPTIONS matches no widget
    # route, so letting it through would return 405 and the browser would refuse
    # to send the real request.
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        response = await call_next(request)

    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Max-Age"] = "600"

    # Starlette's CORSMiddleware sets Allow-Credentials unconditionally whenever
    # an Origin is present, even for an origin it does not allow. Left in place
    # it would pair with the wildcard above, and "Allow-Origin: * with
    # Allow-Credentials: true" is the one combination every browser rejects
    # outright — which would break the widget on every customer site while
    # looking, from the server side, like a correctly configured response.
    if "access-control-allow-credentials" in response.headers:
        del response.headers["access-control-allow-credentials"]

    # Caches must not serve one origin's response to another.
    response.headers["Vary"] = "Origin"

    return response


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
