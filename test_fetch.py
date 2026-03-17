from funds_portfolio.data.price_fetcher import PriceFetcher

pf = PriceFetcher()
print("CSPX.AS:", pf.get_fund_metrics("CSPX.AS"))
print("VWCE.DE:", pf.get_fund_metrics("VWCE.DE"))
