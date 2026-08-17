"""Tests for the two-pass coverage-first selection and its engine toggles.

Builds deterministic universes where the scoring is predictable, then asserts
the toggle semantics of the two-pass selection (plans/2026-08-17-two-pass-*):

- ``thematic_guarantee`` / ``regional_guarantee`` gate the pass-1 coverage walk
  per dimension;
- ``theme_cap`` / ``regional_cap`` gate the per-kind quota (max
  ``max_per_preferred_value`` funds of the SAME preferred theme/region),
  enforced as *skips* during selection, never as drops after it.

Everything is proven via the decision_trace selection events
(``pass1_select`` / ``pass2_select`` / ``selection_skip`` /
``coverage_unfulfillable``) and fund membership — plus the count invariant:
the portfolio always reaches ``final_fund_count`` when the universe allows it.
"""

import json

import pytest

from funds_portfolio.portfolio.decision_engine import DecisionEngine


def _fund(
    isin,
    *,
    sharpe,
    mdd,
    fee,
    region="global",
    theme="NONE",
    srri=4,
    vol=12.0,
    is_etf=True,
    esg_label=None,
    provider=None,
    asset_class="equity",
):
    """A minimal eligible fund. Base score is min-max over the pool, so to make
    a fund reliably low/high base we set it to the extreme on every component."""
    return {
        "isin": isin,
        "name": f"F {isin}",
        "provider": provider or f"P {isin[0]}",
        "asset_class": asset_class,
        "region": region,
        "theme": theme,
        "esg_label": esg_label,
        "is_etf": is_etf,
        "srri": srri,
        "risk_level": srri,
        "volatility": vol,
        "sharpe_ratio": sharpe,
        "max_drawdown": mdd,
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


def _pass1_events(events, dimension=None, value=None):
    return [
        e
        for e in events
        if e.get("type") == "pass1_select"
        and (
            dimension is None
            or any(m.get("dimension") == dimension for m in e.get("matched", []))
        )
        and (
            value is None or any(m.get("value") == value for m in e.get("matched", []))
        )
    ]


def _skip_events(events, reason):
    return [
        e
        for e in events
        if e.get("type") == "selection_skip" and e.get("reason") == reason
    ]


# --------------------------------------------------------------------------- #
# Coverage pass toggles (thematic_guarantee / regional_guarantee)
# --------------------------------------------------------------------------- #
def test_thematic_guarantee_toggles_coverage_pass(write_universe):
    # 6 high-base core funds + 1 zero-base theme fund. top-5 by score are cores;
    # the theme fund only enters via the pass-1 coverage walk.
    cores = [_fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1) for i in range(6)]
    theme_fund = _fund("THEME", sharpe=0.1, mdd=40.0, fee=1.5, theme="energy")
    funds = cores + [theme_fund]
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["energy"],
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

    # Guarantee ON: theme fund picked in pass 1 (coverage), event recorded with
    # the matched dimension.
    assert "THEME" in on_isins
    assert _pass1_events(on_events, dimension="theme", value="ENERGY")
    # Guarantee OFF: no coverage walk for themes, theme fund absent, no event.
    assert "THEME" not in off_isins
    assert not _pass1_events(off_events, dimension="theme")


def test_regional_guarantee_toggles_coverage_pass(write_universe):
    # 6 high-base global funds (top-5 by score); user wants "asia" which only a
    # low-base fund carries — the pass-1 coverage walk must pick it.
    cores = [
        _fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="global") for i in range(6)
    ]
    asia_fund = _fund("ASIA", sharpe=0.1, mdd=40.0, fee=1.5, region="asia")
    funds = cores + [asia_fund]
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["asia"],
        "preferred_themes": [],
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

    # Guarantee ON: ASIA picked in pass 1, event recorded.
    assert "ASIA" in on_isins
    assert _pass1_events(on_events, dimension="region", value="asia")
    # Guarantee OFF: no coverage walk for regions, ASIA absent, no event.
    assert "ASIA" not in off_isins
    assert not _pass1_events(off_events, dimension="region")


def test_guarantees_default_on():
    # Backward-compat: default constructor keeps both coverage passes active
    # and both quota toggles active.
    eng = DecisionEngine()
    assert eng.thematic_guarantee is True
    assert eng.regional_guarantee is True
    assert eng.theme_cap is True
    assert eng.regional_cap is True
    assert eng.max_per_preferred_value == 2


# --------------------------------------------------------------------------- #
# Quota toggles (theme_cap / regional_cap) — skips, not drops
# --------------------------------------------------------------------------- #
def test_regional_cap_toggles_quota_skip(write_universe):
    # 5 high-base funds all from north_america + 2 lower-base global fillers.
    # Quota = 2: pass 1+2 pick 2 north_america funds, the rest are SKIPPED with
    # region_quota; the final relaxation (completeness > quota) restores the
    # count to 5 by adding 1 more north_america fund, logged as caps_relaxed.
    regional = [
        _fund(f"R{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="north_america")
        for i in range(5)
    ]
    fillers = [
        _fund(f"G{i}", sharpe=1.0, mdd=10.0, fee=0.2, region="global") for i in range(2)
    ]
    funds = regional + fillers
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["north_america"],
        "preferred_themes": [],
    }

    on_recs, on_trace = _selected(DecisionEngine(regional_cap=True), funds, answers)
    off_recs, off_trace = _selected(DecisionEngine(regional_cap=False), funds, answers)

    def _regional_count(recs):
        return sum(1 for r in recs if r.get("region") == "north_america")

    on_events = _selection_events(on_trace)
    off_events = _selection_events(off_trace)

    # Quota ON: quota respected during selection (skips logged), count still
    # restored to 5 (relaxation adds back exactly one fund, caps_relaxed).
    assert len(on_recs) == 5
    assert _regional_count(on_recs) == 3  # 2 quota-compliant + 1 relaxed
    assert _skip_events(on_events, "region_quota")
    assert any(e.get("type") == "caps_relaxed" for e in on_events)
    # Quota OFF: no quota skips — top-5 by score are the 5 regional funds.
    assert len(off_recs) == 5
    assert _regional_count(off_recs) == 5
    assert not _skip_events(off_events, "region_quota")


def test_theme_cap_toggles_quota_skip(write_universe):
    # 4 same-theme funds in top-5 → quota skips keep 2 during selection.
    themed = [
        _fund(f"T{i}", sharpe=2.0, mdd=5.0, fee=0.1, theme="energy") for i in range(4)
    ]
    fillers = [_fund(f"G{i}", sharpe=1.0, mdd=10.0, fee=0.2) for i in range(2)]
    funds = themed + fillers
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["energy"],
    }
    on_recs, on_trace = _selected(DecisionEngine(theme_cap=True), funds, answers)
    off_recs, off_trace = _selected(DecisionEngine(theme_cap=False), funds, answers)

    def _theme_count(recs):
        return sum(1 for r in recs if r.get("theme") == "energy")

    on_events = _selection_events(on_trace)
    off_events = _selection_events(off_trace)

    # Quota ON: 2 energy via selection (1 coverage + 1 fill), extras skipped,
    # count restored to 5 by the relaxation (1 more energy, logged).
    assert len(on_recs) == 5
    assert _theme_count(on_recs) == 3  # 2 quota-compliant + 1 relaxed
    assert _skip_events(on_events, "theme_quota")
    assert any(e.get("type") == "caps_relaxed" for e in on_events)
    # Quota OFF: top-5 by score contain 4 themed funds, no quota skips.
    assert len(off_recs) == 5
    assert _theme_count(off_recs) == 4
    assert not _skip_events(off_events, "theme_quota")


def test_none_theme_placeholder_disables_theme_quota(write_universe):
    # preferred_themes == ["none"] is the no-preference placeholder: it must
    # not activate the theme quota (regression: an early implementation
    # quota-counted the literal "NONE" theme and starved pass 2).
    funds = [_fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1) for i in range(6)]
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["none"],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    assert len(recs) == 5
    assert not _skip_events(_selection_events(trace), "theme_quota")
    assert not _pass1_events(_selection_events(trace))


# --------------------------------------------------------------------------- #
# Count safety + cross-dimension coverage (the original bug scenario)
# --------------------------------------------------------------------------- #
def test_count_never_shrinks_below_target(write_universe):
    # Regression for the original 5→3 bug: a same-theme monoculture in the
    # top-5 plus a second preferred theme previously ended with the theme cap
    # dropping funds without refill. The two-pass selection must always return
    # exactly final_fund_count funds here.
    monoculture = [
        _fund(f"S{i}", sharpe=2.0, mdd=5.0, fee=0.1, theme="sustainability")
        for i in range(4)
    ]
    defense = _fund("DEF", sharpe=0.5, mdd=30.0, fee=0.8, theme="defense")
    fillers = [_fund(f"G{i}", sharpe=1.0, mdd=10.0, fee=0.2) for i in range(2)]
    funds = monoculture + [defense] + fillers
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["sustainability", "defense"],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    isins = {r["isin"] for r in recs}
    events = _selection_events(trace)

    assert len(recs) == 5  # never 3 — the count is safe by construction
    assert "DEF" in isins  # defense covered by pass 1
    assert sum(1 for r in recs if r.get("theme") == "sustainability") == 2
    assert not any(e.get("type") == "caps_relaxed" for e in events)


def test_both_dimensions_covered_count_preserved(write_universe):
    # Cross-dimension coverage: a theme fund AND a region fund must both be
    # picked in pass 1, and the portfolio must still reach 5 funds. With the
    # old swap-based guarantees this scenario could starve; with two additive
    # passes it is structural.
    cores = [
        _fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="global") for i in range(6)
    ]
    theme_fund = _fund(
        "THEME", sharpe=0.1, mdd=40.0, fee=1.5, theme="energy", region="global"
    )
    asia_fund = _fund("ASIA", sharpe=0.1, mdd=40.0, fee=1.5, region="asia")
    funds = cores + [theme_fund, asia_fund]
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["asia"],
        "preferred_themes": ["energy"],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    isins = {r["isin"] for r in recs}

    assert "THEME" in isins
    assert "ASIA" in isins
    assert len(recs) == 5
    assert len(_pass1_events(_selection_events(trace))) == 2


def test_synergy_fund_covers_both_dimensions(write_universe):
    # A single fund carrying BOTH a preferred region and a preferred theme
    # satisfies both in one pick; also_satisfies records the collateral dim.
    cores = [_fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1) for i in range(6)]
    synergy = _fund("SYN", sharpe=0.2, mdd=35.0, fee=1.2, region="asia", theme="energy")
    funds = cores + [synergy]
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["asia"],
        "preferred_themes": ["energy"],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    isins = {r["isin"] for r in recs}
    events = _selection_events(trace)

    assert "SYN" in isins
    assert len(recs) == 5
    assert len(_pass1_events(events)) == 1  # one pick covers both values
    ev = _pass1_events(events)[0]
    matched_dims = {(m["dimension"], m["value"]) for m in ev["matched"]}
    assert ("region", "asia") in matched_dims
    assert ("theme", "ENERGY") in matched_dims


# --------------------------------------------------------------------------- #
# Edge policies: coverage beats quota; unfulfillable values
# --------------------------------------------------------------------------- #
def test_coverage_beats_quota_breach_logged(write_universe):
    # The only carrier of theme t3 also carries region r1, which is already at
    # its quota of 2 from earlier coverage picks. Sweep B must still cover t3
    # and log the quota breach explicitly.
    a0 = _fund("A0", sharpe=2.0, mdd=5.0, fee=0.1, region="r1", theme="t1")
    a1 = _fund("A1", sharpe=1.9, mdd=6.0, fee=0.12, region="r1", theme="t2")
    b0 = _fund("B0", sharpe=0.5, mdd=30.0, fee=0.9, region="r1", theme="t3")
    filler = [
        _fund(f"G{i}", sharpe=1.0, mdd=10.0, fee=0.2, region="global") for i in range(2)
    ]
    funds = [a0, a1, b0] + filler
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["r1"],
        "preferred_themes": ["t1", "t2", "t3"],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    isins = {r["isin"] for r in recs}
    events = _selection_events(trace)

    assert "B0" in isins  # t3 covered despite the r1 quota
    breach_picks = [e for e in _pass1_events(events) if e.get("quota_breached")]
    assert breach_picks
    assert any("region:r1" in b for b in breach_picks[0]["quota_breached"])
    assert len(recs) == 5


def test_unfulfillable_value_is_logged(write_universe):
    # A preferred theme with no carrier anywhere in the universe must surface
    # as a coverage_unfulfillable event (reason: no fund in the universe).
    cores = [_fund(f"C{i}", sharpe=2.0, mdd=5.0, fee=0.1) for i in range(6)]
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["ghost"],
    }
    recs, trace = _selected(DecisionEngine(), cores, answers)
    events = _selection_events(trace)

    assert len(recs) == 5
    unf = [e for e in events if e.get("type") == "coverage_unfulfillable"]
    assert len(unf) == 1
    assert unf[0]["value"] == "GHOST"
    assert "no fund" in unf[0]["reason"]


def test_per_value_quota_allows_two_different_values(write_universe):
    # 2 asia + 2 europe + 1 global: the quota is per VALUE, so 2 asia AND
    # 2 europe coexist; all 5 funds are selectable without any relaxation.
    funds = (
        [_fund(f"A{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="asia") for i in range(2)]
        + [
            _fund(f"E{i}", sharpe=2.0, mdd=5.0, fee=0.1, region="europe")
            for i in range(2)
        ]
        + [_fund("G", sharpe=2.0, mdd=5.0, fee=0.1, region="global")]
    )
    answers = {
        "risk_approach": "aggressive",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": ["asia", "europe"],
        "preferred_themes": [],
    }
    recs, trace = _selected(DecisionEngine(), funds, answers)
    by_region = {}
    for r in recs:
        by_region[r["region"]] = by_region.get(r["region"], 0) + 1

    assert len(recs) == 5
    assert by_region.get("asia") == 2
    assert by_region.get("europe") == 2
    assert not any(e.get("type") == "caps_relaxed" for e in _selection_events(trace))
