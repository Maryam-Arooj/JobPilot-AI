import os
import json
import requests
from dotenv import load_dotenv

load_dotenv("backend/.env")

serp_key = os.getenv("SERP_API_KEY")
apify_token = os.getenv("APIFY_API_TOKEN")
firecrawl_key = os.getenv("FIRECRAWL_API_KEY")

print(f"SERP Key: {serp_key[:10]}...")
print(f"Apify Token: {apify_token[:10]}...")
print(f"Firecrawl Key: {firecrawl_key[:10]}...")

# 1. Test SERP
print("\n--- Testing SERP ---")
serp_url = f"https://serpapi.com/search?engine=google_jobs&q=AI+Engineer&api_key={serp_key}"
r_serp = requests.get(serp_url, timeout=15)
print(f"SERP HTTP Status: {r_serp.status_code}")
try:
    serp_json = r_serp.json()
    print("SERP Keys in output:", list(serp_json.keys()))
    jobs = serp_json.get("jobs_results", [])
    print(f"SERP jobs count: {len(jobs)}")
    if jobs:
        print("First SERP job title:", jobs[0].get("title"), "| Company:", jobs[0].get("company_name"))
    elif "error" in serp_json:
        print("SERP Error Message:", serp_json.get("error"))
except Exception as e:
    print("SERP JSON parse error:", e)

# 2. Test Apify
print("\n--- Testing Apify ---")
# Testing with tilde ~ format for Apify actor: apify~linkedin-jobs-scraper or apify~google-jobs-scraper
apify_url = "https://api.apify.com/v2/acts/apify~google-jobs-scraper/run-sync-get-dataset-items"
headers = {"Authorization": f"Bearer {apify_token}"}
r_apify = requests.post(apify_url, json={"queries": "AI Engineer"}, headers=headers, timeout=25)
print(f"Apify HTTP Status: {r_apify.status_code}")
try:
    apify_json = r_apify.json()
    if isinstance(apify_json, list):
        print(f"Apify returned list of {len(apify_json)} items.")
        if apify_json:
            print("First Apify item:", apify_json[0].get("title") or apify_json[0].get("positionName"))
    elif isinstance(apify_json, dict):
        print("Apify Dict output keys:", list(apify_json.keys()))
except Exception as e:
    print("Apify JSON parse error:", e)

# 3. Test Firecrawl
print("\n--- Testing Firecrawl ---")
fire_url = "https://api.firecrawl.dev/v1/scrape"
headers = {"Authorization": f"Bearer {firecrawl_key}"}
r_fire = requests.post(fire_url, json={"url": "https://openai.com/careers"}, headers=headers, timeout=25)
print(f"Firecrawl HTTP Status: {r_fire.status_code}")
try:
    fire_json = r_fire.json()
    print("Firecrawl success:", fire_json.get("success"))
    if fire_json.get("success"):
        data = fire_json.get("data", {})
        print("Extracted title:", data.get("metadata", {}).get("title"))
        print("Markdown length:", len(data.get("markdown", "")))
except Exception as e:
    print("Firecrawl JSON parse error:", e)
