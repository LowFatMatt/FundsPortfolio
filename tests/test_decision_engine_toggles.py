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

    # Per-value cap ON: at most 2 of same region (all 5 are north_america),
    # drop events recorded.
    assert _regional_count(on_recs) <= 2
    assert any(e.get("type") == "regional_cap_drop" for e in on_events)
    # Cap OFF: all 5 regional funds survive, no drop events.
    assert _regional_count(off_recs) == 5
    assert not any(e.get("type") == "regional_cap_drop" for e in off_events)


def test_regional_guarantee_toggles_force_insert(write_universe):
    # 6 high-base global funds (top-5 by score); user wants "asia" which only a
    # low-base fund carries — the regional guarantee must force it in.
    cores = [_fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="global") for i in range(6)]
    asia_fund = _fund("ASIA", sharpe=0.1, mdd=40.0, fee=1.5, region="asia")
    funds = cores + [asia_fund]
    answers = {
        "risk_approach": "aggressive", "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["asia"], "preferred_themes": [],
    }
    on_recs, on_trace = _selected(
        DecisionEngine(regional_guarantee=True), funds, answers
    )
    off_recs, off_trace = _selected(
        DecisionEngine(regional_guarantee=False), funds, answers
    )
    on_isins = {r["isin"] for r in on_recs}
    off_isins = {r["isin"] for r in off_recs}
    on_events = _selection_events(on_trace)
    off_events = _selection_events(off_trace)

    # Guarantee ON: ASIA force-inserted, event recorded.
    assert "ASIA" in on_isins
    assert any(e.get("type") == "regional_insert" for e in on_events)
    # Guarantee OFF: no force-insert, ASIA absent, no event.
    assert "ASIA" not in off_isins
    assert not any(e.get("type") == "regional_insert" for e in off_events)


def test_regional_guarantee_does_not_evict_thematic_insert(write_universe):
    # Cross-dimension safety: when the regional guarantee needs to make room,
    # it must NOT drop a fund that the thematic guarantee already inserted.
    cores = [_fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="global") for i in range(6)]
    theme_fund = _fund("THEME", sharpe=0.1, mdd=40.0, fee=1.5, theme="energy", region="global")
    asia_fund = _fund("ASIA", sharpe=0.1, mdd=40.0, fee=1.5, region="asia")
    funds = cores + [theme_fund, asia_fund]
    answers = {
        "risk_approach": "aggressive", "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["asia"], "preferred_themes": ["energy"],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    isins = {r["isin"] for r in recs}
    events = _selection_events(trace)

    # Both guarantees fired: THEME + ASIA in the portfolio.
    assert "THEME" in isins
    assert "ASIA" in isins
    # The regional guarantee did NOT drop the theme fund.
    regional_ev = [e for e in events if e.get("type") == "regional_insert"]
    if regional_ev:
        assert regional_ev[0].get("dropped") != "THEME"


def test_per_value_region_cap_allows_two_different_regions(write_universe):
    # 2 asia + 2 europe + 1 global = 4 preferred-region funds, max 2 per value
    # → all 4 should survive (2 asia OK, 2 europe OK; total 4 > old cap of 3).
    funds = [
        _fund(f"A{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="asia") for i in range(2)
    ] + [
        _fund(f"E{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="europe") for i in range(2)
    ] + [_fund("G", sharpe=2.0, mdd=5.0, fee=0.1, region="global")]
    answers = {
        "risk_approach": "aggressive", "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["asia", "europe"], "preferred_themes": [],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    by_region = {}
    for r in recs:
        by_region[r["region"]] = by_region.get(r["region"], 0) + 1
    # No preferred region has > 2 funds; both asia and europe present.
    assert by_region.get("asia", 0) <= 2
    assert by_region.get("europe", 0) <= 2
    assert by_region.get("asia", 0) >= 1
    assert by_region.get("europe", 0) >= 1


def test_theme_cap_drops_excess_same_theme(write_universe):
    # 4 same-theme funds in top-5 → cap drops to max 2.
    themed = [
        _fund(f"T{i}", sharpe=2.0, mdd=5.0, fee=0.1, theme="energy") for i in range(4)
    ]
    fillers = [_fund(f"G{i}", sharpe=1.0, mdd=10.0, fee=0.2) for i in range(2)]
    funds = themed + fillers
    answers = {
        "risk_approach": "aggressive", "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [], "preferred_themes": ["energy"],
    }
    on_recs, on_trace = _selected(
        DecisionEngine(theme_cap=True), funds, answers
    )
    off_recs, off_trace = _selected(
        DecisionEngine(theme_cap=False), funds, answers
    )
    def _theme_count(recs):
        return sum(1 for r in recs if r.get("theme") == "energy")
    # Cap ON: ≤ 2 energy funds.
    assert _theme_count(on_recs) <= 2
    assert any(e.get("type") == "theme_cap_drop" for e in _selection_events(on_trace))
    # Cap OFF: all 4 survive.
    assert _theme_count(off_recs) == 4
    assert not any(e.get("type") == "theme_cap_drop" for e in _selection_events(off_trace))
