"""Per-portfolio metrics computed from a single ``DecisionEngine.recommend`` result.

Objective (Phase 1): **preference-satisfaction + diversification**. A
**boost-hijack diagnostic** is reported alongside but is deliberately NOT part
of the optimization objective (it explains *why* a fund was selected, e.g. the
port_20260624 case where a Theme boost of 30 pulled a base-26 fund into the
top 5 while a base-51 fund was dropped).

All sub-metrics are in [0, 1] (higher = better) unless flagged as a raw
diagnostic. The function consumes the same dict shape the engine returns, so
tests can feed synthetic results without running the engine.
"""

from __future__ import annotations

from typing import Any, Dict, List, Sequence

_ESG_LABELS = {"SFDR_ARTICLE_8", "SFDR_ARTICLE_9"}


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _alloc_weight(rec: Dict[str, Any]) -> float:
    return _as_float(rec.get("allocation_percent"), 0.0) / 100.0


def _hhi(shares: Sequence[float]) -> float:
    """Herfindahl-Hirschman index of allocation shares (0 = perfectly diverse)."""
    positive = [x for x in shares if x > 0]
    total = sum(positive)
    if total <= 0:
        return 0.0
    return sum((x / total) ** 2 for x in positive)


def _mean(values: Sequence[float]) -> float:
    cleaned = [v for v in values if v is not None]
    if not cleaned:
        return 0.0
    return sum(cleaned) / len(cleaned)


def compute_metrics(
    user_answers: Dict[str, Any],
    result: Dict[str, Any],
    *,
    final_fund_count: int = 5,
    min_allocation_pct: int = 10,
    pref_weight: float = 0.5,
    div_weight: float = 0.5,
) -> Dict[str, Any]:
    """Compute the full metric vector for one (answers, result) pair.

    Args:
        user_answers: the answers fed to ``recommend``.
        result: the dict returned by ``DecisionEngine.recommend``.
        final_fund_count: target portfolio size (engine default 5).
        min_allocation_pct: per-fund floor (engine default 10%).
        pref_weight/div_weight: composite weights for preference vs.
            diversification (normalised internally).
    """
    recs: List[Dict[str, Any]] = result.get("recommendations") or []
    pmetrics: Dict[str, Any] = result.get("portfolio_metrics") or {}
    trace: Dict[str, Any] = result.get("decision_trace") or {}
    risk_profile = result.get("risk_profile") or pmetrics.get("risk_profile")

    esg_pref = str(user_answers.get("esg_preference") or "NONE")
    etf_pref = str(user_answers.get("etf_preference") or "no_preference")
    pref_regions = {str(r).lower() for r in (user_answers.get("preferred_regions") or [])}
    pref_themes = {str(t).lower() for t in (user_answers.get("preferred_themes") or [])}
    regions_active = bool(pref_regions)
    themes_active = bool(pref_themes)

    total_weight = sum(_alloc_weight(r) for r in recs) or 1.0

    # ---------------- Preference satisfaction ----------------
    relaxations = trace.get("relaxations") or []
    used_fallback = bool(trace.get("used_fallback_risk"))
    risk_adherence = 1.0 if (not relaxations and not used_fallback) else 0.0

    esg_share = (
        sum(
            _alloc_weight(r)
            for r in recs
            if str(r.get("esg_label") or "").upper() in _ESG_LABELS
        )
        / total_weight
    )
    if esg_pref == "NONE":
        esg_match = 1.0
    elif esg_pref == "ART_8_9_ONLY":
        esg_match = (
            1.0
            if recs
            and all(
                str(r.get("esg_label") or "").upper() in _ESG_LABELS for r in recs
            )
            else esg_share
        )
    else:  # PREFER_ESG
        esg_match = esg_share

    active_fallbacks = sum(1 for r in recs if r.get("etf_not_available"))
    etf_share_m = _as_float(pmetrics.get("etf_share"), esg_share)
    if etf_pref == "no_preference":
        etf_match = 1.0
    elif etf_pref == "etf_only":
        etf_match = 1.0 if not active_fallbacks else max(0.0, etf_share_m)
    else:  # prefer_etf
        etf_match = _as_float(pmetrics.get("etf_share"), 0.0)

    region_exposures = pmetrics.get("region_exposures") or {}
    if not regions_active:
        region_match = 1.0
    else:
        match_weight = sum(
            _as_float(v)
            for k, v in region_exposures.items()
            if str(k).lower() in pref_regions
        )
        region_match = max(0.0, min(1.0, match_weight))

    theme_exposures = pmetrics.get("theme_exposures") or {}
    selected_themes = {
        str(r.get("theme") or "").lower() for r in recs
    } - {"none", ""}
    if not themes_active:
        theme_exposure_match = 1.0
        theme_coverage = 1.0
    else:
        match_weight = sum(
            _as_float(v)
            for k, v in theme_exposures.items()
            if str(k).lower() in pref_themes
        )
        theme_exposure_match = max(0.0, min(1.0, match_weight))
        covered = sum(1 for t in pref_themes if t in selected_themes)
        theme_coverage = covered / len(pref_themes) if pref_themes else 1.0
    theme_match = (theme_exposure_match + theme_coverage) / 2.0

    pref_components: List[float] = [risk_adherence, esg_match, etf_match]
    if regions_active:
        pref_components.append(region_match)
    if themes_active:
        pref_components.append(theme_match)
    pref_score = _mean(pref_components)

    # ---------------- Diversification ----------------
    provider_shares: Dict[str, float] = {}
    asset_shares: Dict[str, float] = {}
    region_shares: Dict[str, float] = {}
    satellite_total = 0.0
    min_alloc_pct = 101.0
    for r in recs:
        w = _alloc_weight(r)
        provider = str(r.get("provider") or "unknown")
        asset_class = str(r.get("asset_class") or "other").lower()
        region = str(r.get("region") or "unknown").lower()
        provider_shares[provider] = provider_shares.get(provider, 0.0) + w
        asset_shares[asset_class] = asset_shares.get(asset_class, 0.0) + w
        region_shares[region] = region_shares.get(region, 0.0) + w
        if str(r.get("core_satellite_class") or "").lower() == "satellite":
            satellite_total += w
        min_alloc_pct = min(min_alloc_pct, _as_float(r.get("allocation_percent"), 0.0))

    provider_div = len(provider_shares) / final_fund_count
    asset_div = len(asset_shares) / final_fund_count
    region_div = len(region_shares) / final_fund_count
    satellite_cap_ok = 1.0 if satellite_total <= 0.3001 else 0.0
    min_allocation_ok = (
        1.0 if (not recs or min_alloc_pct >= min_allocation_pct - 1e-9) else 0.0
    )
    completeness = min(1.0, len(recs) / final_fund_count)

    div_score = _mean(
        [
            provider_div,
            asset_div,
            region_div,
            satellite_cap_ok,
            min_allocation_ok,
            completeness,
        ]
    )

    # ---------------- Boost-hijack diagnostic (reported only) ----------------
    ranking = trace.get("ranking") or {}
    candidates = ranking.get("candidates") or []
    selected_isins = {r.get("isin") for r in recs}

    sel_bases = [
        c.get("base")
        for c in candidates
        if c.get("isin") in selected_isins and c.get("base") is not None
    ]
    nonsel_bases = [
        c.get("base")
        for c in candidates
        if c.get("isin") not in selected_isins and c.get("base") is not None
    ]
    all_bases_sorted = sorted(
        [c.get("base") for c in candidates if c.get("base") is not None],
        reverse=True,
    )
    top5_mean = (
        _mean(all_bases_sorted[:final_fund_count]) if all_bases_sorted else 0.0
    )
    sel_mean_base = _mean(sel_bases)
    min_sel_base = min(sel_bases) if sel_bases else 0.0
    max_nonsel_base = max(nonsel_bases) if nonsel_bases else 0.0
    base_gap_top5 = sel_mean_base - top5_mean
    hijack_detected = bool(
        sel_bases and nonsel_bases and min_sel_base < max_nonsel_base
    )
    hijack_gap = (max_nonsel_base - min_sel_base) if hijack_detected else 0.0

    sel_finals = [
        c.get("final")
        for c in candidates
        if c.get("isin") in selected_isins and c.get("final") is not None
    ]
    sel_boost_totals = []
    for c in candidates:
        if c.get("isin") in selected_isins:
            boosts = c.get("boosts") or {}
            sel_boost_totals.append(sum(_as_float(v) for v in boosts.values()))
    boost_dependency = (
        _mean(
            [
                (b / f if f else 0.0)
                for b, f in zip(sel_boost_totals, sel_finals)
            ]
        )
        if sel_finals
        else 0.0
    )

    events = (trace.get("selection", {}) or {}).get("events") or []
    thematic_inserts = sum(1 for e in events if e.get("type") == "thematic_insert")
    regional_drops = sum(1 for e in events if e.get("type") == "regional_cap_drop")

    # ---------------- Composite ----------------
    weight_sum = pref_weight + div_weight
    overall = (
        (pref_weight * pref_score + div_weight * div_score) / weight_sum
        if weight_sum > 0
        else 0.0
    )

    return {
        # identity / raw
        "risk_profile": risk_profile,
        "num_funds": len(recs),
        "weighted_fee": pmetrics.get("weighted_fee"),
        "srri_proxy": pmetrics.get("srri_proxy"),
        "empty": len(recs) == 0,
        # preference
        "pref_score": round(pref_score, 4),
        "risk_adherence": risk_adherence,
        "esg_match": round(esg_match, 4),
        "etf_match": round(etf_match, 4),
        "region_match": round(region_match, 4),
        "theme_match": round(theme_match, 4),
        "theme_exposure_match": round(theme_exposure_match, 4),
        "theme_coverage": round(theme_coverage, 4),
        "regions_active": regions_active,
        "themes_active": themes_active,
        # diversification
        "div_score": round(div_score, 4),
        "provider_div": round(provider_div, 4),
        "asset_div": round(asset_div, 4),
        "region_div": round(region_div, 4),
        "provider_hhi": round(_hhi(list(provider_shares.values())), 4),
        "asset_hhi": round(_hhi(list(asset_shares.values())), 4),
        "region_hhi": round(_hhi(list(region_shares.values())), 4),
        "satellite_total": round(satellite_total, 4),
        "satellite_cap_ok": satellite_cap_ok,
        "min_alloc_pct": round(min_alloc_pct, 4) if recs else None,
        "min_allocation_ok": min_allocation_ok,
        "completeness": round(completeness, 4),
        "distinct_providers": len(provider_shares),
        "distinct_asset_classes": len(asset_shares),
        "distinct_regions": len(region_shares),
        # composite + diagnostics
        "overall": round(overall, 4),
        "base_gap_top5": round(base_gap_top5, 4),
        "hijack_detected": hijack_detected,
        "hijack_gap": round(hijack_gap, 4),
        "boost_dependency": round(boost_dependency, 4),
        "thematic_inserts": thematic_inserts,
        "regional_drops": regional_drops,
        "relaxation_count": len(relaxations),
        "used_fallback_risk": used_fallback,
    }
