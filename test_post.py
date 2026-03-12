import requests

payload = {
    "user_answers": {"risk_approach": "moderate"},
    "portfolio_id": "port_20260312_TEST_ID"
}
response = requests.post("http://localhost:5000/api/portfolio", json=payload)
print(response.json().get('portfolio_id'))
