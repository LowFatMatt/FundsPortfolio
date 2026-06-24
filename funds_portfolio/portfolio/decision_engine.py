"""
Decision Engine - preference-aware filtering, scoring, selection,
allocation, and explainability.

Scoring formula (v2, per Provinzial Fondsauswahllogik spec):
  base = (Sharpe_norm × 5.0) + (MDD_norm × 3.0) + (TER_norm × 2.0)
  Each metric min-max normalised to 0–10; base range 0–100.
  MDD and volatility fall back to SRRI-derived proxies when field is absent.

See FUND_SELECTION_LOGIC_SPEC_V2.md for full specification.
"""

from __future__ import annotations

from typing import Dict, List, Any, Tuple, Optional
import logging
import os
import json

logger = logging.getLogger(__name__)

# SRRI → approximate MDD proxy (positive %, e.g. 20.0 = 20%)
SRRI_MDD_PROXY: Dict[int, float] = {
    1: 5.0,
    2: 8.0,
    3: 12.0,
    4: 20.0,
    5: 30.0,
    6: 42.0,
    7: 55.0,
}

# SRRI → approximate annualised volatility proxy (%)
SRRI_VOL_PROXY: Dict[int, float] = {
    1: 0.25,
    2: 1.25,
    3: 3.5,
    4: 7.5,
    5: 12.5,
    6: 20.0,
    7: 30.0,
}

# Explicit (non-catch-all) regions. "global" is treated as a catch-all that
# matches any fund whose region is NOT one of these.
EXPLICIT_REGIONS: set = {
    "germany",
    "europe",
    "north_america",
    "asia",
    "emerging_markets",
}

# Define boost values for preferences. These are added to the base score to influence ranking.
BOOST_ELEVATORS: Dict[str, float] = {
    "ETF": 20.0,
    "ESG": 20.0,
    "Region": 30.0,
    "Theme": 30.0,
}


def _region_matches(fund_region: str, preferred: set) -> bool:
    """Return True if a fund's region satisfies the user's preferred regions.

    A fund matches when its region is explicitly preferred, or when the user
    selected "global" and the fund's region is not one of the explicit regions
    (i.e. "global" means "anything not covered by the named regions").
    """
    region = str(fund_region or "").lower()
    if region in preferred:
        return True
    if "global" in preferred and region not in EXPLICIT_REGIONS:
        return True
    return False


class DecisionEngine:
    """
    Preference-aware portfolio recommender.

    Uses existing fund fields and falls back to proxy metrics when price
    history is missing.
    """

    def __init__(
        self,
        min_candidates: int = 0,  # set the mimimu to zero to avoid relaxations alltogether to find the limits of our funds universe.
        top_k: int = 65,  # seting it to numer of available funds (65) in the universe disables capping
        final_fund_count: int = 5,
        max_per_provider: int = 5,  # the value "5" ultimately disables the provider cap
        max_per_category: int = 5,  # dito
        min_allocation_percentage: int = 10,  # minimum allocation percentage for any fund in the final portfolio
    ):
        self.min_candidates = min_candidates
        self.top_k = top_k
        self.final_fund_count = final_fund_count
        self.max_per_provider = max_per_provider
        self.max_per_category = max_per_category
        self.min_allocation_percentage = min_allocation_percentage
        self._translations = self._load_translations()

    def recommend(
        self,
        user_answers: Dict[str, Any],
        funds: List[Dict[str, Any]],
        language: Optional[str] = None,
    ) -> Dict[str, Any]:
        trace = {"filters": [], "relaxations": [], "used_fallback_risk": False}

        # Normalise ESG preference to the canonical value set, tolerating legacy
        # answers stored in older portfolios (no_requirement/esg_basic/esg_enhanced).
        user_answers = dict(user_answers)
        user_answers["esg_preference"] = self._normalise_esg_preference(
            user_answers.get("esg_preference")
        )

        def note_filter(
            name: str, before: int, after: int, details: Optional[Dict[str, Any]] = None
        ):
            trace["filters"].append(
                {
                    "name": name,
                    "before": before,
                    "after": after,
                    "details": details or {},
                }
            )

        risk_profile, used_fallback = self._map_risk_profile(user_answers)
        trace["used_fallback_risk"] = used_fallback

        working = list(funds)

        # 1) Basic eligibility test for required fileds: isin + name + fee + sharpe + mdd + (srri or risk_level) + volatility
        before = len(working)
        working = [
            f
            for f in working
            if f.get("isin")
            and f.get("name")
            and f.get("yearly_fee")
            and f.get("sharpe_ratio")
            and f.get("max_drawdown")
            and (f.get("srri") or f.get("risk_level"))
            and f.get("volatility")
        ]
        note_filter("required_fields", before, len(working))

        # 1.1) Filter out funds categorized as "mixed" since they are volatile in their inner structure.
        # This needs to be corrected since it seems to filter out too many funds.
        # before = len(working)
        # working = [f for f in working if str(f.get("asset_class") or "").lower() != "mixed"]
        # note_filter("asset_class_mixed_filter", before, len(working))

        # 2) ESG filter
        before = len(working)
        working = self._apply_esg_filter(working, user_answers)
        note_filter(
            "esg_filter",
            before,
            len(working),
            {"preference": user_answers.get("esg_preference")},
        )

        # 3) ETF filter — with fallback if ETF-only leaves too few funds (edge case 2)
        etf_pref = user_answers.get("etf_preference", "no_preference")
        before = len(working)
        post_etf = self._apply_etf_filter(working, user_answers)
        note_filter("etf_filter", before, len(post_etf), {"preference": etf_pref})

        if etf_pref == "etf_only" and len(post_etf) < self.final_fund_count:
            # Not enough ETFs — fill remaining slots with active funds later
            trace["relaxations"].append(
                {
                    "name": "etf_only_fallback",
                    "before": len(post_etf),
                    "after": len(working),
                    "reason": (
                        f"Only {len(post_etf)} ETF(s) available after filtering. "
                        "Active funds will fill remaining positions."
                    ),
                }
            )
            # Keep the ETF subset; active-fund backfill happens in _select_funds
            trace["etf_fallback_active_pool"] = [
                f["isin"] for f in working if not f.get("is_etf")
            ]
            working = (
                post_etf  # scoring proceeds on ETF-only pool; backfill in selection
            )
        else:
            working = post_etf

        # 4) Risk band filter
        pre_risk = list(working)
        before = len(working)
        working = self._apply_risk_band_filter(working, risk_profile)
        note_filter("risk_band", before, len(working), {"risk_profile": risk_profile})

        # 5) Relaxation if too few candidates
        if len(working) < self.min_candidates:
            relaxed = self._apply_relaxed_risk_band(
                pre_risk, user_answers, risk_profile
            )
            trace["relaxations"].append(
                {
                    "name": "risk_band_relaxation",
                    "before": len(working),
                    "after": len(relaxed),
                    "reason": f"Fewer than {self.min_candidates} candidates; SRRI band widened by ±1.",
                    "details": {"risk_profile": risk_profile},
                }
            )
            working = relaxed

        # Ensure we can return at least final_fund_count recommendations.
        # This is a relaxation too: it discards the risk band and reverts to the
        # pre-risk pool. Gate it on min_candidates so that min_candidates == 0
        # disables *all* relaxations, letting an over-restrictive universe fall
        # through to the "no eligible funds" error instead of silently widening.
        if (
            self.min_candidates > 0
            and len(working) < self.final_fund_count
            and len(pre_risk) >= self.final_fund_count
        ):
            trace["relaxations"].append(
                {
                    "name": "final_fund_floor",
                    "before": len(working),
                    "after": len(pre_risk),
                    "reason": "Risk band too restrictive; widened to pre-risk pool to reach minimum fund count.",
                    "details": {"risk_profile": risk_profile},
                }
            )
            working = pre_risk

        # Edge case 1: if still very few funds, add a warning to trace
        if 0 < len(working) < 3:
            trace["warning"] = (
                f"Restricted universe: only {len(working)} fund(s) remain after all filters. "
                "Portfolio may contain funds at the edge of the suitability range."
            )

        if not working:
            return {
                "recommendations": [],
                "risk_profile": risk_profile,
                "portfolio_metrics": {},
                "explanations": {
                    "summary": self._t(
                        language,
                        "decision.no_eligible",
                        "No eligible funds after filtering.",
                    )
                },
                "decision_trace": trace,
            }

        # 6) Score and select
        # For ETF-only fallback: score active funds separately so they can fill gaps
        etf_fallback_isins: set = set(trace.pop("etf_fallback_active_pool", []) or [])
        active_fallback: List[Dict[str, Any]] = []
        if etf_fallback_isins:
            active_pool = [f for f in funds if f.get("isin") in etf_fallback_isins]
            # Apply risk band to active fallback pool
            active_pool = (
                self._apply_risk_band_filter(active_pool, risk_profile) or active_pool
            )
            active_fallback = self._score_funds(active_pool, user_answers, risk_profile)

        scored = self._score_funds(working, user_answers, risk_profile)
        trace["selection"] = {
            "caps": {
                "max_per_provider": self.max_per_provider,
                "max_per_category": self.max_per_category,
            },
            "events": [],
        }
        selected = self._select_funds(
            scored, user_answers, active_fallback=active_fallback, trace=trace
        )

        # 7) Allocate weights
        trace["allocation"] = {"satellite_cap_applied": False, "funds": []}
        allocations = self._allocate_weights(
            selected, user_answers, risk_profile, trace=trace
        )

        # Ranking trace: the top_k pool with per-candidate score breakdown and
        # final selection status. Records the initial sort (performance/vol +
        # boosts) and which funds were skipped/dropped and why. Recording only.
        trace["ranking"] = self._build_ranking_trace(scored, selected, trace)

        # 8) Build recommendations and explanations
        recommendations, explanations = self._build_recommendations(
            selected, allocations, user_answers, risk_profile, language
        )

        # 9) Portfolio metrics
        metrics = self._compute_portfolio_metrics(recommendations, risk_profile)

        # Summary string for UI
        summary = self._build_summary(
            user_answers, risk_profile, metrics, trace, language
        )
        explanations["summary"] = summary

        return {
            "recommendations": recommendations,
            "risk_profile": risk_profile,
            "portfolio_metrics": metrics,
            "explanations": explanations,
            "decision_trace": trace,
        }

    # --- Mapping ---
    def _map_risk_profile(self, user_answers: Dict[str, Any]) -> Tuple[str, bool]:
        """
        Map questionnaire answers to a 3-tier risk profile.
        Returns (profile, used_fallback).
        """
        approach = str(user_answers.get("risk_approach", "")).lower()

        score = {
            "conservative": 1,
            "moderate": 3,
            "aggressive": 4,
        }.get(approach)
        if score is None:
            return "BALANCED", True

        # score = base

        if score <= 2:
            return "DEFENSIVE", False
        if score <= 3:
            return "BALANCED", False
        return "OPPORTUNITY", False

    # --- Filters ---
    # Funds considered "sustainable" for boosting/filtering: SFDR Article 8 & 9.
    _ESG_SUSTAINABLE_LABELS = ("SFDR_ARTICLE_8", "SFDR_ARTICLE_9")

    @staticmethod
    def _normalise_esg_preference(pref: Any) -> str:
        """Map any stored value to the canonical set NONE | PREFER_ESG | ART_8_9_ONLY.

        Tolerates legacy answers (no_requirement/esg_basic/esg_enhanced) from
        portfolios created before the ESG refactor. Unknown -> NONE.
        """
        p = str(pref or "").strip().upper()
        legacy = {
            "NO_REQUIREMENT": "NONE",
            "ESG_BASIC": "ART_8_9_ONLY",
            "ESG_ENHANCED": "ART_8_9_ONLY",
        }
        p = legacy.get(p, p)
        return p if p in ("NONE", "PREFER_ESG", "ART_8_9_ONLY") else "NONE"

    def _is_esg_fund(self, fund: Dict[str, Any]) -> bool:
        return str(fund.get("esg_label") or "").upper() in self._ESG_SUSTAINABLE_LABELS

    def _apply_esg_filter(
        self, funds: List[Dict[str, Any]], user_answers: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        # NONE and PREFER_ESG never exclude funds; only ART_8_9_ONLY hard-filters.
        if user_answers.get("esg_preference") != "ART_8_9_ONLY":
            return funds
        return [f for f in funds if self._is_esg_fund(f)]

    def _apply_etf_filter(
        self, funds: List[Dict[str, Any]], user_answers: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        pref = user_answers.get("etf_preference", "no_preference")
        if pref != "etf_only":
            return funds
        return [f for f in funds if bool(f.get("is_etf"))]

    def _apply_risk_band_filter(
        self, funds: List[Dict[str, Any]], risk_profile: str
    ) -> List[Dict[str, Any]]:
        band = self._risk_band_for_profile(risk_profile)
        return [f for f in funds if self._fund_in_risk_band(f, band)]

    def _fund_in_risk_band(self, fund: Dict[str, Any], band: Dict[str, Any]) -> bool:
        """Return True if fund satisfies SRRI, and (when present) volatility and MDD checks."""
        srri = (
            fund.get("srri") if fund.get("srri") is not None else fund.get("risk_level")
        )
        if srri is None:
            return False
        srri_val = float(srri)
        if not (band["srri_min"] <= srri_val <= band["srri_max"]):
            return False

        vol = fund.get("volatility")
        if vol is not None:
            vol_f = self._as_float(vol)
            vol_max = band.get("vol_max")
            vol_min = band.get("vol_min")
            if vol_max is not None and vol_f > vol_max:
                return False
            if vol_min is not None and vol_f < vol_min:
                return False

        mdd = fund.get("max_drawdown")
        if mdd is not None:
            if self._as_float(mdd) > band["mdd_max"]:
                return False

        return True

    def _apply_relaxed_risk_band(
        self,
        funds: List[Dict[str, Any]],
        user_answers: Dict[str, Any],
        risk_profile: str,
    ) -> List[Dict[str, Any]]:
        band = self._risk_band_for_profile(risk_profile)
        relaxed = dict(band)
        relaxed["srri_min"] = max(1, band["srri_min"] - 1)
        relaxed["srri_max"] = min(7, band["srri_max"] + 1)
        if "vol_max" in relaxed and relaxed["vol_max"] is not None:
            relaxed["vol_max"] = relaxed["vol_max"] + 5.0
        if "vol_min" in relaxed and relaxed["vol_min"] is not None:
            relaxed["vol_min"] = max(0.0, relaxed["vol_min"] - 5.0)
        return [f for f in funds if self._fund_in_risk_band(f, relaxed)]

    def _risk_band_for_profile(self, risk_profile: str) -> Dict[str, Any]:
        # NOTE: Slide 8 is the ultimate truth specifying the risk bands.
        # The document contains other values in further sildes which
        #  do not reflect the final specification.
        if risk_profile == "DEFENSIVE":
            return {
                "srri_min": 1,
                "srri_max": 3,
                "vol_max": 8.0,
                "vol_min": None,
                "mdd_max": 15.0,
            }
        if risk_profile == "OPPORTUNITY":
            return {
                "srri_min": 4,
                "srri_max": 7,
                "vol_max": None,
                "vol_min": 10.0,
                "mdd_max": 50.0,
            }
        # BALANCED
        return {
            "srri_min": 2,
            "srri_max": 5,
            "vol_max": 15.0,
            "vol_min": 5.0,  # reviewed 2: vol_min corrected to be 5.0 (see Spec. Pg./Sld. 8)
            "mdd_max": 30.0,
        }

    @staticmethod
    def _norm10(
        value: float, vmin: float, vmax: float, higher_is_better: bool = True
    ) -> float:
        """Min-max normalise a value to 0–10 scale."""
        if vmax == vmin:
            return 5.0
        n = (value - vmin) / (vmax - vmin) * 10.0
        if not higher_is_better:
            n = 10.0 - n
        return max(0.0, min(10.0, n))

    def _get_mdd(self, fund: Dict[str, Any]) -> Tuple[float, str]:
        """Return (mdd_value, source) where source is 'actual' or 'srri_proxy'."""
        mdd = fund.get("max_drawdown")
        if mdd is not None:
            return self._as_float(mdd), "actual"
        srri = int(self._as_float(fund.get("srri") or fund.get("risk_level") or 4))
        srri = max(1, min(7, srri))
        return SRRI_MDD_PROXY[srri], "srri_proxy"

    def _get_vol(self, fund: Dict[str, Any]) -> float:
        """Return annualised volatility (%), falling back to SRRI proxy."""
        vol = fund.get("volatility")
        if vol is not None:
            return max(0.01, self._as_float(vol))
        srri = int(self._as_float(fund.get("srri") or fund.get("risk_level") or 4))
        srri = max(1, min(7, srri))
        return SRRI_VOL_PROXY[srri]

    # --- Scoring & Selection ---
    def _score_funds(
        self,
        funds: List[Dict[str, Any]],
        user_answers: Dict[str, Any],
        risk_profile: str,
    ) -> List[Dict[str, Any]]:
        # Collect per-metric ranges across eligible universe
        sharpes = [self._as_float(f.get("sharpe_ratio") or 0.0) for f in funds]
        fees = [self._as_float(f.get("yearly_fee") or 0.0) for f in funds]
        mdds = [self._get_mdd(f)[0] for f in funds]

        sharpe_min, sharpe_max = min(sharpes), max(sharpes)
        fee_min, fee_max = min(fees), max(fees)
        mdd_min, mdd_max = min(mdds), max(mdds)

        scored = []
        for f in funds:
            sharpe = self._as_float(f.get("sharpe_ratio") or 0.0)
            fee = self._as_float(f.get("yearly_fee") or 0.0)
            mdd, mdd_source = self._get_mdd(f)

            sharpe_norm = self._norm10(
                sharpe, sharpe_min, sharpe_max, higher_is_better=True
            )
            mdd_norm = self._norm10(mdd, mdd_min, mdd_max, higher_is_better=False)
            ter_norm = self._norm10(fee, fee_min, fee_max, higher_is_better=False)

            base = (sharpe_norm * 5.0) + (mdd_norm * 3.0) + (ter_norm * 2.0)
            boosts = self._preference_boosts(f, user_answers)
            final_score = base + sum(boosts.values())

            f_scored = dict(f)
            f_scored["_scores"] = {
                "base": round(base, 2),
                "sharpe_norm": round(sharpe_norm, 2),
                "mdd_norm": round(mdd_norm, 2),
                "ter_norm": round(ter_norm, 2),
                "mdd_source": mdd_source,
                "boosts": boosts,
                "final": round(final_score, 2),
            }
            scored.append(f_scored)

        scored.sort(
            key=lambda x: (
                x["_scores"]["final"],
                self._as_float(x.get("sharpe_ratio")),
                -self._as_float(x.get("yearly_fee")),
                x.get("isin", ""),
            ),
            reverse=True,
        )
        return scored

    def _preference_boosts(
        self, fund: Dict[str, Any], user_answers: Dict[str, Any]
    ) -> Dict[str, float]:
        boosts: Dict[str, float] = {}

        # Boost are now configured to be higher to significantly change the ranking:
        # see BOOST_ELEVATORS at the top of the file.

        # ETF preference boost
        if user_answers.get("etf_preference") == "prefer_etf" and fund.get("is_etf"):
            boosts["ETF"] = BOOST_ELEVATORS["ETF"]

        # ESG boost: Article 8/9 funds when the user prefers ESG.
        # (NONE ignores ESG entirely; ART_8_9_ONLY is a hard filter, not a bonus.)
        if user_answers.get("esg_preference") == "PREFER_ESG" and self._is_esg_fund(
            fund
        ):
            boosts["ESG"] = BOOST_ELEVATORS["ESG"]

        # Regional preference boost
        preferred_regions = {
            str(r).lower() for r in (user_answers.get("preferred_regions") or [])
        }
        ##if preferred_regions and _region_matches(fund.get("region"), preferred_regions):
        ## Auskommentiert, um wieder nur auf die "einfache" Region zu schauen.
        if preferred_regions and fund.get("region").lower() in preferred_regions:
            boosts["Region"] = BOOST_ELEVATORS["Region"]

        # Thematic preference boost
        preferred_themes = {
            str(t).upper() for t in (user_answers.get("preferred_themes") or [])
        }
        if (
            preferred_themes
            and "NONE" not in preferred_themes
            and str(fund.get("theme") or "").upper() in preferred_themes
        ):
            boosts["Theme"] = BOOST_ELEVATORS["Theme"]

        return boosts

    def _select_funds(
        self,
        scored: List[Dict[str, Any]],
        user_answers: Optional[Dict[str, Any]] = None,
        active_fallback: Optional[List[Dict[str, Any]]] = None,
        trace: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        pool = scored[: self.top_k]
        selected: List[Dict[str, Any]] = []
        provider_count: Dict[str, int] = {}
        category_count: Dict[str, int] = {}

        # Trace-only: record selection decisions without affecting them.
        events = (
            trace["selection"]["events"] if trace and "selection" in trace else None
        )

        def _note(event: Dict[str, Any]) -> None:
            if events is not None:
                events.append(event)

        def category_for(f: Dict[str, Any]) -> str:
            return str(f.get("asset_class") or "other").lower()

        for f in pool:
            provider = f.get("provider") or "unknown"
            category = category_for(f)
            if provider_count.get(provider, 0) >= self.max_per_provider:
                _note(
                    {
                        "type": "provider_cap_skip",
                        "isin": f.get("isin"),
                        "name": f.get("name"),
                        "provider": provider,
                    }
                )
                continue
            if category_count.get(category, 0) >= self.max_per_category:
                _note(
                    {
                        "type": "category_cap_skip",
                        "isin": f.get("isin"),
                        "name": f.get("name"),
                        "category": category,
                    }
                )
                continue
            selected.append(f)
            provider_count[provider] = provider_count.get(provider, 0) + 1
            category_count[category] = category_count.get(category, 0) + 1
            if len(selected) >= self.final_fund_count:
                break

        if len(selected) < self.final_fund_count:
            # Relax diversification caps to reach target count
            added: List[str] = []
            for f in pool:
                if f in selected:
                    continue
                selected.append(f)
                added.append(f.get("isin"))
                if len(selected) >= self.final_fund_count:
                    break
            if added:
                _note({"type": "caps_relaxed", "added": added})

        # Edge case 2: ETF-only fallback — fill remaining slots with active funds
        if active_fallback and len(selected) < self.final_fund_count:
            selected_isins = {f["isin"] for f in selected}
            for f in active_fallback:
                if f["isin"] in selected_isins:
                    continue
                f_copy = dict(f)
                f_copy["etf_not_available"] = True
                selected.append(f_copy)
                selected_isins.add(f["isin"])
                _note(
                    {
                        "type": "etf_fallback_fill",
                        "isin": f.get("isin"),
                        "name": f.get("name"),
                    }
                )
                if len(selected) >= self.final_fund_count:
                    break

        # Thematic guarantee: if user has a theme preference and a matching fund
        # exists in the scored pool but didn't make the cut, force it in.
        preferred_themes: set = set()
        preferred_regions: set = set()
        if user_answers:
            preferred_themes = {
                str(t).upper() for t in (user_answers.get("preferred_themes") or [])
            }
            preferred_regions = {
                str(r).lower() for r in (user_answers.get("preferred_regions") or [])
            }

        if preferred_themes and "NONE" not in preferred_themes:

            def _fund_theme(f: Dict[str, Any]) -> str:
                return str(f.get("theme") or "").upper()

            # Guarantee *each* preferred theme (max 2) is represented by at
            # least one fund. For every theme still missing, swap in the best
            # available matching fund and drop the worst-scoring fund that
            # matches none of the preferred themes — so a fund already covering
            # the other theme is never sacrificed. At most one swap per missing
            # theme, which the 2-theme selection cap keeps to ≤2 swaps total.
            for theme in sorted(preferred_themes):
                if any(_fund_theme(f) == theme for f in selected):
                    continue
                candidates = [
                    f for f in scored if _fund_theme(f) == theme and f not in selected
                ]
                if not candidates:
                    continue  # no fund carries this theme in the universe
                to_insert = candidates[0]
                non_thematic = [
                    f for f in selected if _fund_theme(f) not in preferred_themes
                ]
                if not non_thematic:
                    _note(
                        {
                            "type": "thematic_insert_skipped",
                            "theme": theme,
                            "isin": to_insert.get("isin"),
                            "name": to_insert.get("name"),
                            "reason": "no non-thematic fund available to swap out",
                        }
                    )
                    continue
                worst = min(
                    non_thematic,
                    key=lambda x: x.get("_scores", {}).get("final", 0),
                )
                selected.remove(worst)
                selected.append(to_insert)
                _note(
                    {
                        "type": "thematic_insert",
                        "theme": theme,
                        "inserted": to_insert.get("isin"),
                        "inserted_name": to_insert.get("name"),
                        "dropped": worst.get("isin"),
                        "dropped_name": worst.get("name"),
                    }
                )

        # Edge case 3: Regional concentration cap — max 3 of 5 from same preferred region
        def _region_match(f: Dict[str, Any]) -> bool:
            return _region_matches(f.get("region"), preferred_regions)

        if preferred_regions and len(selected) > 3:
            regional = [f for f in selected if _region_match(f)]
            if len(regional) > 3:
                # Keep top 3, preferring thematic matches so the user's theme
                # preference is not sacrificed to the regional cap.
                def _theme_match_drop(f: Dict[str, Any]) -> bool:
                    return str(f.get("theme") or "").upper() in preferred_themes

                regional_sorted = sorted(
                    regional,
                    key=lambda x: (
                        1
                        if (
                            preferred_themes
                            and "NONE" not in preferred_themes
                            and _theme_match_drop(x)
                        )
                        else 0,
                        x.get("_scores", {}).get("final", 0),
                    ),
                    reverse=True,
                )
                to_drop = {f["isin"] for f in regional_sorted[3:]}
                for f in regional_sorted[3:]:
                    _note(
                        {
                            "type": "regional_cap_drop",
                            "isin": f.get("isin"),
                            "name": f.get("name"),
                        }
                    )
                selected = [f for f in selected if f["isin"] not in to_drop]
                selected_isins = {f["isin"] for f in selected}
                for f in scored:
                    if len(selected) >= self.final_fund_count:
                        break
                    if f["isin"] in selected_isins:
                        continue
                    if _region_match(f):
                        continue  # already have 3
                    selected.append(f)
                    selected_isins.add(f["isin"])
                    _note(
                        {
                            "type": "regional_cap_fill",
                            "isin": f.get("isin"),
                            "name": f.get("name"),
                        }
                    )

        return selected

    def _build_ranking_trace(
        self,
        scored: List[Dict[str, Any]],
        selected: List[Dict[str, Any]],
        trace: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Build the ranking-stage trace: the top_k pool with per-candidate
        score breakdown (base + boosts → final) and final selection status.
        Recording only — does not influence the recommendation.
        """
        selected_isins = {f.get("isin") for f in selected}

        # Map a non-selected candidate to the reason it didn't make the cut.
        status_by_isin: Dict[str, str] = {}
        for ev in trace.get("selection", {}).get("events", []):
            etype = ev.get("type")
            if etype == "provider_cap_skip":
                status_by_isin.setdefault(ev["isin"], "skipped_provider_cap")
            elif etype == "category_cap_skip":
                status_by_isin.setdefault(ev["isin"], "skipped_category_cap")
            elif etype == "thematic_insert":
                status_by_isin.setdefault(ev["dropped"], "dropped_thematic")
            elif etype == "regional_cap_drop":
                status_by_isin.setdefault(ev["isin"], "dropped_regional_cap")

        candidates = []
        for rank, f in enumerate(scored[: self.top_k], start=1):
            sc = f.get("_scores", {})
            isin = f.get("isin")
            if isin in selected_isins:
                status = "selected"
            else:
                status = status_by_isin.get(isin, "not_reached")
            candidates.append(
                {
                    "rank": rank,
                    "isin": isin,
                    "name": f.get("name"),
                    "provider": f.get("provider"),
                    "base": sc.get("base"),
                    "sharpe_norm": sc.get("sharpe_norm"),
                    "mdd_norm": sc.get("mdd_norm"),
                    "ter_norm": sc.get("ter_norm"),
                    "boosts": sc.get("boosts", {}),
                    "final": sc.get("final"),
                    "status": status,
                }
            )

        return {
            "formula": {"sharpe": 5, "mdd": 3, "ter": 2},
            "top_k": self.top_k,
            "candidates": candidates,
        }

    # --- Core-Satellite helpers ---
    @staticmethod
    def _classify_core_satellite(fund: Dict[str, Any]) -> str:
        """Return 'core' if the fund has no thematic focus, 'satellite' otherwise."""
        theme = str(fund.get("theme") or "").upper().strip()
        return "satellite" if theme and theme != "NONE" else "core"

    @staticmethod
    def _tiered_bounds(rank: int, is_satellite: bool) -> Tuple[float, float]:
        """Return (min_weight, max_weight) for a fund based on its rank and class."""
        if is_satellite:
            return 0.10, 0.15  # ambiguous specification corrected: 10-15% it is!
        bounds = [
            (0.25, 0.40),  # Core 1
            (0.15, 0.30),  # Core 2
            (0.10, 0.25),  # Core 3
            (0.10, 0.15),  # Core 4+
        ]
        idx = min(rank, len(bounds) - 1)
        return bounds[idx]

    # --- Allocation ---
    def _allocate_weights(
        self,
        selected: List[Dict[str, Any]],
        user_answers: Dict[str, Any],
        risk_profile: str,
        trace: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, float]:
        if not selected:
            return {}

        # Trace-only: per-fund weighting breakdown, populated as we go.
        alloc_rec: Dict[str, Dict[str, Any]] = {}
        sat_cap_applied = False

        # Classify and rank funds
        cores = [f for f in selected if self._classify_core_satellite(f) == "core"]
        satellites = [
            f for f in selected if self._classify_core_satellite(f) == "satellite"
        ]

        # Assign tiers: cores ranked by their quality score, satellites flat
        ranked: List[Tuple[Dict[str, Any], int, bool]] = []
        for rank, f in enumerate(cores):
            ranked.append((f, rank, False))
        for f in satellites:
            ranked.append((f, 0, True))

        # Inverse volatility raw weights
        inv_vols = {f["isin"]: 1.0 / self._get_vol(f) for f in selected}
        total_inv_vol = sum(inv_vols.values())
        if total_inv_vol <= 0:
            total_inv_vol = 1.0

        raw_weights = {isin: v / total_inv_vol for isin, v in inv_vols.items()}

        # Clip each weight to its tiered bounds
        weights: Dict[str, float] = {}
        for f, rank, is_sat in ranked:
            isin = f["isin"]
            w_min, w_max = self._tiered_bounds(rank, is_sat)
            weights[isin] = max(w_min, min(w_max, raw_weights[isin]))
            alloc_rec[isin] = {
                "isin": isin,
                "name": f.get("name"),
                "class": "satellite" if is_sat else "core",
                "inv_vol_raw": round(raw_weights[isin], 4),
                "tier_bounds": [w_min, w_max],
                "after_clip": round(weights[isin], 4),
                "regional_tilt": False,
            }

        # Enforce satellite total cap (30%)
        sat_isins = {f["isin"] for f in satellites}
        sat_total = sum(weights[i] for i in sat_isins)
        if sat_total > 0.30:
            sat_cap_applied = True
            scale = 0.30 / sat_total
            for isin in sat_isins:
                weights[isin] *= scale
            # Redistribute excess to cores proportionally up to their max
            excess = 1.0 - sum(weights.values())
            core_isins = [f["isin"] for f in cores]
            if core_isins and excess > 0:
                core_total = sum(weights[i] for i in core_isins)
                if core_total > 0:
                    for isin in core_isins:
                        rank_for = next(
                            r for f, r, s in ranked if f["isin"] == isin and not s
                        )
                        _, w_max = self._tiered_bounds(rank_for, False)
                        headroom = max(0.0, w_max - weights[isin])
                        add = excess * (weights[isin] / core_total)
                        weights[isin] += min(add, headroom)

        # Apply regional ×1.2 tilt
        preferred_regions = {
            str(r).lower() for r in (user_answers.get("preferred_regions") or [])
        }
        if preferred_regions:
            for f in selected:
                isin = f["isin"]
                if str(f.get("region") or "").lower() in preferred_regions:
                    _, w_max = self._tiered_bounds(
                        next(r for ff, r, s in ranked if ff["isin"] == isin),
                        isin in sat_isins,
                    )
                    weights[isin] = min(weights[isin] * 1.2, w_max)
                    if isin in alloc_rec:
                        alloc_rec[isin]["regional_tilt"] = True

        # Normalise to sum to 1.0
        weights = self._normalize(weights)

        # Enforce satellite total cap after normalization to account for
        # floating-point rounding and redistribution steps above.
        sat_isins = {f["isin"] for f in satellites}
        sat_total = sum(weights.get(i, 0.0) for i in sat_isins)
        if sat_total > 0.30:
            sat_cap_applied = True
            scale = 0.30 / sat_total
            for isin in sat_isins:
                if isin in weights:
                    weights[isin] = weights[isin] * scale
            # Fill the remaining headroom with cores only. A plain re-normalise
            # here would scale the satellites straight back up over the cap.
            core_isins = [i for i in weights if i not in sat_isins]
            core_total = sum(weights[i] for i in core_isins)
            if core_total > 0:
                target_core = 1.0 - sum(weights.get(i, 0.0) for i in sat_isins)
                cscale = target_core / core_total
                for isin in core_isins:
                    weights[isin] = weights[isin] * cscale

        # Enforce the per-fund minimum allocation as the final step, so it holds
        # after every prior redistribution (clip → satellite cap → tilt →
        # normalise). Lifts any sub-floor fund to the floor and reclaims the
        # deficit from funds with surplus above it.
        floor_applied = False
        floor = self.min_allocation_percentage / 100.0
        if floor > 0:
            before_floor = dict(weights)
            weights = self._enforce_min_allocation(weights, floor)
            floor_applied = any(
                abs(weights.get(i, 0.0) - before_floor.get(i, 0.0)) > 1e-9
                for i in weights
            )

        # Trace-only: finalise the per-fund allocation breakdown.
        if trace is not None and "allocation" in trace:
            for isin, rec in alloc_rec.items():
                rec["final_weight"] = round(weights.get(isin, 0.0), 4)
            trace["allocation"]["min_allocation_applied"] = floor_applied
            trace["allocation"]["min_allocation_percentage"] = (
                self.min_allocation_percentage
            )
            trace["allocation"]["satellite_cap_applied"] = sat_cap_applied
            trace["allocation"]["funds"] = [
                alloc_rec[f["isin"]] for f in selected if f["isin"] in alloc_rec
            ]

        return weights

    @staticmethod
    def _clip_weights(
        weights: Dict[str, float], wmin: float, wmax: float
    ) -> Dict[str, float]:
        return {k: max(wmin, min(wmax, v)) for k, v in weights.items()}

    def _enforce_min_allocation(
        self, weights: Dict[str, float], floor: float
    ) -> Dict[str, float]:
        """Guarantee every fund holds at least ``floor`` of the portfolio.

        Lifts any fund below ``floor`` up to it, and reclaims the deficit from
        funds above ``floor`` in proportion to their surplus (the classic
        "water-filling" floor). Input is assumed normalised (sums to 1.0); the
        result is re-normalised and also sums to 1.0.

        If ``floor`` is infeasible for the fund count (floor × n > 1, e.g. six
        funds at a 20% floor), no per-fund floor can hold, so an equal split is
        the closest achievable allocation.
        """
        if not weights:
            return weights
        n = len(weights)
        if floor * n > 1.0 + 1e-9:
            logger.warning(
                "min allocation %.0f%% infeasible for %d funds; using equal split",
                floor * 100,
                n,
            )
            return {k: 1.0 / n for k in weights}

        weights = dict(weights)
        # One proportional pass restores the floor without pushing any donor
        # below it (deficit ≤ donor surplus whenever the floor is feasible); the
        # loop is a float-safety backstop.
        for _ in range(n):
            deficit = sum(floor - w for w in weights.values() if w < floor)
            if deficit <= 1e-12:
                break
            donor_surplus = sum(w - floor for w in weights.values() if w > floor)
            if donor_surplus <= 0:
                break
            for k, w in weights.items():
                if w < floor:
                    weights[k] = floor
                elif w > floor:
                    weights[k] = w - deficit * (w - floor) / donor_surplus

        return self._normalize(weights)

    @staticmethod
    def _normalize(weights: Dict[str, float]) -> Dict[str, float]:
        total = sum(weights.values())
        if total <= 0:
            n = len(weights)
            return {k: 1.0 / n for k in weights}
        return {k: v / total for k, v in weights.items()}

    @staticmethod
    def _as_float(value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    # --- Output ---
    def _build_recommendations(
        self,
        selected: List[Dict[str, Any]],
        weights: Dict[str, float],
        user_answers: Dict[str, Any],
        risk_profile: str,
        language: Optional[str] = None,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        explanations: Dict[str, Any] = {"per_fund": {}}
        recs: List[Dict[str, Any]] = []

        for f in selected:
            isin = f["isin"]
            alloc = int(round(weights.get(isin, 0.0) * 100))

            reasons = []
            if f.get("is_etf"):
                reasons.append(
                    self._t(
                        language,
                        "decision.reason.etf",
                        "ETF structure supports lower costs and transparency.",
                    )
                )
            esg_pref = user_answers.get("esg_preference")
            if esg_pref == "ART_8_9_ONLY":
                reasons.append(
                    self._t(
                        language,
                        "decision.reason.esg",
                        "Meets your sustainability requirement (SFDR Article 8/9).",
                    )
                )
            elif esg_pref == "PREFER_ESG" and self._is_esg_fund(f):
                reasons.append(
                    self._t(
                        language,
                        "decision.reason.esg_preferred",
                        "Sustainable fund (SFDR Article 8/9), matching your preference.",
                    )
                )
            preferred_regions = {
                str(r).lower() for r in (user_answers.get("preferred_regions") or [])
            }
            if (
                preferred_regions
                and str(f.get("region") or "").lower() in preferred_regions
            ):
                reasons.append(
                    self._t(
                        language,
                        "decision.reason.region",
                        "Matches your regional preference.",
                    )
                )
            preferred_themes = {
                str(t).upper() for t in (user_answers.get("preferred_themes") or [])
            }
            if (
                preferred_themes
                and "NONE" not in preferred_themes
                and str(f.get("theme") or "").upper() in preferred_themes
            ):
                reasons.append(
                    self._t(
                        language,
                        "decision.reason.theme",
                        "Matches your thematic preference.",
                    )
                )

            score_info = f.get("_scores", {})
            reasons.append(
                self._t(
                    language,
                    "decision.reason.score",
                    "Quality score: {score} (Sharpe: {sharpe_norm}, MDD: {mdd_norm}, TER: {ter_norm}).",
                ).format(
                    score=score_info.get("base", "n/a"),
                    sharpe_norm=score_info.get("sharpe_norm", "n/a"),
                    mdd_norm=score_info.get("mdd_norm", "n/a"),
                    ter_norm=score_info.get("ter_norm", "n/a"),
                )
            )
            if f.get("etf_not_available"):
                reasons.append(
                    self._t(
                        language,
                        "decision.reason.etf_not_available",
                        "Active fund (ETF not available within your criteria).",
                    )
                )

            explanations["per_fund"][isin] = reasons

            recs.append(
                {
                    "isin": isin,
                    "name": f.get("name"),
                    "allocation_percent": alloc,
                    "asset_class": f.get("asset_class"),
                    "asset_class_breakdown": f.get("asset_class_breakdown"),
                    "region_breakdown": f.get("region_breakdown"),
                    "benchmark_id": f.get("benchmark_id"),
                    "yearly_fee": f.get("yearly_fee", 0.0),
                    "provider": f.get("provider"),
                    "region": f.get("region"),
                    "theme": f.get("theme"),
                    "is_etf": f.get("is_etf"),
                    "esg_label": f.get("esg_label"),
                    "core_satellite_class": self._classify_core_satellite(f),
                    "etf_not_available": f.get("etf_not_available", False),
                    "rationale": " ".join(reasons[:2])
                    if reasons
                    else self._t(
                        language,
                        "decision.reason.default",
                        "Aligned with your preferences.",
                    ),
                    "explanations": reasons,
                }
            )

        # Fix rounding to sum 100
        total = sum(r["allocation_percent"] for r in recs)
        diff = int(round(100 - total))
        if recs and abs(diff) > 0:
            recs[0]["allocation_percent"] = recs[0]["allocation_percent"] + diff

        return recs, explanations

    def _compute_portfolio_metrics(
        self, recommendations: List[Dict[str, Any]], risk_profile: str
    ) -> Dict[str, Any]:
        if not recommendations:
            return {}

        weighted_fee = 0.0
        fee_weight_sum = 0.0  # weight of funds that actually have a fee value
        total_weight = 0.0
        region_exposure: Dict[str, float] = {}
        theme_exposure: Dict[str, float] = {}
        etf_share = 0.0

        for r in recommendations:
            w = (r.get("allocation_percent", 0.0) or 0.0) / 100.0
            total_weight += w
            if r.get("yearly_fee") is not None:
                weighted_fee += w * float(r["yearly_fee"])
                fee_weight_sum += w

            region = r.get("region") or "unknown"
            theme = r.get("theme") or "none"
            region_exposure[region] = region_exposure.get(region, 0.0) + w
            theme_exposure[theme] = theme_exposure.get(theme, 0.0) + w

            if r.get("is_etf"):
                etf_share += w

        if total_weight <= 0:
            total_weight = 1.0

        # None when no fund had a fee value; partial when only some funds did
        weighted_fee_result: Optional[float] = None
        if fee_weight_sum > 0:
            weighted_fee_result = round(weighted_fee, 3)

        # Approximate SRRI proxy from risk profile
        srri_proxy = {"DEFENSIVE": 3, "BALANCED": 4, "OPPORTUNITY": 6}.get(
            risk_profile, 4
        )

        return {
            "risk_profile": risk_profile,
            "srri_proxy": srri_proxy,
            "weighted_fee": weighted_fee_result,
            "region_exposures": {k: round(v, 3) for k, v in region_exposure.items()},
            "theme_exposures": {k: round(v, 3) for k, v in theme_exposure.items()},
            "etf_share": round(etf_share, 3),
        }

    def _build_summary(
        self,
        user_answers: Dict[str, Any],
        risk_profile: str,
        metrics: Dict[str, Any],
        trace: Dict[str, Any],
        language: Optional[str] = None,
    ) -> str:
        risk_profile_label = self._t(
            language,
            f"decision.risk_profile.{risk_profile.lower()}",
            risk_profile,
        )
        parts = [
            self._t(
                language,
                "decision.summary.risk_profile",
                "Risk profile: {risk_profile}.",
            ).format(risk_profile=risk_profile_label),
        ]
        weighted_fee = metrics.get("weighted_fee")
        if weighted_fee is not None:
            parts.append(
                self._t(
                    language,
                    "decision.summary.weighted_fee",
                    "Weighted fee estimate: {weighted_fee}%.",
                ).format(weighted_fee=weighted_fee)
            )
        esg_pref = user_answers.get("esg_preference")
        if esg_pref == "ART_8_9_ONLY":
            parts.append(
                self._t(
                    language,
                    "decision.summary.esg",
                    "Sustainability filter applied (SFDR Article 8/9 only).",
                )
            )
        elif esg_pref == "PREFER_ESG":
            parts.append(
                self._t(
                    language,
                    "decision.summary.esg_preferred",
                    "Sustainable funds weighted higher.",
                )
            )
        if user_answers.get("etf_preference") == "etf_only":
            parts.append(
                self._t(
                    language,
                    "decision.summary.etf_only",
                    "ETF-only filter applied.",
                )
            )
        preferred_regions = set(user_answers.get("preferred_regions") or [])
        if preferred_regions:
            match_pct = self._match_percent(
                metrics.get("region_exposures", {}), preferred_regions
            )
            if match_pct is None:
                parts.append(
                    self._t(
                        language,
                        "decision.summary.region",
                        "Regional preferences considered.",
                    )
                )
            else:
                pct = self._format_percent(match_pct)
                if match_pct <= 0:
                    parts.append(
                        self._t(
                            language,
                            "decision.summary.region_none",
                            "Regional preferences considered, but no matching funds were available ({percent}%).",
                        ).format(percent=pct)
                    )
                else:
                    parts.append(
                        self._t(
                            language,
                            "decision.summary.region_match",
                            "Regional preferences matched {percent}% of allocation.",
                        ).format(percent=pct)
                    )

        preferred_themes = set(user_answers.get("preferred_themes") or [])
        if preferred_themes and "none" not in preferred_themes:
            match_pct = self._match_percent(
                metrics.get("theme_exposures", {}), preferred_themes
            )
            if match_pct is None:
                parts.append(
                    self._t(
                        language,
                        "decision.summary.theme",
                        "Thematic preferences considered.",
                    )
                )
            else:
                pct = self._format_percent(match_pct)
                if match_pct <= 0:
                    parts.append(
                        self._t(
                            language,
                            "decision.summary.theme_none",
                            "Thematic preferences considered, but no matching funds were available ({percent}%).",
                        ).format(percent=pct)
                    )
                else:
                    parts.append(
                        self._t(
                            language,
                            "decision.summary.theme_match",
                            "Thematic preferences matched {percent}% of allocation.",
                        ).format(percent=pct)
                    )
        if trace.get("used_fallback_risk"):
            parts.append(
                self._t(
                    language,
                    "decision.summary.fallback",
                    "Risk profile fallback applied.",
                )
            )
        if trace.get("relaxations"):
            parts.append(
                self._t(
                    language,
                    "decision.summary.relaxed",
                    "Risk filters were relaxed to ensure enough eligible funds.",
                )
            )
        return " ".join(parts)

    @staticmethod
    def _match_percent(exposures: Dict[str, float], preferred: set) -> Optional[float]:
        if not exposures or not preferred:
            return None
        total = 0.0
        match = 0.0
        preferred_norm = {str(p).lower() for p in preferred}
        for key, value in exposures.items():
            try:
                weight = float(value)
            except (TypeError, ValueError):
                continue
            total += weight
            if str(key).lower() in preferred_norm:
                match += weight
        if total <= 0:
            return None
        return round(match * 100, 1)

    @staticmethod
    def _format_percent(value: float) -> str:
        return str(int(value)) if float(value).is_integer() else f"{value:.1f}"

    def _load_translations(self) -> Dict[str, Dict[str, str]]:
        base_dir = os.path.join(os.path.dirname(__file__), "translations")
        translations: Dict[str, Dict[str, str]] = {}
        if not os.path.isdir(base_dir):
            return translations
        for filename in os.listdir(base_dir):
            if not filename.endswith(".json"):
                continue
            lang = filename[:-5]
            path = os.path.join(base_dir, filename)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    translations[lang] = json.load(f)
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Failed to load decision translations %s: %s", path, e)
        return translations

    def _t(self, language: Optional[str], key: str, fallback: str) -> str:
        if not language:
            return fallback
        short = str(language).lower().split("-")[0]
        lang_map = self._translations.get(short) or self._translations.get("en")
        if not lang_map:
            return fallback
        return lang_map.get(key, fallback)
