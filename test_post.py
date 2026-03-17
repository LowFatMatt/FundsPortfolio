"""Manual integration script for posting to the running API.

This file is intentionally not a pytest test. Run it directly:
  python test_post.py
"""

import requests


def main() -> None:
    payload = {
        "user_answers": {"risk_approach": "moderate"},
        "portfolio_id": "port_20260312_TEST_ID",
    }
    response = requests.post("http://localhost:5000/api/portfolio", json=payload)
    response.raise_for_status()
    print(response.json().get("portfolio_id"))


if __name__ == "__main__":
    main()
