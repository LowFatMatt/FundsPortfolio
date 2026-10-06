"""Flow-config contract tests — variant C phase model (MVP-1).

The wizard engine (static/js/app.js) navigates a flattened step list built
from the declarative ``phases`` in ``flows/variantC.json``. These tests pin
the config contract that the phase engine relies on:

* phase order and ids (product-determination → strategy-preferences),
* the entry-channel skip rule encoded in the config
  (``skipOnProductContext`` — docs/user-journey D-10/D-21),
* the retired Komfort/Aktiv persona: no customer-type step and no
  Ja/Nein gate steps in variant C (product decision 2026-10-05),
* ``source: "section"`` steps reference sections that exist in
  ``preferences_schema.json``,
* the /flows/ route serves the new variant.

Behavioural JS tests (entry index, one-way back navigation, hash deep links)
run in the browser; see plans/user-journey-redesign.md §4 MVP-1 acceptance.
"""

import json
from pathlib import Path

import pytest

from funds_portfolio.app import create_app
from funds_portfolio.data.providers import reset_provider
from funds_portfolio.data.fund_manager import reset_fund_manager

FLOWS_DIR = Path(__file__).resolve().parent.parent / "flows"
SCHEMA_PATH = Path(__file__).resolve().parent.parent / "preferences_schema.json"


def _load_variant(variant: str) -> dict:
    return json.loads((FLOWS_DIR / f"variant{variant}.json").read_text(encoding="utf-8"))


@pytest.fixture
def app(monkeypatch):
    monkeypatch.setenv("CUSTOMER", "general")
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


# ---------------------------------------------------------------------------
# Phase schema (variant C)
# ---------------------------------------------------------------------------


def test_variant_c_declares_phases_in_order():
    flow = _load_variant("C")
    phases = flow["phases"]
    assert [p["id"] for p in phases] == [
        "product-determination",
        "strategy-preferences",
    ]


def test_product_determination_phase_encodes_skip_rule():
    """Phase A is skipped one-way when the journey is entered with a
    ?product= handover (Tarifrechner / Online Sales / LeAn). MVP-2 merged the
    payment-mode and amounts questions into one step."""
    phase = _load_variant("C")["phases"][0]
    assert phase["skipOnProductContext"] is True
    step_ids = [s["id"] for s in phase["steps"]]
    assert step_ids == ["goal", "payment", "product"]


def test_payment_step_merges_mode_and_amounts():
    """MVP-2: one screen for payment mode + conditional amounts."""
    steps = {s["id"]: s for s in _load_variant("C")["phases"][0]["steps"]}
    payment = steps["payment"]
    assert payment["section"]["id"] == "beitrag"
    field_ids = [f["id"] for f in payment["fields"]]
    assert field_ids == ["beitragLaufend", "beitragEinmalig"]
    # MVP-2 refinement: positive reveal — an amount field appears only once
    # its payment mode is explicitly chosen (never both before choosing).
    laufend, einmalig = payment["fields"]
    assert {c["equals"] for c in laufend["showIf"]["anyOf"]} == {"laufend", "beides"}
    assert {c["equals"] for c in einmalig["showIf"]["anyOf"]} == {"einmalig", "beides"}


def test_strategy_phase_contains_preferences_without_persona():
    """Komfort/Aktiv (customer-type) is retired in variant C — every customer
    may set preferences; no Ja/Nein gate steps either. MVP-2 merged ESG and
    ETF into one 'preferences' step."""
    phase = _load_variant("C")["phases"][1]
    ids = {s["id"] for s in phase["steps"]}
    assert {"risk", "preferences", "regions", "themes"} <= ids
    assert not ids & {"activity", "region_gate", "themes_gate", "esg", "etf"}
    for step in phase["steps"]:
        assert "showIf" not in step, (
            "strategy-phase steps must not gate on a persona answer"
        )
    prefs = next(s for s in phase["steps"] if s["id"] == "preferences")
    assert prefs["sections"] == ["esg_preference", "etf_preference"]


def test_region_theme_steps_carry_adaptive_cta_and_optional():
    """MVP-2: the gates are absorbed — regions/themes are optional with an
    adaptive CTA (skip label when empty, lock-in label once selected)."""
    phase = _load_variant("C")["phases"][1]
    for step in (s for s in phase["steps"] if s["id"] in ("regions", "themes")):
        assert step.get("optional") is True
        cta = step["cta"]
        assert cta["empty_label"]["de"] and cta["empty_label"]["en"]
        assert cta["filled_label"]["de"] and cta["filled_label"]["en"]
        assert cta["empty_label"] != cta["filled_label"]


def test_single_select_steps_auto_advance():
    """MVP-2: goal, product and risk cards advance on selection."""
    flow = _load_variant("C")
    for phase in flow["phases"]:
        for step in phase["steps"]:
            if step["id"] in ("goal", "product", "risk"):
                assert step.get("auto_advance") is True, step["id"]
            else:
                assert not step.get("auto_advance"), step["id"]


def test_phase_steps_carry_unique_ids():
    flow = _load_variant("C")
    step_ids = [
        s["id"] for phase in flow["phases"] for s in phase["steps"]
    ]
    assert len(step_ids) == len(set(step_ids))


def test_section_steps_reference_known_schema_sections():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    section_ids = {s["id"] for s in schema["questionnaire"]["sections"]}
    for phase in _load_variant("C")["phases"]:
        for step in phase["steps"]:
            if step.get("source") == "section":
                if "section" in step:
                    assert step["section"] in section_ids
                for sid in step.get("sections", []):
                    assert sid in section_ids


# ---------------------------------------------------------------------------
# Backward compatibility (variants A/B stay flat)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("variant", ["A", "B"])
def test_flat_variants_unchanged(variant):
    flow = _load_variant(variant)
    assert "phases" not in flow
    assert isinstance(flow["steps"], list) and flow["steps"]


# ---------------------------------------------------------------------------
# Serving
# ---------------------------------------------------------------------------


def test_flows_route_serves_variant_c(client):
    resp = client.get("/flows/variantC.json")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["id"] == "C"
    assert [p["id"] for p in body["phases"]] == [
        "product-determination",
        "strategy-preferences",
    ]


def test_questionnaire_serves_universe_totals(client):
    """MVP-2: the live feasible-count footer data — per (profile × combo)
    totals, consistent with the per-option feasible tables (same bands)."""
    resp = client.get("/api/questionnaire?lang=en")
    assert resp.status_code == 200
    gating = resp.get_json()["preference_gating"]
    totals = gating["universe_totals"]
    for profile in ("DEFENSIVE", "BALANCED", "OPPORTUNITY"):
        for combo in ("any", "esg8_9", "etf", "esg8_9+etf"):
            assert isinstance(totals[profile][combo], int)
    # The total for the no-filter combo must be the largest per profile.
    for profile, per_combo in totals.items():
        assert per_combo["any"] >= max(per_combo[c] for c in ("esg8_9", "etf", "esg8_9+etf"))
    # Product-reduced overlay recomputes totals on the smaller universe.
    resp80 = client.get("/api/questionnaire?lang=en&product=avg80")
    reduced = resp80.get_json()["preference_gating"]["universe_totals"]
    assert reduced["BALANCED"]["any"] <= totals["BALANCED"]["any"]
