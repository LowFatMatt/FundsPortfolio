"""Flask application entry point"""

import os
import logging
from flask import Flask, jsonify, render_template, render_template_string


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

    # Home page
    @app.route("/")
    def index():
        # Try to render the template; fall back if missing
        tpl_path = os.path.join(app.template_folder, "index.html")
        if os.path.exists(tpl_path):
            return render_template("index.html")
        logging.warning(
            "index.html template not found at %s, returning fallback HTML", tpl_path
        )
        return render_template_string(
            "<!doctype html><html><head><title>FundsPortfolio</title></head>"
            "<body><h1>FundsPortfolio API</h1><p>Template missing.</p></body></html>"
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
        return jsonify(ql.get_questionnaire()), 200

    # Portfolio endpoints
    @app.route("/api/portfolio", methods=["POST"])
    def create_portfolio():
        data = request.get_json()
        if not data or "user_answers" not in data:
            return jsonify({"error": "Missing user_answers"}), 400

        user_answers = data["user_answers"]

        # 1. Validate answers
        valid, errors = ql.validate_answers(user_answers)
        if not valid:
            return jsonify({"error": "Validation failed", "details": errors}), 400

        # 2. Get funds
        funds = fm.get_all_funds()

        # 3. Recommend
        result = decision_engine.recommend(user_answers, funds)
        recommendations = result.get("recommendations", [])
        if not recommendations:
            return jsonify(
                {
                    "error": "No eligible funds after filtering",
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

    # log template folder for debugging
    logging.getLogger("werkzeug").setLevel(logging.INFO)
    app.logger.info("template folder = %s", app.template_folder)
    return app


# Create app instance for gunicorn
app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
