"""Tests for Nera 2.0 Greenfield Frontend Architecture & Endpoints."""

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

from app.main import app

client = TestClient(app)

FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def test_greenfield_directory_structure():
    """Verify Greenfield directory and required core files exist."""
    assert FRONTEND_DIR.is_dir()
    assert (FRONTEND_DIR / "index.html").is_file()
    assert (FRONTEND_DIR / "src" / "app.js").is_file()
    assert (FRONTEND_DIR / "src" / "styles" / "tokens.css").is_file()
    assert (FRONTEND_DIR / "src" / "styles" / "components.css").is_file()
    assert (FRONTEND_DIR / "src" / "styles" / "animations.css").is_file()
    assert (FRONTEND_DIR / "src" / "brand" / "nera-logo.svg").is_file()
    assert (FRONTEND_DIR / "src" / "brand" / "nera-emblem.svg").is_file()


def test_greenfield_views_exist():
    """Verify all 10 customer-facing views exist in frontend/src/views/."""
    views_dir = FRONTEND_DIR / "src" / "views"
    expected_views = [
        "HomeView.js",
        "ProductsView.js",
        "WorkforceView.js",
        "DemoView.js",
        "PricingView.js",
        "BuildView.js",
        "TrustView.js",
        "AuthView.js",
        "DashboardView.js",
        "CheckoutReturnView.js",
    ]
    for view_file in expected_views:
        path = views_dir / view_file
        assert path.is_file(), f"Missing view {view_file}"
        content = path.read_text(encoding="utf-8")
        assert "async render(" in content or "render(" in content


def test_greenfield_endpoints_return_200():
    """Verify all Greenfield /v2 routes return HTTP 200 and serve HTML."""
    subroutes = [
        "",
        "/",
        "/products",
        "/workforce",
        "/demo",
        "/pricing",
        "/build",
        "/trust",
        "/login",
        "/signup",
        "/dashboard",
        "/checkout/return",
    ]
    for route in subroutes:
        resp = client.get(f"/v2{route}")
        assert resp.status_code == 200, f"/v2{route} returned {resp.status_code}"
        assert "text/html" in resp.headers.get("content-type", "")
        assert "Nera — AI-Powered Business Automation" in resp.text
        assert 'id="app"' in resp.text


def test_greenfield_static_assets_serve_correctly():
    """Verify static assets are mounted and served with proper MIME types."""
    assets = [
        ("/frontend/src/app.js", 200, "javascript"),
        ("/frontend/src/styles/tokens.css", 200, "css"),
        ("/frontend/src/styles/components.css", 200, "css"),
        ("/frontend/src/styles/animations.css", 200, "css"),
        ("/frontend/src/brand/nera-logo.svg", 200, "svg"),
        ("/frontend/src/brand/nera-emblem.svg", 200, "svg"),
    ]
    for path, expected_status, mime_sub in assets:
        resp = client.get(path)
        assert resp.status_code == expected_status, f"{path} returned {resp.status_code}"
        assert mime_sub in resp.headers.get("content-type", "").lower()
