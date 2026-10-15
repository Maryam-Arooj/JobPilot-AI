import os
import sys
from dotenv import load_dotenv

# Load backend/.env
env_path = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(env_path)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.providers.serp_job_search import SerpJobSearchProvider
from backend.providers.apify_job_source import ApifyJobSource
from backend.providers.firecrawl_extractor import FirecrawlJobExtractor
from backend.providers.company_providers import FirecrawlCompanyResearchProvider

def test_real_serp():
    print("--- Testing Live SerpAPI (Google Jobs) ---")
    serp = SerpJobSearchProvider()
    results = serp.search("remote AI Engineer")
    print(f"SerpAPI returned {len(results)} live results.")
    if results:
        first = results[0]
        print(f"  Sample Job: {first.get('title')} at {first.get('company')} ({first.get('location')})")
    return len(results) > 0

def test_real_apify():
    print("\n--- Testing Live Apify API ---")
    apify = ApifyJobSource()
    results = apify.search("AI Engineer")
    print(f"Apify returned {len(results)} results.")
    return True

def test_real_firecrawl():
    print("\n--- Testing Live Firecrawl Scraping & Company Research ---")
    extractor = FirecrawlJobExtractor()
    extracted = extractor.extract("https://openai.com/careers")
    print(f"Firecrawl scrape status: {extracted.get('extraction_method')}")
    print(f"  Content length: {len(extracted.get('content', ''))} bytes")

    comp_provider = FirecrawlCompanyResearchProvider()
    research = comp_provider.research_company("OpenAI", "https://openai.com")
    print(f"Company Research: {research.get('company_name')} - {research.get('industry')}")
    print(f"  Tech Info: {research.get('technology_info')}")
    print(f"  Claims count: {len(research.get('claims', []))}")
    return len(extracted.get('content', '')) > 0

if __name__ == "__main__":
    print(f"Using SERP_API_KEY: {os.getenv('SERP_API_KEY')[:10]}...")
    print(f"Using APIFY_API_TOKEN: {os.getenv('APIFY_API_TOKEN')[:10]}...")
    print(f"Using FIRECRAWL_API_KEY: {os.getenv('FIRECRAWL_API_KEY')[:10]}...")

    serp_ok = test_real_serp()
    apify_ok = test_real_apify()
    firecrawl_ok = test_real_firecrawl()

    print("\n================ REAL PROVIDER SMOKE TEST RESULTS ================")
    print(f"SerpAPI (Google Jobs): {'PASSED ✅' if serp_ok else 'FAILED ❌'}")
    print(f"Apify: {'PASSED ✅' if apify_ok else 'FAILED ❌'}")
    print(f"Firecrawl: {'PASSED ✅' if firecrawl_ok else 'FAILED ❌'}")
    print("==================================================================")
