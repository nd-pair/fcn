#!/usr/bin/env python3
"""
Crawl Robotics @ Notre Dame faculty publication data from OpenAlex.

The faculty roster is a curated list below (FACULTY). It is kept as canonical
names that resolve cleanly on OpenAlex -- the public people page shows informal
nicknames (e.g. "Pat Wensing", "Margaret McGuinness") that do not, so we do not
drive resolution from a live scrape. Update FACULTY when the roster changes.
For each faculty member we resolve an OpenAlex author id (preferring a Notre
Dame affiliation and a matching surname), then pull every work with co-authors.

Output: data/oa_profiles/<slug>.json  (one file per faculty)

Why OpenAlex rather than Google Scholar? Scholar has no API and serves a
CAPTCHA to automated/CI traffic, so it cannot run unattended in GitHub
Actions. OpenAlex is an open, crawlable scholarly graph with the same
co-authorship signal. (scripts/crawl_scholar.py keeps a Scholar version for
manual runs from a residential IP.)
"""
import json, os, re, sys, time, urllib.parse, urllib.request

MAILTO = os.environ.get("OPENALEX_MAILTO", "nd-pair@nd.edu")
ND = "https://openalex.org/I107639228"          # University of Notre Dame
API = "https://api.openalex.org"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "oa_profiles")
os.makedirs(OUT, exist_ok=True)

# Manual disambiguation for hard namesakes: display name -> OpenAlex author id.
OVERRIDES = {
    "zhi zheng": "A5065741205",     # ND HRI/assistive-robotics (not "Zheng Zhang")
}

# Curated roster (canonical names that resolve on OpenAlex). Source of truth:
# https://robotics.nd.edu/people/  -- edit this list when the roster changes.
FACULTY = [
    # Core faculty
    "Edgar Bolivar-Nieto", "Tingyu Cheng", "Nikolaus Correll", "Bill Goodwine",
    "Mengxue Hou", "Hai Lin", "Margaret Coad", "Yasemin Ozkan-Aydin",
    "James Schmiedeler", "Patrick Wensing", "Zhi Zheng",
    # Affiliated faculty
    "Panos Antsaklis", "Toros Arikan", "Jane Cleland-Huang",
    "Robert Landers", "Michael Lemmon",
]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def http_get(url, as_json=True):
    req = urllib.request.Request(url, headers={"User-Agent": f"nd-pair-crawler ({MAILTO})"})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode("utf-8", "replace")
    return json.loads(raw) if as_json else raw


def name_tokens(s):
    return [t for t in re.sub(r"[^a-z ]", " ", s.lower()).split() if len(t) > 1]


def surname(name):
    toks = name_tokens(name)
    return toks[-1] if toks else ""


def resolve_author(name):
    """Best OpenAlex author for a name: prefer ND affiliation + surname match."""
    over = OVERRIDES.get(name.lower())
    if over:
        a = http_get(f"{API}/authors/{over}?mailto={MAILTO}")
        return a
    sur = surname(name)
    q = urllib.parse.quote(name)
    tries = [
        f"{API}/authors?filter=affiliations.institution.id:{ND.split('/')[-1]}&search={q}&per-page=25&mailto={MAILTO}",
        f"{API}/authors?search={q}&per-page=25&mailto={MAILTO}",
    ]
    for url in tries:
        results = http_get(url).get("results", [])
        # keep only candidates whose surname matches the query surname
        matched = [a for a in results if sur and sur in name_tokens(a.get("display_name", ""))]
        pool = matched or results
        nd = [a for a in pool if any(i.get("id") == ND for i in (a.get("last_known_institutions") or []))
              or any((aff.get("institution") or {}).get("id") == ND for aff in a.get("affiliations", []))]
        cand = nd or pool
        if cand:
            return max(cand, key=lambda a: a.get("works_count", 0))
    return None


def fetch_works(author_id):
    works, cursor = [], "*"
    aid = author_id.rsplit("/", 1)[-1]
    while cursor:
        q = urllib.parse.urlencode({
            "filter": f"author.id:{aid}",
            "select": "id,title,publication_year,authorships",
            "per-page": 200, "cursor": cursor, "mailto": MAILTO,
        })
        data = http_get(f"{API}/works?{q}")
        for w in data.get("results", []):
            coauthors = [{"id": (a.get("author") or {}).get("id"),
                          "name": (a.get("author") or {}).get("display_name")}
                         for a in w.get("authorships", []) if (a.get("author") or {}).get("id")]
            works.append({"id": w["id"], "title": w.get("title"),
                          "year": w.get("publication_year"), "coauthors": coauthors})
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.25)
    return works


def main():
    print(f"[roster] {len(FACULTY)} faculty")
    json.dump(FACULTY, open(os.path.join(ROOT, "data", "faculty.json"), "w"), indent=2)

    current_slugs = set()
    for name in FACULTY:
        s = slug(name)
        current_slugs.add(s)
        path = os.path.join(OUT, f"{s}.json")
        print(f"[resolve] {name}")
        try:
            author = resolve_author(name)
            if not author:
                json.dump({"query_name": name, "not_found": True}, open(path, "w"), indent=2)
                print("   -- not found"); continue
            insts = author.get("last_known_institutions") or [{}]
            print(f"   -> {author['display_name']} ({author.get('works_count')} works)")
            works = fetch_works(author["id"])
            json.dump({
                "query_name": name, "openalex_id": author["id"],
                "display_name": author["display_name"],
                "affiliation": insts[0].get("display_name"),
                "works_count": author.get("works_count"),
                "cited_by_count": author.get("cited_by_count"),
                "num_works_fetched": len(works), "works": works,
            }, open(path, "w"), indent=2)
            print(f"   saved {len(works)} works")
        except Exception as e:
            print(f"   !! error: {e}")
        time.sleep(0.4)

    # prune profiles for faculty who left the roster
    for f in os.listdir(OUT):
        if f.endswith(".json") and f[:-5] not in current_slugs:
            os.remove(os.path.join(OUT, f))
            print(f"[prune] removed stale {f}")


if __name__ == "__main__":
    main()
