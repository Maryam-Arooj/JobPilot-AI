import os
import requests
from dotenv import load_dotenv

load_dotenv("backend/.env")
apify_token = os.getenv("APIFY_API_TOKEN")

print("Searching Apify store for job scrapers...")
resp = requests.get(f"https://api.apify.com/v2/store?search=jobs&token={apify_token}", timeout=15)
print("Store HTTP Status:", resp.status_code)
if resp.status_code == 200:
    items = resp.json().get("data", {}).get("items", [])
    print(f"Found {len(items)} job scraper actors on Apify store:")
    for item in items[:5]:
        print(f"  - ID: {item.get('id')} | Name: {item.get('name')} | Username: {item.get('username')}")

# Test running top actor
if items:
    actor = items[0]
    actor_identifier = f"{actor.get('username')}~{actor.get('name')}"
    print(f"\nTesting run with actor: {actor_identifier}")
    run_url = f"https://api.apify.com/v2/acts/{actor_identifier}/runs?token={apify_token}"
    r_run = requests.post(run_url, json={"queries": ["AI Engineer"]}, timeout=15)
    print(f"Actor run status: {r_run.status_code}")
    if r_run.status_code in (200, 201):
        print("Actor run launched successfully!")
