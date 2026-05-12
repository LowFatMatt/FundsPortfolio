"""Flask application entry point"""

import os
import logging
import json
from datetime import datetime, timezone
from flask import (
    Flask,
    jsonify,
    render_template,
    render_template_string,
    send_from_directory,
)

APP_STARTED_AT = datetime.now(timezone.utc)
logger = logging.getLogger(__name__)


def _format_build_time(raw_time: str | None) -> str:
    if raw_time:
        return raw_time
    return APP_STARTED_AT.strftime("%Y-%m-%d %H:%M:%S UTC")


def _build_brand_css_vars(config: dict) -> dict:
    colors = config.get("colors", {})
    fonts = config.get("fonts", {})
    radii = config.get("radii", {})
    spacing = config.get("spacing", {})
    effects = config.get("effects", {})

    return {
        "--bg-color": colors.get("bg", "#0d1117"),
        "--card-bg": colors.get("card", "rgba(22, 27, 34, 0.65)"),
        "--card-border": colors.get("card_border", "rgba(48, 54, 61, 0.5)"),
        "--text-primary": colors.get("text_primary", "#f0f6fc"),
        "--text-secondary": colors.get("text_secondary", "#8b949e"),
        "--accent": colors.get("accent", "#58a6ff"),
        "--accent-hover": colors.get("accent_hover", "#1f6feb"),
        "--success": colors.get("success", "#2ea043"),
        "--error": colors.get("error", "#f85149"),
        "--input-bg": colors.get("input_bg", "rgba(13, 17, 23, 0.8)"),
        "--input-border": colors.get("input_border", "rgba(48, 54, 61, 0.5)"),
        "--surface-muted": colors.get("surface_muted", "rgba(48, 54, 61, 0.5)"),
        "--bg-accent-1": colors.get("bg_accent_1", "rgba(88, 166, 255, 0.08)"),
        "--bg-accent-2": colors.get("bg_accent_2", "rgba(46, 160, 67, 0.05)"),
        "--banner-info-bg": colors.get("banner_info_bg", "rgba(88, 166, 255, 0.1)"),
        "--banner-info-border": colors.get(
            "banner_info_border", "rgba(88, 166, 255, 0.3)"
        ),
        "--banner-info-text": colors.get("banner_info_text", "#58a6ff"),
        "--banner-success-bg": colors.get(
            "banner_success_bg", "rgba(46, 160, 67, 0.1)"
        ),
        "--banner-success-border": colors.get(
            "banner_success_border", "rgba(46, 160, 67, 0.3)"
        ),
        "--banner-success-text": colors.get("banner_success_text", "#3fb950"),
        "--banner-warning-bg": colors.get(
            "banner_warning_bg", "rgba(248, 81, 73, 0.1)"
        ),
        "--banner-warning-border": colors.get(
            "banner_warning_border", "rgba(248, 81, 73, 0.4)"
        ),
        "--banner-warning-text": colors.get("banner_warning_text", "#ff7b72"),
        "--font-body": fonts.get(
            "body", "'Inter', system-ui, -apple-system, sans-serif"
        ),
        "--font-heading": fonts.get(
            "heading",
            fonts.get("body", "'Inter', system-ui, -apple-system, sans-serif"),
        ),
        "--radius-card": radii.get("card", "16px"),
        "--radius-button": radii.get("button", "8px"),
        "--radius-input": radii.get("input", "8px"),
        "--radius-pill": radii.get("pill", "999px"),
        "--page-padding": spacing.get("page_padding", "2rem 1rem"),
        "--card-padding": spacing.get("card_padding", "2rem"),
        "--glass-blur": effects.get("glass_blur", "blur(12px)"),
        "--card-shadow": effects.get("card_shadow", "0 8px 32px rgba(0, 0, 0, 0.2)"),
        "--button-shadow": effects.get(
            "button_shadow", "0 4px 12px rgba(88, 166, 255, 0.3)"
        ),
        "--button-shadow-hover": effects.get(
            "button_shadow_hover", "0 6px 16px rgba(88, 166, 255, 0.4)"
        ),
    }


def _load_brand(base_dir: str) -> dict:
    brand_root = os.path.join(base_dir, "brand")
    requested = os.getenv("BRAND", "default")
    default_dir = os.path.join(brand_root, "default")
    brand_dir = os.path.join(brand_root, requested)
    if not os.path.isdir(brand_dir):
        logger.warning("Brand '%s' not found. Falling back to default.", requested)
        requested = "default"
        brand_dir = default_dir

    config_path = os.path.join(brand_dir, "brand.json")
    config = {}
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Failed to load brand config %s: %s", config_path, exc)

    brand_name = config.get("name", requested)
    logo_file = config.get("logo", "logo.svg")
    overrides_file = config.get("overrides_css", "overrides.css")
    font_import_url = config.get("font_import_url")

    logo_path = os.path.join(brand_dir, logo_file)
    overrides_path = os.path.join(brand_dir, overrides_file)

    return {
        "name": brand_name,
        "slug": requested,
        "dir": brand_dir,
        "font_import_url": font_import_url,
        "logo": logo_file if os.path.exists(logo_path) else None,
        "overrides_css": overrides_file if os.path.exists(overrides_path) else None,
        "css_vars": _build_brand_css_vars(config),
    }


def create_app():
    """Create and configure Flask app"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    app = Flask(
        __name__,
        template_folder="/app/templates"
        if os.path.exists("/app/templates")
        else os.path.join(base_dir, "templates"),
        static_folder="/app/static"
        if os.path.exists("/app/static")
        else os.path.join(base_dir, "static"),
    )

    brand = _load_brand(base_dir)
    brand_css_vars = "; ".join(
        f"{key}: {value}" for key, value in brand.get("css_vars", {}).items()
    )
    brand_logo_url = f"/brand/{brand['logo']}" if brand.get("logo") else None
    brand_overrides_url = (
        f"/brand/{brand['overrides_css']}" if brand.get("overrides_css") else None
    )

    @app.route("/brand/<path:filename>")
    def brand_asset(filename: str):
        return send_from_directory(brand["dir"], filename)

    # Home page
    @app.route("/")
    def index():
        # Try to render the template; fall back if missing
        tpl_path = os.path.join(app.template_folder, "index.html")
        build_id = os.getenv("BUILD_ID", "local-dev")
        build_time = _format_build_time(os.getenv("BUILD_TIME"))
        if os.path.exists(tpl_path):
            return render_template(
                "index.html",
                build_id=build_id,
                build_time=build_time,
                brand_name=brand.get("name"),
                brand_css_vars=brand_css_vars,
                brand_logo_url=brand_logo_url,
                brand_overrides_url=brand_overrides_url,
                brand_font_url=brand.get("font_import_url"),
            )
        logging.warning(
            "index.html template not found at %s, returning fallback HTML", tpl_path
        )
        return render_template_string(
            "<!doctype html><html><head><title>FundsPortfolio</title></head>"
            "<body><h1>FundsPortfolio API</h1>"
            f"<p>Build: {build_id} • Started: {build_time}</p>"
            "<p>Template missing.</p></body></html>"
        )

    # Health check endpoint
    @app.route("/health")
    def health():
        return jsonify({"status": "ok"}), 200

    from funds_portfolio.questionnaire.loader import get_questionnaire_loader
    from funds_portfolio.data.fund_manager import get_fund_manager
    from funds_portfolio.portfolio.validator import PortfolioValidator
    from funds_portfolio.portfolio.decision_engine import DecisionEngine
    from funds_portfolio.models.portfolio import Portfolio
    from flask import request

    # Initialize singletons
    ql = get_questionnaire_loader()
    fm = get_fund_manager()

    # Init calculation engine components
    decision_engine = DecisionEngine()

    # Questionnaire endpoint
    @app.route("/api/questionnaire", methods=["GET"])
    def get_questionnaire():
        lang = request.args.get("lang")
        if not lang:
            accept_lang = request.headers.get("Accept-Language", "")
            if accept_lang:
                lang = accept_lang.split(",")[0].strip().split("-")[0]
        return jsonify(ql.get_questionnaire(language=lang)), 200

    # Portfolio endpoints
    @app.route("/api/portfolio", methods=["POST"])
    def create_portfolio():
        data = request.get_json()
        if not data or "user_answers" not in data:
            return jsonify({"error": "Missing user_answers"}), 400

        user_answers = data["user_answers"]
        lang = data.get("language") or data.get("lang")
        if not lang:
            accept_lang = request.headers.get("Accept-Language", "")
            if accept_lang:
                lang = accept_lang.split(",")[0].strip().split("-")[0]

        # 1. Validate answers
        valid, errors = ql.validate_answers(user_answers)
        if not valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        # 2. Get funds
        funds = fm.get_all_funds()

        # 3. Recommend
        result = decision_engine.recommend(user_answers, funds, language=lang)
        recommendations = result.get("recommendations", [])
        if not recommendations:
            error_summary = (
                result.get("explanations", {}).get("summary")
                or "No eligible funds after filtering"
            )
            return jsonify(
                {
                    "error": error_summary,
                    "decision_trace": result.get("decision_trace", {}),
                }
            ), 422

        # 4. Validate output
        validator = PortfolioValidator(min_funds=min(5, len(recommendations)))
        is_valid, val_errors = validator.validate_recommendations(recommendations)
        if not is_valid:
            return jsonify(
                {"error": "Failed to generate valid portfolio", "details": val_errors}
            ), 422

        # Create Model
        portfolio_id = data.get("portfolio_id")
        portfolio = Portfolio(user_answers=user_answers, portfolio_id=portfolio_id)
        portfolio.set_recommendations(recommendations)
        portfolio.set_calculated_metrics(result.get("portfolio_metrics", {}))
        portfolio.set_portfolio_metrics(result.get("portfolio_metrics", {}))
        portfolio.set_risk_profile(result.get("risk_profile"))
        portfolio.set_explanations(result.get("explanations", {}))
        portfolio.set_decision_trace(result.get("decision_trace", {}))

        if result.get("decision_trace", {}).get("used_fallback_risk"):
            portfolio.add_log(
                "Warning: Could not strongly determine your exact "
                "risk profile from the provided answers. "
                "The engine defaulted to a Balanced risk profile."
            )

        # Save to disk
        base_dir = (
            "/app/portfolios"
            if os.path.exists("/app/portfolios")
            and os.access("/app/portfolios", os.W_OK)
            else os.path.join(os.getcwd(), "portfolios")
        )
        port_file = os.path.join(base_dir, f"{portfolio.portfolio_id}.json")
        try:
            os.makedirs(base_dir, exist_ok=True)
            with open(port_file, "w") as f:
                f.write(portfolio.to_json())
        except PermissionError:
            app.logger.warning(
                "Could not write portfolio to %s due to permissions. "
                "Using /tmp instead.",
                base_dir,
            )
            import tempfile

            base_dir = os.path.join(tempfile.gettempdir(), "portfolios")
            port_file = os.path.join(base_dir, f"{portfolio.portfolio_id}.json")
            os.makedirs(base_dir, exist_ok=True)
            with open(port_file, "w") as f:
                f.write(portfolio.to_json())

        return jsonify(portfolio.to_dict()), 201

    @app.route("/api/portfolio/<portfolio_id>", methods=["GET"])
    def get_portfolio(portfolio_id):
        base_dir = (
            "/app/portfolios"
            if os.path.exists("/app/portfolios")
            and os.access("/app/portfolios", os.R_OK)
            else os.path.join(os.getcwd(), "portfolios")
        )
        port_file = os.path.join(base_dir, f"{portfolio_id}.json")
        if not os.path.exists(port_file):
            return jsonify({"error": "Portfolio not found"}), 404

        with open(port_file, "r") as f:
            data = f.read()
        return data, 200, {"Content-Type": "application/json"}

    @app.route("/api/funds", methods=["GET"])
    def get_funds():
        funds = fm.get_all_funds()
        return jsonify({"funds": funds, "count": len(funds)}), 200

    # ---- Phase 2: fund time-series & breakdowns ----
    from funds_portfolio.config.stress_periods import list_stress_periods
    from funds_portfolio.portfolio.aggregator import (
        aggregate_portfolio_nav,
        aggregate_breakdowns,
    )

    def _portfolio_dir_candidates() -> list:
        import tempfile
        return [
            "/app/portfolios",
            os.path.join(os.getcwd(), "portfolios"),
            os.path.join(tempfile.gettempdir(), "portfolios"),
        ]

    def _load_portfolio(portfolio_id: str):
        for base in _portfolio_dir_candidates():
            port_file = os.path.join(base, f"{portfolio_id}.json")
            if os.path.exists(port_file) and os.access(port_file, os.R_OK):
                with open(port_file, "r", encoding="utf-8") as f:
                    return json.load(f)
        return None

    @app.route("/api/funds/<isin>/performance", methods=["GET"])
    def get_fund_performance(isin: str):
        ts = fm.get_fund_timeseries(isin)
        if not ts:
            return jsonify({"error": "No performance data for ISIN", "isin": isin}), 404
        return jsonify({
            "isin": isin.upper(),
            "as_of": ts.get("as_of"),
            "currency": ts.get("currency"),
            "performance": ts.get("performance") or {},
        }), 200

    @app.route("/api/funds/<isin>/risk", methods=["GET"])
    def get_fund_risk(isin: str):
        ts = fm.get_fund_timeseries(isin)
        if not ts:
            return jsonify({"error": "No risk data for ISIN", "isin": isin}), 404
        return jsonify({
            "isin": isin.upper(),
            "as_of": ts.get("as_of"),
            "volatility": ts.get("volatility") or {},
            "risk_metrics": ts.get("risk_metrics") or {},
        }), 200

    @app.route("/api/funds/<isin>/breakdown", methods=["GET"])
    def get_fund_breakdown(isin: str):
        meta = fm.get_fund_by_isin(isin)
        if not meta:
            return jsonify({"error": "Fund not found", "isin": isin}), 404
        ts = fm.get_fund_timeseries(isin) or {}
        return jsonify({
            "isin": isin.upper(),
            "asset_class": meta.get("asset_class"),
            "region": meta.get("region"),
            "asset_class_breakdown": meta.get("asset_class_breakdown"),
            "region_breakdown": meta.get("region_breakdown"),
            "top_holdings": ts.get("top_holdings"),
            "as_of": ts.get("as_of"),
        }), 200

    @app.route("/api/portfolio/<portfolio_id>/performance", methods=["GET"])
    def get_portfolio_performance(portfolio_id: str):
        portfolio = _load_portfolio(portfolio_id)
        if portfolio is None:
            return jsonify({"error": "Portfolio not found"}), 404
        recommendations = portfolio.get("recommendations") or []
        start = request.args.get("from")
        end = request.args.get("to")

        weighted_series = []
        for rec in recommendations:
            isin = rec.get("isin")
            weight = (rec.get("allocation_percent") or 0.0) / 100.0
            if not isin or weight <= 0:
                continue
            ts = fm.get_fund_timeseries(isin) or {}
            nav_series = ((ts.get("performance") or {}).get("nav_series")) or []
            weighted_series.append({"isin": isin, "weight": weight, "nav_series": nav_series})

        # Pick benchmark by dominant asset_class in the portfolio
        breakdown = aggregate_breakdowns(recommendations)
        dominant_class = max(
            (breakdown.get("asset_class") or {}).items(),
            key=lambda kv: kv[1],
            default=("equity", 0.0),
        )[0]
        benchmarks_cfg = fm.list_benchmarks()
        defaults = benchmarks_cfg.get("default_by_asset_class") or {}
        bench_id = defaults.get(dominant_class) or defaults.get("equity")
        bench = fm.get_benchmark(bench_id) if bench_id else None
        bench_nav = (bench or {}).get("nav_series") or []

        agg = aggregate_portfolio_nav(weighted_series, bench_nav, start=start, end=end)
        agg["benchmark"] = {"id": bench_id, "name": (bench or {}).get("name")} if bench_id else None
        agg["portfolio_id"] = portfolio_id
        return jsonify(agg), 200

    @app.route("/api/portfolio/<portfolio_id>/breakdown", methods=["GET"])
    def get_portfolio_breakdown(portfolio_id: str):
        portfolio = _load_portfolio(portfolio_id)
        if portfolio is None:
            return jsonify({"error": "Portfolio not found"}), 404
        recommendations = portfolio.get("recommendations") or []
        return jsonify({
            "portfolio_id": portfolio_id,
            "breakdown": aggregate_breakdowns(recommendations),
        }), 200

    @app.route("/api/config/stress-periods", methods=["GET"])
    def get_stress_periods():
        return jsonify({"stress_periods": list_stress_periods()}), 200

    @app.route("/api/config/benchmarks", methods=["GET"])
    def get_benchmarks():
        cfg = fm.list_benchmarks()
        # Don't ship raw nav_series in the catalog endpoint — keep response small.
        catalog = {
            bid: {k: v for k, v in (entry or {}).items() if k != "nav_series"}
            for bid, entry in (cfg.get("benchmarks") or {}).items()
        }
        return jsonify({
            "benchmarks": catalog,
            "default_by_asset_class": cfg.get("default_by_asset_class") or {},
        }), 200

    @app.route("/api/data/health", methods=["GET"])
    def data_health():
        return jsonify(fm.health()), 200

    # log template folder for debugging
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    app.logger.info("template folder = %s", app.template_folder)
    return app


# Create app instance for gunicorn
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
