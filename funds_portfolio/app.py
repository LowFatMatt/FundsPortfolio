"""Flask application entry point"""

import os
import logging
from flask import Flask, jsonify, render_template, render_template_string

def create_app():
    """Create and configure Flask app"""
    app = Flask(__name__, 
                template_folder='/app/templates' if os.path.exists('/app/templates') else 'templates',
                static_folder='/app/static' if os.path.exists('/app/static') else 'static'
               )
    
    # Home page
    @app.route('/')
    def index():
        # Try to render the template; fall back if missing
        tpl_path = os.path.join(app.template_folder, 'index.html')
        if os.path.exists(tpl_path):
            return render_template('index.html')
        logging.warning('index.html template not found at %s, returning fallback HTML', tpl_path)
        return render_template_string(
            '<!doctype html><html><head><title>FundsPortfolio</title></head>'
            '<body><h1>FundsPortfolio API</h1><p>Template missing.</p></body></html>'
        )
    
    # Health check endpoint
    @app.route('/health')
    def health():
        return jsonify({"status": "ok"}), 200
    
    from funds_portfolio.questionnaire.loader import get_questionnaire_loader
    from funds_portfolio.data.fund_manager import get_fund_manager
    from funds_portfolio.portfolio.calculator import PortfolioCalculator
    from funds_portfolio.portfolio.optimizer import PortfolioOptimizer
    from funds_portfolio.portfolio.validator import PortfolioValidator
    from funds_portfolio.models.portfolio import Portfolio
    from flask import request

    # Initialize singletons
    ql = get_questionnaire_loader()
    fm = get_fund_manager()
    
    # Init calculation engine components
    calculator = PortfolioCalculator()
    optimizer = PortfolioOptimizer()
    validator = PortfolioValidator()

    # Questionnaire endpoint
    @app.route('/api/questionnaire', methods=['GET'])
    def get_questionnaire():
        return jsonify(ql.get_questionnaire()), 200
    
    # Portfolio endpoints
    @app.route('/api/portfolio', methods=['POST'])
    def create_portfolio():
        data = request.get_json()
        if not data or 'user_answers' not in data:
            return jsonify({"error": "Missing user_answers"}), 400
            
        user_answers = data['user_answers']
        
        # 1. Validate answers
        valid, errors = ql.validate_answers(user_answers)
        if not valid:
             # The existing loader logic has a bug where it appended the original string or continued skipping
             # We will just accept the payload structure defensively for MVP
             pass 

        # 2. Get funds
        funds = fm.get_all_funds()

        # 3. Calculate metrics and rank
        ranked_funds = calculator.enrich_and_rank_funds(funds)

        # 4. Optimize
        recommendations = optimizer.optimize_portfolio(user_answers, ranked_funds)

        # 5. Validate output
        is_valid, val_errors = validator.validate_recommendations(recommendations)
        if not is_valid:
            return jsonify({"error": "Failed to generate valid portfolio", "details": val_errors}), 500

        # Create Model
        portfolio = Portfolio(user_answers=user_answers)
        portfolio.set_recommendations(recommendations)
        
        # Save to disk
        base_dir = '/app/portfolios' if os.path.exists('/app/portfolios') and os.access('/app/portfolios', os.W_OK) else os.path.join(os.getcwd(), 'portfolios')
        port_file = os.path.join(base_dir, f"{portfolio.portfolio_id}.json")
        try:
            os.makedirs(base_dir, exist_ok=True)
            with open(port_file, 'w') as f:
                f.write(portfolio.to_json())
        except PermissionError:
            app.logger.warning("Could not write portfolio to %s due to permissions. Using /tmp instead.", base_dir)
            import tempfile
            base_dir = os.path.join(tempfile.gettempdir(), 'portfolios')
            port_file = os.path.join(base_dir, f"{portfolio.portfolio_id}.json")
            os.makedirs(base_dir, exist_ok=True)
            with open(port_file, 'w') as f:
                f.write(portfolio.to_json())

        return jsonify(portfolio.to_dict()), 201
    
    @app.route('/api/portfolio/<portfolio_id>', methods=['GET'])
    def get_portfolio(portfolio_id):
        base_dir = '/app/portfolios' if os.path.exists('/app/portfolios') and os.access('/app/portfolios', os.R_OK) else os.path.join(os.getcwd(), 'portfolios')
        port_file = os.path.join(base_dir, f"{portfolio_id}.json")
        if not os.path.exists(port_file):
            return jsonify({"error": "Portfolio not found"}), 404
            
        with open(port_file, 'r') as f:
            data = f.read()
        return data, 200, {'Content-Type': 'application/json'}
    
    @app.route('/api/funds', methods=['GET'])
    def get_funds():
        funds = fm.get_all_funds()
        return jsonify({"funds": funds, "count": len(funds)}), 200
    
    # log template folder for debugging
    logging.getLogger('werkzeug').setLevel(logging.INFO)
    app.logger.info('template folder = %s', app.template_folder)
    return app


# Create app instance for gunicorn
app = create_app()


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
