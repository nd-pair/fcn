#!/usr/bin/env python3
"""
OPTIONAL / MANUAL: Google Scholar version of the crawler.

Google Scholar has no API and serves a CAPTCHA to datacenter / CI traffic, so
this CANNOT run in GitHub Actions -- it is here for running by hand from a
residential connection. The automated pipeline uses crawl_openalex.py instead.

Usage:
    pip install scholarly
    python scripts/crawl_scholar.py     # writes data/scholar_profiles/<slug>.json

It is resumable: already-saved faculty are skipped, so if Scholar throttles you
just re-run it later and it continues.
"""
import json, os, re, time, random

from scholarly import scholarly

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "scholar_profiles")
os.makedirs(OUT, exist_ok=True)

# (display name, Scholar search query)
FACULTY = [
    ("Edgar Bolivar-Nieto", "Edgar Bolivar Notre Dame"),
    ("Tingyu Cheng", "Tingyu Cheng Notre Dame"),
    ("Nikolaus Correll", "Nikolaus Correll"),
    ("J. William Goodwine", "Bill Goodwine Notre Dame"),
    ("Mengxue Hou", "Mengxue Hou"),
    ("Hai Lin", "Hai Lin Notre Dame"),
    ("Margaret Coad", "Margaret Coad Notre Dame"),
    ("Yasemin Ozkan-Aydin", "Yasemin Ozkan-Aydin"),
    ("James Schmiedeler", "James Schmiedeler Notre Dame"),
    ("Patrick Wensing", "Patrick Wensing Notre Dame"),
    ("Zhi Zheng", "Zhi Zheng Notre Dame robotics"),
    ("Panos Antsaklis", "Panos Antsaklis Notre Dame"),
    ("Toros Arikan", "Toros Arikan"),
    ("Jane Cleland-Huang", "Jane Cleland-Huang Notre Dame"),
    ("Robert Landers", "Robert Landers Notre Dame"),
    ("Michael Lemmon", "Michael Lemmon Notre Dame"),
]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def fetch(name, query):
    author = next(scholarly.search_author(query), None)
    if author is None:
        return {"query_name": name, "not_found": True}
    author = scholarly.fill(author, sections=["basics", "indices", "publications"])
    works = []
    for p in author.get("publications", []):
        t = (p.get("bib", {}).get("title") or "").strip()
        if t:
            works.append({"title": t, "year": p.get("bib", {}).get("pub_year"),
                          "num_citations": p.get("num_citations", 0)})
    return {
        "query_name": name, "scholar_name": author.get("name"),
        "scholar_id": author.get("scholar_id"), "affiliation": author.get("affiliation"),
        "citedby": author.get("citedby"), "hindex": author.get("hindex"),
        "num_works_fetched": len(works), "works": works,
    }


def main():
    for name, query in FACULTY:
        path = os.path.join(OUT, f"{slug(name)}.json")
        if os.path.exists(path):
            print(f"[skip] {name}"); continue
        print(f"[fetch] {name}")
        try:
            data = fetch(name, query)
        except Exception as e:
            data = {"query_name": name, "error": str(e)}
        json.dump(data, open(path, "w"), indent=2)
        time.sleep(random.uniform(4, 8))


if __name__ == "__main__":
    main()
