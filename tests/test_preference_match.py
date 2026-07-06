"""Tests for the shared preference_satisfaction helper.

These pin the counting rule agreed with the user: dynamic denominator (2..7),
set-membership across selected funds, and reuse of the engine's trait semantics
(no second truth). Includes the user's worked example from the plan.
"""

from funds_portfolio.portfolio.preference_match import preference_satisfaction


def _rec(
    region="global", theme="NONE", is_etf=True, esg_label=None, etf_not_available=False
):
    return {
        "region": region,
        "theme": theme,
        "is_etf": is_etf,
        "esg_label": esg_label,
        "etf_not_available": etf_not_available,
    }


def _eng_q():  # engine questions: aggressive + PREFER_ESG + prefer_etf, no region/theme
    return {
        "risk_approach": "aggressive",
        "esg_preference": "PREFER_ESG",
        "etf_preference": "prefer_etf",
        "preferred_regions": [],
        "preferred_themes": [],
    }


def test_minimum_denominator_is_three_single_selects():
    # No region/theme selected -> denominator is exactly 3 (risk+esg+etf).
    # All three single-selects fulfilled here -> 3/3.
    recs = [_rec(esg_label="SFDR_ARTICLE_8")]  # an ETF that's also ESG
    ps = preference_satisfaction(_eng_q(), recs)
    assert ps["total"] == 3
    assert ps["fulfilled"] == 3
    assert ps["display"] == "3/3"
    assert [it["dimension"] for it in ps["per_item"]] == [
        "risk_approach",
        "esg_preference",
        "etf_preference",
    ]


def test_max_denominator_is_seven():
    answers = dict(_eng_q())
    answers["preferred_regions"] = ["asia", "europe"]
    answers["preferred_themes"] = ["technology", "water"]
    recs = [_rec(region="asia", theme="technology", esg_label="SFDR_ARTICLE_9")]
    ps = preference_satisfaction(answers, recs)
    assert ps["total"] == 7
    # asia met, technology met; europe + water not; risk/esg/etf all met -> 5/7.
    assert ps["fulfilled"] == 5
    assert ps["display"] == "5/7"


def test_users_worked_example_full_fulfillment():
    # aggressive + PREFER_ESG + prefer_etf + [asia] + [water]; portfolio covers
    # every requested trait -> 5/5.
    answers = dict(_eng_q())
    answers["preferred_regions"] = ["asia"]
    answers["preferred_themes"] = ["water"]
    recs = [
        _rec(region="asia", esg_label="SFDR_ARTICLE_8"),  # asia+esg+etf
        _rec(theme="water"),  # water
    ]
    ps = preference_satisfaction(answers, recs)
    assert ps["total"] == 5
    assert ps["fulfilled"] == 5
    assert ps["display"] == "5/5"
    by_dim = {it["dimension"]: it for it in ps["per_item"]}
    assert by_dim["risk_approach"]["fulfilled"] is True
    assert by_dim["esg_preference"]["fulfilled"] is True
    assert by_dim["etf_preference"]["fulfilled"] is True
    assert by_dim["preferred_regions"]["fulfilled"] is True
    assert by_dim["preferred_themes"]["fulfilled"] is True


def test_risk_not_fulfilled_when_relaxation_used():
    ps = preference_satisfaction(
        _eng_q(),
        [_rec(esg_label="SFDR_ARTICLE_8")],
        relaxations=[{"name": "x"}],
        used_fallback_risk=False,
    )
    risk = next(it for it in ps["per_item"] if it["dimension"] == "risk_approach")
    assert risk["fulfilled"] is False
    assert ps["fulfilled"] == 2  # esg + etf only


def test_esg_hard_filter_requires_every_fund_sustainable():
    answers = dict(_eng_q())
    answers["esg_preference"] = "ART_8_9_ONLY"
    recs = [
        _rec(esg_label="SFDR_ARTICLE_8"),
        _rec(esg_label=None),  # one non-ESG fund -> not all -> unfulfilled
    ]
    ps = preference_satisfaction(answers, recs)
    esg = next(it for it in ps["per_item"] if it["dimension"] == "esg_preference")
    assert esg["fulfilled"] is False


def test_etf_only_unfulfilled_when_active_backfill_used():
    answers = dict(_eng_q())
    answers["etf_preference"] = "etf_only"
    recs = [_rec(), _rec(is_etf=False, etf_not_available=True)]
    ps = preference_satisfaction(answers, recs)
    etf = next(it for it in ps["per_item"] if it["dimension"] == "etf_preference")
    assert etf["fulfilled"] is False


def test_none_theme_chip_does_not_count():
    # "none" is the "no theme" placeholder; it must NOT add a slot.
    answers = dict(_eng_q())
    answers["preferred_themes"] = ["none"]
    ps = preference_satisfaction(answers, [_rec(esg_label="SFDR_ARTICLE_8")])
    assert ps["total"] == 3  # still just risk+esg+etf


def test_engine_emits_preference_satisfaction_in_metrics_and_trace():
    # Integration: the engine must populate both portfolio_metrics and
    # decision_trace with the shared breakdown.
    from funds_portfolio.data.fund_manager import FundManager
    from funds_portfolio.portfolio.decision_engine import DecisionEngine

    funds = FundManager("funds_database.json").get_all_funds()
    answers = dict(_eng_q())
    answers["preferred_regions"] = ["north_america"]
    answers["preferred_themes"] = ["energy"]
    res = DecisionEngine().recommend(answers, funds)
    pm = res["portfolio_metrics"].get("preference_satisfaction")
    dt = res["decision_trace"].get("preference_satisfaction")
    assert pm is not None and dt is not None
    assert pm == dt  # same object in both places
    assert pm["total"] == 5
    assert pm["display"] == f"{pm['fulfilled']}/{pm['total']}"
    assert isinstance(pm["per_item"], list) and len(pm["per_item"]) == 5
