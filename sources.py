"""Step 1: Data collection - live REST API se (aur sample se offline testing ke liye)."""
import html
import json
import os
import re
from pathlib import Path

import requests

HN_URL = "https://hn.algolia.com/api/v1/search_by_date"


def _clean(text):
    """HTML tags hata kar saaf text banata hai."""
    text = html.unescape(re.sub(r"<[^>]+>", " ", text or ""))
    return re.sub(r"\s+", " ", text).strip()


def load_sample(path=None):
    """Offline demo data (file ki apni jagah ke hisaab se dhoondta hai)."""
    path = path or Path(__file__).parent / "data" / "sample_listings.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def fetch_hackernews(query="looking for developer", limit=20):
    """
    LIVE data: Hacker News ki free public API (key ki zaroorat nahi).
    Har post ko hamare standard format {id, source, company, text} mein badalta hai.
    """
    resp = requests.get(
        HN_URL,
        params={"query": query, "tags": "story", "hitsPerPage": limit},
        timeout=20,
    )
    resp.raise_for_status()  # 4xx/5xx par error uthaye
    listings = []
    for hit in resp.json().get("hits", []):
        text = _clean(f"{hit.get('title', '')}. {hit.get('story_text', '')}")
        if len(text) < 20:
            continue
        listings.append({
            "id": hit["objectID"],
            "source": "hackernews",
            "company": hit.get("author", "unknown"),  # poster ka naam
            "text": text[:1500],                      # Claude ko lambi text bhejna mehenga hai
        })
    return listings


def fetch_website_text(url, max_chars=3000):
    """Kisi company ki apni website ka text lata hai (analysis ke liye)."""
    resp = requests.get(url, timeout=20, headers={"User-Agent": "Mozilla/5.0 (lead-research-bot)"})
    resp.raise_for_status()
    body = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", resp.text)
    return _clean(body)[:max_chars]


def fetch_from_rest_api(page=1):
    """Koi bhi apni authorized REST API (.env mein DIRECTORY_API_URL set karein)."""
    url = os.getenv("DIRECTORY_API_URL")
    if not url:
        raise ValueError("DIRECTORY_API_URL set nahi hai (.env check karein)")
    headers = {"Authorization": f"Bearer {os.getenv('DIRECTORY_API_KEY', '')}"}
    resp = requests.get(url, headers=headers, params={"page": page}, timeout=20)
    resp.raise_for_status()
    return resp.json()  # format: [{"id","source","company","text"}, ...]


def find_website_osm(business_name, city="Karachi"):
    """
    OpenStreetMap Nominatim (FREE, key nahi chahiye) se business ka naam dhoondh kar
    uski website ka link nikalta hai. Rules: User-Agent zaroori, 1 request/second se zyada nahi.
    Agar OSM par website darj na ho to None wapas aata hai.
    """
    resp = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": f"{business_name} {city}", "format": "jsonv2",
                "extratags": 1, "limit": 5, "countrycodes": "pk"},
        headers={"User-Agent": "lead-extraction-student-project/1.0"},
        timeout=20,
    )
    resp.raise_for_status()
    for place in resp.json():
        tags = place.get("extratags") or {}
        site = tags.get("website") or tags.get("contact:website") or tags.get("url")
        if site:
            return site if site.startswith("http") else "https://" + site
    return None
