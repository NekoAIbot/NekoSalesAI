from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.api import api_router
from app.config import build
from app.config.logging import configure_logging, get_logger
from app.config.settings import settings
from app.web.routes import router as web_router

# A process-local guard prevents two lifespan entries in the same worker from
# starting duplicate long-poll loops. Render currently runs one Uvicorn worker.
_poller_task = None
_poller_stop = None
_zuri_poller_task = None
_zuri_poller_stop = None

logger = get_logger(__name__)


async def _run_poller(stop_event, bot_token: str | None = None, label: str = "telegram"):
    """Run a poller loop off the event loop until application shutdown.

    ``bot_token`` selects which shared bot this loop polls: the buyer bot
    (default) or the owner-facing Zuri bot. Each bot gets its own loop; both
    route by the same account-link logic.
    """
    import asyncio

    from app.messaging.poller import PollerError, TelegramPoller

    from app.messaging.clients import TelegramClient

    poller = TelegramPoller(bot_token=bot_token) if bot_token else TelegramPoller()
    logger.info("Starting embedded Telegram poller (%s)", label)
    # A webhook set by anything else (a previous webhook-mode deploy, a setup
    # script) makes Telegram refuse getUpdates with a 409. Clear it and retry
    # with backoff instead of giving up: the poller is the buyer's front door.
    #
    # The retry never exhausts. The earlier 5-attempt cap made one bad boot
    # window (overlapping deploys both polling, a slow database) kill a bot
    # for the rest of the day while the app looked perfectly healthy.
    attempt = 0
    while True:
        run_task = asyncio.create_task(
            asyncio.to_thread(poller.run), name=f"{label}-poller-loop"
        )
        stop_or_fail = asyncio.wait(
            [run_task, stop_event.wait()], return_when=asyncio.FIRST_COMPLETED
        )
        await stop_or_fail
        if stop_event.is_set():
            poller.stop()
            try:
                await asyncio.wait_for(run_task, timeout=40)
            except asyncio.TimeoutError:
                logger.warning("Telegram poller did not stop within the long-poll timeout")
            except Exception:
                logger.exception("Telegram poller exited with an error during shutdown")
            logger.info("Embedded Telegram poller stopped")
            return
        # The poller exited on its own: an error, since it loops until stopped.
        try:
            await run_task
        except PollerError as exc:
            logger.error(
                "Telegram poller failed (attempt %s): %s", attempt, exc
            )
        except Exception:
            logger.exception("Telegram poller exited with an error (attempt %s)", attempt)
        attempt += 1
        TelegramClient(bot_token=bot_token).delete_webhook(drop_pending_updates=False)
        backoff = min(60, 15 * attempt)
        logger.info("Telegram webhook cleared; retrying poller in %ss", backoff)
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=backoff)
            break  # shutting down
        except asyncio.TimeoutError:
            pass
    logger.info("Embedded Telegram poller stopped")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _poller_task, _poller_stop

    configure_logging()
    logger.info(
        "%s v%s starting (env=%s, db=%s)",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.ENVIRONMENT,
        "sqlite" if settings.is_sqlite else "postgres",
    )

    # The version above is a constant someone types; this is what is actually
    # loaded. The two diverge silently, and it was the divergence that mattered:
    # a live process serving withdrawn prices reported the same version string as
    # the corrected source. See ``app.config.build``.
    logger.info("Running %s", build.describe())

    if settings.SECRET_KEY.startswith("dev-only"):
        logger.warning(
            "SECRET_KEY is the insecure development default. "
            "Set SECRET_KEY in .env before deploying."
        )

    telegram_mode = settings.TELEGRAM_MODE.strip().lower()
    if telegram_mode not in {"polling", "webhook"}:
        raise RuntimeError("TELEGRAM_MODE must be 'polling' or 'webhook'.")

    # Zuri's own shared bot, for owners. Her loop is independent of the buyer
    # bot's: one dying must not take the other with it.
    global _zuri_poller_task, _zuri_poller_stop
    zuri_token = settings.ZURI_BOT_TOKEN or settings.MIRA_BOT_TOKEN
    if telegram_mode == "polling" and zuri_token and _zuri_poller_task is None:
        import asyncio

        from app.messaging.clients import TelegramClient as _ZuriClient
        webhook_reset = _ZuriClient(bot_token=zuri_token).delete_webhook(drop_pending_updates=False)
        logger.info("Zuri bot polling: deleteWebhook result=%s", webhook_reset.get("result"))
        _zuri_poller_stop = asyncio.Event()
        _zuri_poller_task = asyncio.create_task(
            _run_poller(_zuri_poller_stop, bot_token=zuri_token, label="zuri"),
            name="zuri-poller",
        )

    if telegram_mode == "polling" and settings.TELEGRAM_BOT_TOKEN and _poller_task is None:
        import asyncio

        from app.messaging.clients import TelegramClient
        webhook_reset = TelegramClient().delete_webhook(drop_pending_updates=False)
        logger.info("Telegram polling mode selected; deleteWebhook result=%s", webhook_reset.get("result"))
        _poller_stop = asyncio.Event()
        _poller_task = asyncio.create_task(_run_poller(_poller_stop), name="telegram-poller")
    elif telegram_mode == "webhook":
        logger.info("Telegram polling disabled: TELEGRAM_MODE=webhook")
    elif not settings.TELEGRAM_BOT_TOKEN:
        logger.warning("Telegram poller is disabled: TELEGRAM_BOT_TOKEN is not configured")

    yield

    if _poller_task is not None:
        _poller_stop.set()
        try:
            await _poller_task
        finally:
            _poller_task = None
            _poller_stop = None

    if _zuri_poller_task is not None:
        _zuri_poller_stop.set()
        try:
            await _zuri_poller_task
        finally:
            _zuri_poller_task = None
            _zuri_poller_stop = None

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


# The new vanilla-JS app is served for public and workspace page paths. Keep the
# original templates and frontend/src-legacy available, while API routes remain
# mounted above this catch-all page set.
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"
NEW_APP_INDEX = FRONTEND_DIR / "app" / "index.html"

@app.api_route("/", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/products", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/pricing", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/trust", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/signup", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/login", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/build", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/configure", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/dashboard", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/workspace", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/settings", methods=["GET", "HEAD"], include_in_schema=False)
@app.api_route("/checkout/return", methods=["GET", "HEAD"], include_in_schema=False)
async def serve_new_frontend():
    if NEW_APP_INDEX.is_file():
        return FileResponse(NEW_APP_INDEX)
    return JSONResponse(status_code=404, content={"detail": "New frontend index.html not found"})

app.include_router(api_router)
app.include_router(web_router)

app.mount(
    "/static",
    StaticFiles(directory=str(Path(__file__).parent / "web" / "static")),
    name="static",
)

if FRONTEND_DIR.is_dir():
    # Mobile browsers pin JS modules aggressively; a stale main.js against a
    # new backend renders literal "undefined" pages and looks like a outage.
    # Code is small and static files are cheap: revalidate every time.
    class _NoCacheStatic(StaticFiles):
        def file_response(self, *args, **kwargs):
            response = super().file_response(*args, **kwargs)
            response.headers["Cache-Control"] = "no-cache, must-revalidate"
            return response

    app.mount(
        "/frontend",
        _NoCacheStatic(directory=str(FRONTEND_DIR)),
        name="frontend",
    )

    @app.api_route("/v2", methods=["GET", "HEAD"], include_in_schema=False)
    @app.api_route("/v2/{full_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def serve_greenfield_frontend(full_path: str = ""):
        index_file = FRONTEND_DIR / "app" / "index.html"
        if index_file.is_file():
            return FileResponse(index_file)
        return JSONResponse(status_code=404, content={"detail": "Frontend index.html not found"})
