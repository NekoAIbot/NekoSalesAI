from app.web.routes import _build_context
from unittest.mock import MagicMock

req = MagicMock()
req.query_string = b""
req.url.path = "/build"
req.url = MagicMock()
req.url.path = "/build"
req.url_for = MagicMock()

class FakeQuery:
    def filter(self, *a, **kw):
        return self
    def first(self):
        return None
    def all(self):
        return []
    def order_by(self, *a, **kw):
        return self
    def offset(self, *a, **kw):
        return self
    def limit(self, *a, **kw):
        return self
    def count(self):
        return 0

class FakeSession:
    def query(self, *a, **kw):
        return FakeQuery()
    def commit(self):
        pass
    def rollback(self):
        pass
    def close(self):
        pass
    def add(self, *a, **kw):
        pass
    def delete(self, *a, **kw):
        pass
    def refresh(self, *a, **kw):
        pass
    def execute(self, *a, **kw):
        return FakeQuery()
    def scalars(self, *a, **kw):
        return FakeQuery()

db = FakeSession()
try:
    ctx = _build_context(req, db, {"page": "build"})
    print(f"ctx OK: builder keys = {list(ctx['builder'].keys())}")
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()
