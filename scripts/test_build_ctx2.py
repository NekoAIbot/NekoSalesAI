from app.web.routes import _build_context
from app.database.database import SessionLocal
from unittest.mock import MagicMock

db = SessionLocal()
req = MagicMock()
req.query_string = b""
req.url.path = "/build"
req.url_for = MagicMock(return_value="http://localhost:8000/static/css/app-v4.css")
req.url = MagicMock()
req.url.path = "/build"
req.scope = {"path": "/build"}
req.headers = {}

try:
    ctx = _build_context(req, db, {"page": "build"})
    print(f"ctx OK, keys: {list(ctx.keys())}")
    
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader("/root/NekoSalesAI/backend/app/web/templates"))
    env.filters["number_format"] = lambda v: f"{int(v):,}" if v else "0"
    tmpl = env.get_template("build.html")
    result = tmpl.render(**ctx)
    print(f"Template rendered: {len(result)} bytes")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
