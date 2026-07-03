"""Tests for the thematic_guarantee / regional_cap engine toggles.

Builds deterministic universes where the scoring is predictable, then asserts
the toggles gate the corresponding code blocks — proven via the decision_trace
selection events and fund membership, not by reverse-engineering every score.
"""

import json

import pytest

from funds_portfolio.portfolio.decision_engine import DecisionEngine


def _fund(isin, *, sharpe, mdd, fee, region="global", theme="NONE",
          srri=4, vol=12.0, is_etf=True, esg_label=None, provider=None,
          asset_class="equity"):
    """A minimal eligible fund. Base score is min-max over the pool, so to make
    a fund reliably low/high base we set it to the extreme on every component."""
    return {
        "isin": isin, "name": f"F {isin}", "provider": provider or f"P {isin[0]}",
        "asset_class": asset_class, "region": region, "theme": theme,
        "esg_label": esg_label, "is_etf": is_etf, "srri": srri, "risk_level": srri,
        "volatility": vol, "sharpe_ratio": sharpe, "max_drawdown": mdd,
        "yearly_fee": fee,
    }


@pytest.fixture()
def write_universe(tmp_path):
    """Return a callable that writes a universe and returns its path."""

    def _write(funds):
        path = tmp_path / "funds_database.json"
        path.write_text(json.dumps({"funds_database": funds}), encoding="utf-8")
        return str(path)

    return _write


def _selected(engine, funds, answers):
    res = engine.recommend(answers, funds)
    return res["recommendations"], res["decision_trace"]


def _selection_events(trace):
    return trace.get("selection", {}).get("events", [])


# --------------------------------------------------------------------------- #
# thematic_guarantee
# --------------------------------------------------------------------------- #
def test_thematic_guarantee_toggles_force_insert(write_universe):
    # 6 high-base core funds + 1 zero-base theme fund. top-5 by score are cores;
    # the theme fund only enters via the thematic guarantee.
    cores = [
        _fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1) for i in range(6)
    ]
    theme_fund = _fund("THEME", sharpe=0.1, mdd=40.0, fee=1.5, theme="energy")
    funds = cores + [theme_fund]
    answers = {
        "risk_approach": "aggressive", "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [], "preferred_themes": ["energy"],
    }

    on_recs, on_trace = _selected(
        DecisionEngine(thematic_guarantee=True), funds, answers
    )
    off_recs, off_trace = _selected(
        DecisionEngine(thematic_guarantee=False), funds, answers
    )

    on_isins = {r["isin"] for r in on_recs}
    off_isins = {r["isin"] for r in off_recs}
    on_events = _selection_events(on_trace)
    off_events = _selection_events(off_trace)

    # Guarantee ON: theme fund force-inserted, event recorded.
    assert "THEME" in on_isins
    assert any(e.get("type") == "thematic_insert" for e in on_events)
    # Guarantee OFF: no force-insert, theme fund absent, no event.
    assert "THEME" not in off_isins
    assert not any(e.get("type") == "thematic_insert" for e in off_events)


def test_thematic_guarantee_default_is_on():
    # Backward-compat: default constructor keeps the guarantee active.
    eng = DecisionEngine()
    assert eng.thematic_guarantee is True
    assert eng.regional_cap is True


# --------------------------------------------------------------------------- #
# regional_cap
# --------------------------------------------------------------------------- #
def test_regional_cap_toggles_concentration_limit(write_universe):
    # 5 high-base funds all from north_america + 2 lower-base global fillers.
    # top-5 by score are the 5 north_america funds -> cap triggers.
    regional = [
        _fund(f"R{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="north_america")
        for i in range(5)
    ]
    fillers = [
        _fund(f"G{i}", sharpe=1.0, mdd=10.0, fee=0.2, region="global")
        for i in range(2)
    ]
    funds = regional + fillers
    answers = {
        "risk_approach": "aggressive", "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["north_america"], "preferred_themes": [],
    }

    on_recs, on_trace = _selected(
        DecisionEngine(regional_cap=True), funds, answers
    )
    off_recs, off_trace = _selected(
        DecisionEngine(regional_cap=False), funds, answers
    )

    def _regional_count(recs):
        return sum(1 for r in recs if r.get("region") == "north_america")

    on_events = _selection_events(on_trace)
    off_events = _selection_events(off_trace)

    # Cap ON: at most 3 regional funds, drop events recorded.
    assert _regional_count(on_recs) <= 3
    assert any(e.get("type") == "regional_cap_drop" for e in on_events)
    # Cap OFF: all 5 regional funds survive, no drop events.
    assert _regional_count(off_recs) == 5
    assert not any(e.get("type") == "regional_cap_drop" for e in off_events)
