import json

from funds_portfolio.scrapers.finanzen import FinanzenNetScraper


def test_finanzen_scraper_extracts_expected_fields():
    html = """
    <html>
      <body>
        <div>Laufende Kosten 1,80%</div>
        <div>Volatilität 3 Jahre: 7,15%</div>
        <div>Max. Drawdown 10,55%</div>
        <div>Sharpe Ratio 5 Jahre: 0,13</div>
        <div>SRRI 3</div>
        <div>SFDR Artikel 8</div>
        <div>ETF</div>
        <img src="https://c.finanzen.net/chart.aspx?labels=Aktien;Anleihen;Barmittel&values=60,0;30,0;10,0" />
      </body>
    </html>
    """
    scraper = FinanzenNetScraper()
    result = scraper.extract_all(html, "https://www.finanzen.net/fonds/DE000A0X7541")

    assert result["yearly_fee"] == 1.8
    assert result["volatility"] == 7.15
    assert result["max_drawdown"] == 10.55
    assert result["sharpe_ratio"] == 0.13
    assert result["srri"] == 3
    assert result["is_etf"] is True
    assert result["esg_label"] == "SFDR_ARTICLE_8"
    assert result["esg_article_8"] is True
    assert result["asset_class_breakdown_raw"] == {
        "Aktien": 60.0,
        "Anleihen": 30.0,
        "Barmittel": 10.0,
    }
    assert result["asset_class_breakdown_translated"] == {
        "equity": 60.0,
        "bond": 30.0,
        "cash": 10.0,
    }


def test_finanzen_scraper_returns_empty_when_no_chart():
    html = "<html><body><div>Some fund page without chart data.</div></body></html>"
    scraper = FinanzenNetScraper()
    result = scraper.extract_all(html, "https://www.finanzen.net/fonds/DE000A0X7541")

    assert result.get("asset_class_breakdown_raw") is None
    assert result.get("asset_class_breakdown_translated") is None
