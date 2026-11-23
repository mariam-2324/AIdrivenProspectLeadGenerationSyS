"""Pipeline: collect -> extract (LLM) -> analyze -> export."""
import argparse
import os

from dotenv import load_dotenv

load_dotenv()

from sources import (load_sample, fetch_hackernews, fetch_from_rest_api,
                     find_website_osm, fetch_website_text)
from extractor import extract, pick_provider
from analytics import build_dataframe, summary


def business_listing(name, url=None, focus=None):
    """Business ka naam -> website link (OSM) -> website text -> listing."""
    url = url or find_website_osm(name)
    if not url:
        raise SystemExit(f"'{name}' ki website OpenStreetMap par nahi mili. "
                         f"Link khud dein: --url https://...")
    print(f"[info] Website: {url}")
    return [{"id": 1, "source": f"website:{url}", "company": name,
             "text": fetch_website_text(url), "focus": focus}]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", choices=["sample", "hn", "api"], default="sample")
    p.add_argument("--query", default="looking for developer", help="--source hn ke liye")
    p.add_argument("--limit", type=int, default=20)
    p.add_argument("--business", help='Business ka naam, jaise "Daraz"')
    p.add_argument("--url", help="Website ka link (agar OSM par na mile)")
    p.add_argument("--focus", help='Kis cheez par dhyan do, jaise "website text/copy quality"')
    p.add_argument("--offline", action="store_true", help="LLM ke baghair keyword rules")
    args = p.parse_args()

    provider = "offline" if args.offline else pick_provider()
    print(f"[info] LLM provider: {provider}")

    if args.business or args.url:
        listings = business_listing(args.business or args.url, args.url, args.focus)
    elif args.source == "sample":
        listings = load_sample()
    elif args.source == "hn":
        listings = fetch_hackernews(args.query, args.limit)
    else:
        listings = fetch_from_rest_api()
    if not listings:
        print("Koi listing nahi mili - query badal kar dekhein.")
        return

    results = [extract(l, provider) for l in listings]
    df = build_dataframe(listings, results)
    summary(df)

    if args.business or args.url:  # ek business ki poori detail dikhana
        r = results[0]
        print("\n--- Detail ---")
        print("Requirement :", r["requirement"] or "-")
        print("Industry    :", r["industry"])
        print("Signals     :", ", ".join(r["buying_signals"]) or "-")
        print("Website gaps:", ", ".join(r["website_gaps"]) or "-")
        print("Outreach    :", r["outreach_angle"])

    os.makedirs("output", exist_ok=True)
    df.to_csv("output/qualified_leads.csv", index=False)
    print("\nSaved: output/qualified_leads.csv")


if __name__ == "__main__":
    main()