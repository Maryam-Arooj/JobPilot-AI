"""Clean job locations: 'Khānewāl, Punjab, Pakistan' -> city Khanewal, region Punjab, country Pakistan.
Only rewrites what the provider gave; never invents a city."""
import re
import unicodedata
from typing import Dict, Optional

PK_CITIES = {
    "lahore": "Punjab", "faisalabad": "Punjab", "rawalpindi": "Punjab", "multan": "Punjab", "gujranwala": "Punjab",
    "sialkot": "Punjab", "bahawalpur": "Punjab", "sargodha": "Punjab", "sahiwal": "Punjab", "sheikhupura": "Punjab",
    "jhang": "Punjab", "rahim yar khan": "Punjab", "gujrat": "Punjab", "kasur": "Punjab", "okara": "Punjab",
    "khanewal": "Punjab", "dera ghazi khan": "Punjab", "wah cantt": "Punjab", "chiniot": "Punjab", "jhelum": "Punjab",
    "karachi": "Sindh", "hyderabad, sindh": "Sindh", "sukkur": "Sindh", "larkana": "Sindh", "nawabshah": "Sindh",
    "mirpur khas": "Sindh", "peshawar": "Khyber Pakhtunkhwa", "mardan": "Khyber Pakhtunkhwa",
    "abbottabad": "Khyber Pakhtunkhwa", "swat": "Khyber Pakhtunkhwa", "mingora": "Khyber Pakhtunkhwa",
    "kohat": "Khyber Pakhtunkhwa", "quetta": "Balochistan", "gwadar": "Balochistan",
    "islamabad": "Islamabad Capital Territory", "gilgit": "Gilgit-Baltistan", "muzaffarabad": "Azad Kashmir",
    "mirpur": "Azad Kashmir",
}
PK_REGIONS = {"punjab": "Punjab", "sindh": "Sindh", "khyber pakhtunkhwa": "Khyber Pakhtunkhwa", "kpk": "Khyber Pakhtunkhwa",
              "balochistan": "Balochistan", "islamabad capital territory": "Islamabad Capital Territory",
              "gilgit-baltistan": "Gilgit-Baltistan", "azad kashmir": "Azad Kashmir"}
COUNTRIES = {
    "pakistan": "Pakistan", "united states": "United States", "usa": "United States", "united states of america": "United States",
    "united kingdom": "United Kingdom", "uk": "United Kingdom", "england": "United Kingdom", "scotland": "United Kingdom",
    "wales": "United Kingdom", "canada": "Canada", "united arab emirates": "United Arab Emirates", "uae": "United Arab Emirates",
    "germany": "Germany", "deutschland": "Germany", "saudi arabia": "Saudi Arabia", "qatar": "Qatar", "india": "India",
    "australia": "Australia", "ireland": "Ireland", "netherlands": "Netherlands", "france": "France", "spain": "Spain",
    "singapore": "Singapore", "hong kong": "Hong Kong", "hong kong sar": "Hong Kong", "peru": "Peru", "tunisia": "Tunisia",
    "poland": "Poland", "portugal": "Portugal", "italy": "Italy", "sweden": "Sweden", "switzerland": "Switzerland",
    "egypt": "Egypt", "turkey": "Turkey", "malaysia": "Malaysia", "philippines": "Philippines", "brazil": "Brazil",
    "mexico": "Mexico", "kuwait": "Kuwait", "oman": "Oman", "bahrain": "Bahrain", "bangladesh": "Bangladesh",
}
CITY_COUNTRY = {"dubai": "United Arab Emirates", "abu dhabi": "United Arab Emirates", "sharjah": "United Arab Emirates",
                "riyadh": "Saudi Arabia", "jeddah": "Saudi Arabia", "doha": "Qatar", "london": "United Kingdom",
                "manchester": "United Kingdom", "toronto": "Canada", "vancouver": "Canada", "montreal": "Canada",
                "berlin": "Germany", "munich": "Germany", "frankfurt": "Germany", "bengaluru": "India", "bangalore": "India",
                "new york": "United States", "san francisco": "United States", "seattle": "United States", "austin": "United States"}
US_STATES = set("AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH "
                "OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split())
US_STATE_NAMES = {"california", "texas", "new york", "florida", "washington", "nevada", "illinois", "virginia",
                  "massachusetts", "georgia", "colorado", "north carolina", "new jersey", "arizona", "oregon", "ohio", "michigan"}
CA_PROVINCES = {"ontario", "quebec", "british columbia", "alberta", "manitoba", "nova scotia", "saskatchewan",
                "on", "qc", "bc", "ab"}
REMOTE_WORDS = ("anywhere", "remote", "worldwide", "work from home")


def _ascii(text: str) -> str:
    return unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()


def _title(part: str) -> str:
    return part if part.isupper() and len(part) <= 3 else " ".join(w if w.isupper() else w.capitalize() for w in part.split())


def parse_location(raw: Optional[str], country_hint: Optional[str] = None) -> Dict[str, str]:
    text = re.sub(r"\s+", " ", _ascii(raw or "")).strip(" ,-·")
    text = re.sub(r"\((?:remote|on-?site|hybrid)\)", "", text, flags=re.I).strip(" ,")
    low = text.lower()
    out = {"city": "", "region": "", "country": "", "display": text, "remote": any(w in low for w in REMOTE_WORDS)}
    text = re.sub(r"\b(division|district|city|metropolitan area)\b(?=,|$)", "", text, flags=re.I)
    text = re.sub(r"\s+,", ",", re.sub(r"\s{2,}", " ", text)).strip(" ,")
    parts = [p.strip() for p in re.split(r",|\s[-–|]\s", text) if p.strip()]
    lparts = [p.lower() for p in parts]

    country = ""
    for p in reversed(lparts):
        if p in COUNTRIES:
            country = COUNTRIES[p]; break
    if not country:
        if parts and re.fullmatch(r"[A-Z]{2}", parts[-1]) and parts[-1] in US_STATES:
            country = "United States"
        elif any(p in US_STATE_NAMES for p in lparts) or low.endswith(" metropolitan area") and "montreal" not in low and "toronto" not in low:
            country = "United States" if any(p in US_STATE_NAMES for p in lparts) else ""
        if not country and any(p in CA_PROVINCES for p in lparts[1:]):
            country = "Canada"
        if not country and any(p in PK_REGIONS for p in lparts):
            country = "Pakistan"
        if not country:
            for p in lparts:
                if p in PK_CITIES or p.replace(" cantt", "") in PK_CITIES:
                    country = "Pakistan"; break
                if p in CITY_COUNTRY:
                    country = CITY_COUNTRY[p]; break
            if not country:
                for city, c in CITY_COUNTRY.items():
                    if city in low:
                        country = c; break
    if not country:
        for name, c in COUNTRIES.items():
            if len(name) > 3 and re.search(r"\b" + re.escape(name) + r"\b", low):
                country = c; break
    if not country and country_hint:
        country = COUNTRIES.get(country_hint.strip().lower(), "")

    if country == "Pakistan":
        city = next((parts[i] for i, p in enumerate(lparts) if p in PK_CITIES), "")
        region = next((PK_REGIONS[p] for p in lparts if p in PK_REGIONS), "") or (PK_CITIES.get(city.lower(), "") if city else "")
        if not city:
            city = next((parts[i] for i, p in enumerate(lparts)
                         if p not in PK_REGIONS and p != "pakistan" and not any(w in p for w in REMOTE_WORDS)), "")
        out.update(city=_title(city), region=region, country="Pakistan")
        out["display"] = ", ".join(x for x in [_title(city), region, "Pakistan"] if x) if (city or region) else "Pakistan"
        if out["remote"]:
            out["display"] = f"Remote ({out['display']})"
        return out
    if country:
        out["country"] = country
        if parts:
            out["city"] = _title(parts[0]) if lparts[0] not in COUNTRIES else ""
    if out["remote"] and not country:
        out["display"] = "Remote (anywhere)"
    elif text:
        out["display"] = ", ".join(_title(p) if p.islower() else p for p in parts)
    return out


def country_of(raw: Optional[str], stored: Optional[str] = None) -> str:
    p = parse_location(raw, stored)
    if p["country"]:
        return p["country"]
    return "Remote Worldwide" if p["remote"] else "Global / Unspecified"
