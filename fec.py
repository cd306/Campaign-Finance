import os
import requests
from typing import Optional

BASE_URL = "https://api.open.fec.gov/v1"


def _get(endpoint: str, params: dict) -> dict:
    params["api_key"] = os.getenv("FEC_API_KEY", "DEMO_KEY")
    response = requests.get(f"{BASE_URL}{endpoint}", params=params)
    if response.status_code == 429:
        return {"error": "FEC API rate limit hit. Sign up for a free API key at https://api.data.gov/signup/ and add it as FEC_API_KEY in .env"}
    response.raise_for_status()
    return response.json()


def search_candidate(name: str, state: Optional[str] = None, office: Optional[str] = None):
    params = {"q": name, "per_page": 10, "sort": "-receipts"}
    if state:
        params["state"] = state.upper()
    if office:
        params["office"] = office[0].upper()  # H, S, or P

    data = _get("/candidates/search/", params)
    if "error" in data:
        return data

    results = []
    for c in data.get("results", []):
        results.append({
            "candidate_id": c.get("candidate_id"),
            "name": c.get("name"),
            "office": c.get("office_full"),
            "state": c.get("state"),
            "district": c.get("district"),
            "party": c.get("party_full"),
            "committees": [
                {"id": pc.get("committee_id"), "name": pc.get("name")}
                for pc in c.get("principal_committees", [])
            ],
        })
    return results


def get_employer_breakdown(committee_id: str, cycle: int, limit: int = 30) -> list[dict]:
    params = {
        "committee_id": committee_id,
        "cycle": cycle,
        "per_page": limit,
        "sort": "-total",
    }
    data = _get("/schedules/schedule_a/by_employer/", params)
    return [
        {
            "employer": r.get("employer") or "Unknown",
            "total": r.get("total"),
            "count": r.get("count"),
        }
        for r in data.get("results", [])
    ]


def get_contributions(
    committee_id: str,
    cycle: int,
    min_amount: Optional[float] = None,
    employer: Optional[str] = None,
    limit: int = 50,
) -> list[dict]:
    params = {
        "committee_id": committee_id,
        "two_year_transaction_period": cycle,
        "per_page": limit,
        "sort": "-contribution_receipt_amount",
    }
    if min_amount is not None:
        params["min_amount"] = min_amount
    if employer:
        params["contributor_employer"] = employer

    data = _get("/schedules/schedule_a/", params)
    return [
        {
            "contributor_name": r.get("contributor_name"),
            "employer": r.get("contributor_employer"),
            "occupation": r.get("contributor_occupation"),
            "amount": r.get("contribution_receipt_amount"),
            "date": r.get("contribution_receipt_date"),
            "city": r.get("contributor_city"),
            "state": r.get("contributor_state"),
            "entity_type": r.get("entity_type_desc"),
        }
        for r in data.get("results", [])
    ]


def get_large_contributions(committee_id: str, cycle: int, threshold: float = 5000) -> list[dict]:
    return get_contributions(committee_id, cycle, min_amount=threshold)
