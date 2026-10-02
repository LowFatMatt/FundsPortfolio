"""Layer-0 product-context tests: catalog, predicates, engine filter,
questionnaire overlay, API surface and the compass-CSV importer.

Decisions this suite pins down (2026-10-01):
  * 14 canonical product keys; compound CSV column families expand to
    individual keys sharing the column's validity.
  * STRICT boolean: only a plain ``ja`` (whitespace/case-normalised) is
    valid — ``ja (SW)``, ``Ablaufm. T93``, ``Einstiegsm.``, ``nein (alte
    WSF)`` are NOT valid (but are reported by the importer).
  * Full sync: CSV is the master list — CSV-only funds become stubs, DB
    funds absent from the CSV keep no ``valid_for`` (dropped under any
    product context, present when no context is set).
  * No product context (None/absent) → passthrough, backward compatible.
"""

import csv
import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from funds_portfolio.portfolio.decision_engine import DecisionEngine
from funds_portfolio.portfolio.eligibility import (
    PRODUCTS,
    PRODUCT_COLUMNS,
    filter_by_product,
    normalise_product,
    product_eligible,
)


# ---------------------------------------------------------------------------
# Catalog & predicates
# ---------------------------------------------------------------------------


def test_catalog_has_14_canonical_keys():
    assert len(PRODUCTS) == 14
    assert len(PRODUCT_COLUMNS) == 9  # CSV columns L–T
    for headline, keys in PRODUCT_COLUMNS:
        for key in keys:
            assert key in PRODUCTS
            assert PRODUCTS[key]["column"] == headline


def test_catalog_uses_basisflexgarant_not_baraflexgarant():
    assert "basisflexgarant" in PRODUCTS
    assert "baraflexgarant" not in PRODUCTS
    assert normalise_product("BasisFlexGarant") == "basisflexgarant"


def test_compound_columns_expand_to_families():
    garant_family = PRODUCT_COLUMNS[4][1]
    assert garant_family == (
        "garantrentevario",
        "flexgarant",
        "firmengarantrente",
        "firmenflexgarant",
    )
    assert PRODUCT_COLUMNS[5][1] == ("basisgarantrente", "basisflexgarant")
    assert PRODUCT_COLUMNS[6][1] == ("fondsrentevario", "starterkids")


def test_normalise_product_accepts_aliases():
    assert normalise_product("AVG80") == "avg80"
    assert normalise_product(" GarantRenteVario ") == "garantrentevario"
    assert normalise_product("1LTF") == "1ltf"
    assert normalise_product(
        "GARANTRENTEVARIO / FLEXGARANT / FIRMENGARANTRENTE / FIRMENFLEXGARANT"
    ) == "garantrentevario"
    assert normalise_product(None) is None
    assert normalise_product("") is None
    assert normalise_product("bogus") is None


def test_product_eligible_strict_membership():
    fund = {"isin": "X", "valid_for": ["avg80"]}
    assert product_eligible(fund, "avg80")
    assert product_eligible(fund, "AVG80")  # alias normalized
    assert product_eligible(fund, None)  # no context → passthrough
    assert not product_eligible(fund, "avg100")
    assert not product_eligible({}, "avg80")  # funds without valid_for drop out
    assert product_eligible({}, None)  # ...but only under a context
    assert len(filter_by_product([fund, {}, {"valid_for": []}], "avg80")) == 1


# ---------------------------------------------------------------------------
# Engine layer-0
# ---------------------------------------------------------------------------


def _fund(isin, name, **overrides):
    f = {
        "isin": isin,
        "name": name,
        "srri": 4,
        "yearly_fee": 0.2,
        "is_etf": True,
        "esg_label": None,
        "region": "global",
        "theme": "none",
        "provider": "p",
        "asset_class": "equity",
        "sharpe_ratio": 1.0,
        "volatility": 10.0,
        "max_drawdown": 12.0,
    }
    f.update(overrides)
    return f


def _answers(**overrides):
    a = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
        "preferred_regions": [],
        "preferred_themes": ["none"],
    }
    a.update(overrides)
    return a


def _product_filters(trace):
    return [f for f in trace["filters"] if f["name"] == "product_context"]


def test_engine_layer0_no_context_passthrough():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [_fund("A", "A"), _fund("B", "B")]
    result = engine.recommend(_answers(), funds)
    entry = _product_filters(result["decision_trace"])
    assert len(entry) == 1
    assert entry[0]["before"] == 2 and entry[0]["after"] == 2
    assert entry[0]["details"]["product"] is None


def test_engine_layer0_filters_by_product():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [
        _fund("A", "A", valid_for=["avg80"]),
        _fund("B", "B", valid_for=["avg100"]),
        _fund("C", "C"),  # no valid_for → dropped under a context
    ]
    result = engine.recommend(_answers(product_context="avg80"), funds)
    entry = _product_filters(result["decision_trace"])
    assert entry[0]["before"] == 3 and entry[0]["after"] == 1
    assert entry[0]["details"]["product"] == "avg80"
    recs = result["recommendations"]
    assert recs and all(r["isin"] == "A" for r in recs)


def test_engine_layer0_alias_normalized_in_answers():
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    funds = [_fund("A", "A", valid_for=["starterkids"])]
    result = engine.recommend(_answers(product_context="StarterKids"), funds)
    entry = _product_filters(result["decision_trace"])
    assert entry[0]["details"]["product"] == "starterkids"
    assert result["recommendations"]


def test_engine_layer0_reduces_before_required_fields():
    """Layer-0 runs first: a fund failing BOTH product and required-fields
    is attributed to the product filter (its before/after counts move)."""
    engine = DecisionEngine(min_candidates=1, top_k=5, final_fund_count=1)
    broken = _fund("B", "B", valid_for=["avg100"])
    del broken["sharpe_ratio"]  # required-fields candidate
    funds = [_fund("A", "A", valid_for=["avg80"]), broken]
    result = engine.recommend(_answers(product_context="avg80"), funds)
    filters = {f["name"]: f for f in result["decision_trace"]["filters"]}
    assert filters["product_context"]["before"] == 2
    assert filters["product_context"]["after"] == 1
    assert filters["required_fields"]["before"] == 1
    assert filters["required_fields"]["after"] == 1


# ---------------------------------------------------------------------------
# Questionnaire loader overlay
# ---------------------------------------------------------------------------


def test_questionnaire_overlay_reduces_counts_and_keeps_cache(tmp_path, monkeypatch):
    """The product overlay decorates a copy; the cached product-less
    questionnaire and its counts stay untouched."""
    from funds_portfolio.questionnaire.loader import QuestionnaireLoader

    db = {
        "funds_database": [
            _fund("A", "Fund A", region="europe", valid_for=["avg80"]),
            _fund("B", "Fund B", region="europe", valid_for=["avg80"]),
            _fund("C", "Fund C", region="asia"),
        ]
    }
    db_path = tmp_path / "funds_database.json"
    db_path.write_text(json.dumps(db), encoding="utf-8")

    loader = QuestionnaireLoader.__new__(QuestionnaireLoader)
    loader._funds_db_path = str(db_path)
    loader._funds_mtime = None
    loader._translations = {}
    loader._questionnaire = {
        "sections": [
            {"id": "preferred_regions", "options": []},
            {"id": "preferred_themes", "options": []},
        ]
    }
    loader._apply_dynamic_options()

    q_plain = loader.get_questionnaire()
    q_product = loader.get_questionnaire(product="avg80")

    assert q_product["product_context"] == "avg80"
    assert "product_context" not in q_plain

    def region_counts(q):
        sec = next(s for s in q["sections"] if s["id"] == "preferred_regions")
        return {o["value"]: o["fund_count"] for o in sec["options"]}

    plain, product = region_counts(q_plain), region_counts(q_product)
    assert plain["europe"] == 2 and plain["asia"] == 1
    assert product["europe"] == 2 and product["asia"] == 0

    # cache untouched by the overlay call
    assert "product_context" not in loader.get_questionnaire()


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch):
    # No CUSTOMER override: the product-validity import targets the root
    # catalog (funds_database.json per data_sources.yaml); the customer
    # copies (e.g. data/customers/general) are re-build follow-ups and
    # carry no valid_for yet — under a product context they would filter
    # everything out.
    monkeypatch.delenv("CUSTOMER", raising=False)
    from funds_portfolio.data.providers import reset_provider
    from funds_portfolio.data.fund_manager import reset_fund_manager

    reset_provider()
    reset_fund_manager()
    from funds_portfolio.app import create_app

    app = create_app()
    app.config["TESTING"] = True
    yield app.test_client()
    reset_provider()
    reset_fund_manager()


def test_products_endpoint_returns_catalog(client):
    resp = client.get("/api/products")
    assert resp.status_code == 200
    products = resp.get_json()["products"]
    keys = [p["key"] for p in products]
    assert len(keys) == 14
    assert "basisflexgarant" in keys


def test_questionnaire_with_product_param(client):
    ok = client.get("/api/questionnaire?product=avg80")
    assert ok.status_code == 200
    assert ok.get_json().get("product_context") == "avg80"

    bad = client.get("/api/questionnaire?product=nope")
    assert bad.status_code == 400
    assert "valid_products" in bad.get_json()


@patch("funds_portfolio.data.price_fetcher.yf.Ticker")
def test_portfolio_post_product_flow(mock_ticker, client):
    mock_instance = MagicMock()
    mock_instance.history.return_value = MagicMock(empty=True)
    mock_ticker.return_value = mock_instance

    answers = {
        "risk_approach": "moderate",
        "esg_preference": "NONE",
        "etf_preference": "no_preference",
    }

    # back-compat: no product → no product_context key injected as filter-off
    r0 = client.post("/api/portfolio", json={"user_answers": dict(answers)})
    assert r0.status_code == 201
    trace0 = {
        f["name"]: f for f in r0.get_json()["decision_trace"]["filters"]
    }
    assert trace0["product_context"]["details"]["product"] is None

    # alias accepted, normalized, persisted
    r1 = client.post(
        "/api/portfolio", json={"user_answers": dict(answers), "product": "AVG80"}
    )
    assert r1.status_code == 201
    body = r1.get_json()
    assert body["user_answers"]["product_context"] == "avg80"
    trace1 = {f["name"]: f for f in body["decision_trace"]["filters"]}
    assert trace1["product_context"]["after"] <= trace1["product_context"]["before"]
    assert trace1["product_context"]["after"] < trace0["product_context"]["after"]

    # unknown product → 400 with the allowed enum
    r2 = client.post(
        "/api/portfolio", json={"user_answers": dict(answers), "product": "nope"}
    )
    assert r2.status_code == 400
    assert "valid_products" in r2.get_json()


# ---------------------------------------------------------------------------
# Importer (scripts/import_product_validity.py)
# ---------------------------------------------------------------------------


def _csv_row(name, isin, validity_cells, cost="1,00%", esg="Art. 8", kvg="Deka"):
    """Build a 26-column compass CSV row; validity_cells covers L–T."""
    row = [""] * 26
    row[0] = "Aktienfonds"
    row[3] = name
    row[4] = isin
    row[5] = cost
    row[8] = esg
    row[10] = kvg
    for i, cell in enumerate(validity_cells):
        row[11 + i] = cell
    row[25] = "TICKER.F"
    return row


# L–T column defaults: all "nein"
def _validity(**overrides):
    cells = ["nein"] * 9
    for idx, value in overrides.items():
        cells[int(idx)] = value
    return cells


@pytest.fixture
def mini_db(tmp_path):
    db = {
        "funds_database": [
            _fund("DE000AAA00001", "Match By Isin", valid_for=["stale"]),
            _fund("LU000BBB00002", "Paren Isin Fund"),
            _fund("LU000CCC00003", "Remap Candidate"),
            _fund("DE000DDD00004", "Absent From Csv"),
        ]
    }
    path = tmp_path / "funds_database.json"
    path.write_text(json.dumps(db), encoding="utf-8")
    return path


@pytest.fixture
def mini_csv(tmp_path):
    rows = [
        # header (26 columns; duplicate "Region" as in the real file)
        [
            "Assetklasse",
            "Themen / Assets",
            "Region",
            "Name",
            "ISIN",
            "Kosten",
            "Performance-fee",
            "Währung",
            "Nachhaltigkeit",
            "Publikumsfonds",
            "KVG",
            "STANDARDDEPOT",
            "AVI",
            "AVG80",
            "AVG100",
            "GARANTRENTEVARIO / FLEXGARANT / FIRMENGARANTRENTE / FIRMENFLEXGARANT",
            "BASISGARANTRENTE / BASISFLEXGARANT",
            "FONDSRENTEVARIO / STARTERKIDS",
            "1LF",
            "1LTF",
            "Fondsart",
            "Region",
            "Thema",
            "Fondsmanagement",
            "Link",
            "Ticker",
        ],
        # plain ja on compound columns expands to the full family
        _csv_row(
            "Match By Isin",
            "DE000AAA00001",
            # idx 2 = AVG80, idx 4 = GARANT-family compound, idx 5 = BASIS-family
            _validity(**{"2": "ja", "4": "ja ", "5": "ja"}),
        ),
        # strict rule: conditional yeses are NOT valid
        _csv_row(
            "Paren Isin Fund",
            "(LU000BBB00002)",
            _validity(**{"4": "ja (SW)", "6": "Ablaufm. T93"}),
        ),
        # different ISIN, same name → name-match remap (DB ISIN kept)
        _csv_row(
            "Remap Candidate",
            "IE000CCC00009",
            _validity(**{"7": "ja"}),
        ),
        # CSV-only fund → stub (with model annotation on 1LF, excluded)
        _csv_row(
            "Brand New Fund",
            "FR000EEE00005",
            _validity(**{"3": "ja", "7": "Einstiegsm."}),
        ),
    ]
    path = tmp_path / "compass.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        csv.writer(f, delimiter=";").writerows(rows)
    return path


def _run_importer(db_path, csv_path, **kwargs):
    from scripts.import_product_validity import import_product_validity

    return import_product_validity(str(db_path), str(csv_path), **kwargs)


def _load(db_path):
    with open(db_path, encoding="utf-8") as f:
        return json.load(f)["funds_database"]


def test_importer_strict_ja_and_compound_expansion(mini_db, mini_csv, capsys):
    _run_importer(mini_db, mini_csv)
    funds = {f["name"]: f for f in _load(mini_db)}

    matched = funds["Match By Isin"]
    assert set(matched["valid_for"]) == {
        "avg80",
        "garantrentevario",
        "flexgarant",
        "firmengarantrente",
        "firmenflexgarant",
        "basisgarantrente",
        "basisflexgarant",
    }  # trailing-space "ja " still counts; "stale" overwritten (full sync)


def test_importer_conditional_annotations_excluded_and_reported(
    mini_db, mini_csv, capsys
):
    _run_importer(mini_db, mini_csv)
    funds = {f["name"]: f for f in _load(mini_db)}

    # paren ISIN normalized + strict rule → nothing valid
    paren = funds["Paren Isin Fund"]
    assert paren["valid_for"] == []

    out = capsys.readouterr().out
    assert "ja (SW)" in out
    assert "Ablaufm. T93" in out
    assert "IE000CCC00009" in out  # remap candidate surfaced


def test_importer_name_remap_keeps_db_isin(mini_db, mini_csv):
    _run_importer(mini_db, mini_csv)
    funds = {f["name"]: f for f in _load(mini_db)}
    remap = funds["Remap Candidate"]
    assert remap["isin"] == "LU000CCC00003"  # DB ISIN kept
    assert set(remap["valid_for"]) == {"1lf"}  # idx 7 = 1LF


def test_importer_stub_creation(mini_db, mini_csv):
    _run_importer(mini_db, mini_csv)
    stub = next(f for f in _load(mini_db) if f["name"] == "Brand New Fund")
    assert stub["source"] == "csv_20260928"
    assert stub["yearly_fee"] == 1.0
    assert stub["esg_label"] == "SFDR_ARTICLE_8"
    assert set(stub["valid_for"]) == {"avg100"}  # Einstiegsm. excluded


def test_importer_flags_absent_and_optional_removal(mini_db, mini_csv):
    _run_importer(mini_db, mini_csv)
    names = [f["name"] for f in _load(mini_db)]
    assert "Absent From Csv" in names  # report-only by default

    _run_importer(mini_db, mini_csv, remove_absent=True)
    names = [f["name"] for f in _load(mini_db)]
    assert "Absent From Csv" not in names


def test_importer_dry_run_writes_nothing(mini_db, mini_csv):
    before = mini_db.read_text(encoding="utf-8")
    _run_importer(mini_db, mini_csv, dry_run=True)
    assert mini_db.read_text(encoding="utf-8") == before


def test_importer_skip_stubs_match_only(mini_db, mini_csv, capsys):
    """Match-only mode for customer catalogs: no stubs, but valid_for is set."""
    _run_importer(mini_db, mini_csv, skip_stubs=True)
    funds = {f["name"]: f for f in _load(mini_db)}
    # CSV-only fund NOT added — customer universe stays closed
    assert "Brand New Fund" not in funds
    assert len(funds) == 4
    # matched funds still receive their valid_for (AVG80 + both families)
    assert funds["Match By Isin"]["valid_for"] == [
        "avg80",
        "garantrentevario",
        "flexgarant",
        "firmengarantrente",
        "firmenflexgarant",
        "basisgarantrente",
        "basisflexgarant",
    ]
    # report lists the skipped stubs
    out = capsys.readouterr().out
    assert "Stubs skipped (match-only mode --skip-stubs): 1" in out


# ---------------------------------------------------------------------------
# Customer-catalog builder (scripts/build_customer_catalog.py)
# ---------------------------------------------------------------------------


def _tsv_row(isin="LU1111111111", name="Customer Fund"):
    return {
        "name": name,
        "isin": isin,
        "asset_class_de": "Aktienfonds",
        "ytd_return": None,
        "five_y_return": None,
        "sri": 3,
        "ter_pct": 1.5,
    }


def test_build_record_valid_for_from_general_profile():
    from scripts.build_customer_catalog import build_record

    gp = {"LU1111111111": {"provider": "Deka", "valid_for": ["avg80"]}}
    rec = build_record(_tsv_row(), gp, None, {})
    assert rec["valid_for"] == ["avg80"]


def test_build_record_valid_for_falls_back_to_root_catalog():
    from scripts.build_customer_catalog import build_record

    root = {"LU1111111111": {"valid_for": ["1lf"]}}
    rec = build_record(_tsv_row(), {}, None, root)
    assert rec["valid_for"] == ["1lf"]


def test_build_record_valid_for_passthrough_when_unknown():
    from scripts.build_customer_catalog import build_record

    rec = build_record(_tsv_row(), {}, None, {})
    assert rec["valid_for"] is None
