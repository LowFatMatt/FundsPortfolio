import argparse
import json

import requests

from funds_portfolio.scrapers import get_scraper_for_url


def main():
    parser = argparse.ArgumentParser(
        description="Validate a fund scraper by fetching a provider URL and printing extracted KIID metadata."
    )
    parser.add_argument("--url", required=True, help="Provider page URL to scrape")
    parser.add_argument(
        "--timeout",
        type=int,
        default=15,
        help="Request timeout in seconds (default: 15)",
    )
    args = parser.parse_args()

    scraper = get_scraper_for_url(args.url)
    if not scraper:
        raise SystemExit(f"No scraper available for URL: {args.url}")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FundsPortfolio/1.0; +https://github.com)"
    }
    response = requests.get(args.url, headers=headers, timeout=args.timeout)
    response.raise_for_status()

    result = scraper.extract_all(response.text, args.url)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
