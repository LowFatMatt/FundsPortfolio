"""Brand theming tests — the ?brand= URL contract (D-22, MVP-3).

The Kundenportal colour themes (Provinzial West green / Nord blue /
Sparkassen blue / HFK red, plans/user-journey-redesign.md §3.2) are served as
per-brand M3 token sheets:

* ``/?brand=<slug>`` renders the app shell wired to that brand's
  ``tokens.css`` (unknown slugs fall back to the default brand),
* ``/brand/<slug>/<file>`` serves brand assets (token sheets, fonts),
* brand token sheets define the full ``--md-sys-color-*`` role set the
  components consume,
* path traversal on the asset route is rejected.
"""

import pytest

from funds_portfolio.app import create_app
from funds_portfolio.data.providers import reset_provider
from funds_portfolio.data.fund_manager import reset_fund_manager

THEMES = ("provinzial-west", "provinzial-nord", "sparkassen", "hfk")


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("CUSTOMER", "general")
    monkeypatch.delenv("BRAND", raising=False)
    reset_provider()
    reset_fund_manager()
    app = create_app()
    app.config["TESTING"] = True
    yield app
    reset_provider()
    reset_fund_manager()


@pytest.fixture
def client(app):
    return app.test_client()


def test_default_index_renders_without_token_sheet(client):
    """The default prototype brand has no M3 token sheet (dark dev look
    stays via style.css :root); Provinzial themes wire one via ?brand=."""
    resp = client.get("/")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "app-bar" in html
    assert "tokens.css" not in html


@pytest.mark.parametrize("slug", THEMES)
def test_brand_param_wires_token_sheet(client, slug):
    resp = client.get(f"/?brand={slug}")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert f"/brand/{slug}/tokens.css" in html


def test_unknown_brand_falls_back_to_default(client):
    resp = client.get("/?brand=does-not-exist")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "brand/does-not-exist" not in html


@pytest.mark.parametrize("slug", THEMES)
def test_token_sheet_defines_m3_roles(client, slug):
    resp = client.get(f"/brand/{slug}/tokens.css")
    assert resp.status_code == 200
    css = resp.get_data(as_text=True)
    for role in (
        "--md-sys-color-primary",
        "--md-sys-color-on-primary",
        "--md-sys-color-surface",
        "--md-sys-color-on-surface",
        "--md-sys-color-error",
        "--font-body",
    ):
        assert role in css, (slug, role)


def test_brand_primary_colours_differ(client):
    """The four themes are actually distinct colour identities."""
    primaries = {}
    for slug in THEMES:
        css = client.get(f"/brand/{slug}/tokens.css").get_data(as_text=True)
        for line in css.splitlines():
            if line.strip().startswith("--md-sys-color-primary:"):
                primaries[slug] = line.split(":")[1].strip().rstrip(";")
                break
    assert len(primaries) == len(THEMES)
    assert len(set(primaries.values())) == len(THEMES)


def test_brand_fonts_served(client):
    resp = client.get("/brand/sparkassen/fonts/iconfont-provinzial.woff2")
    assert resp.status_code == 200


@pytest.mark.parametrize("slug", THEMES)
def test_brand_logo_served(client, slug):
    resp = client.get(f"/brand/{slug}/logo.svg")
    assert resp.status_code == 200
    assert resp.get_data(as_text=True).lstrip().startswith("<svg")


def test_brand_text_font_served(client):
    """The scraped "Sparkasse Web" text font (MVP-3 input, 2026-10-06)."""
    resp = client.get(
        "/brand/provinzial-west/fonts/sparkasse-web-400-500.1348175173db8b19.woff"
    )
    assert resp.status_code == 200
    assert resp.get_data()[:4] == b"wOFF"
    resp = client.get("/brand/sparkassen/fonts/SparkasseWeb-Regular.ttf")
    assert resp.status_code == 200


def test_index_renders_brand_logo(client):
    resp = client.get("/?brand=provinzial-west")
    html = resp.get_data(as_text=True)
    assert "/brand/provinzial-west/logo.svg" in html
    assert "/brand/provinzial-west/tokens.css" in html


def test_brand_asset_traversal_blocked(client):
    resp = client.get("/brand/default/..%2f..%2ffunds_portfolio%2fapp.py")
    assert resp.status_code == 404
