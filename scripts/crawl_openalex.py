#!/usr/bin/env python3
"""
Crawl Robotics @ Notre Dame faculty publication data from OpenAlex, and keep the
roster in sync with https://robotics.nd.edu/people/.

Roster (self-updating): each faculty card on the people page links to
`*.nd.edu/faculty/<slug>/` and carries a headshot (`img.image-circle`). We take
every card whose profile link is on an nd.edu domain -- that is exactly the ND
robotics faculty (external collaborators link off-site and are skipped). The
slug (e.g. `patrick-wensing`) gives the formal name we search OpenAlex with,
which resolves far better than the informal display names ("Pat Wensing"). When
someone is added or removed on the people page, they are added/removed here on
the next run, and their stale profile JSON + photo are pruned.

Safety: if the people page can't be parsed (empty/tiny roster), we fall back to a
curated list and DO NOT prune, so a transient scrape failure can't wipe the graph.

Why OpenAlex, not Google Scholar? Scholar has no API and CAPTCHA-blocks CI, so it
can't run unattended. scripts/crawl_scholar.py is a manual Scholar alternative.

Output: data/oa_profiles/<slug>.json  and  assets/faculty/<slug>.<ext>
"""
import json, os, re, sys, time, urllib.parse, urllib.request

MAILTO = os.environ.get("OPENALEX_MAILTO", "nd-pair@nd.edu")
ND = "https://openalex.org/I107639228"          # University of Notre Dame
API = "https://api.openalex.org"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "oa_profiles")
PHOTO_DIR = os.path.join(ROOT, "assets", "faculty")
os.makedirs(OUT, exist_ok=True)
os.makedirs(PHOTO_DIR, exist_ok=True)

PEOPLE_URL = "https://robotics.nd.edu/people/"
PEOPLE_ORIGIN = "https://robotics.nd.edu"

# Disambiguation for hard namesakes: slug -> OpenAlex author id.
OVERRIDES = {
    "zhi-zheng": "A5065741205",     # ND HRI/assistive robotics (not "Zheng Zhang")
}
# Slugs whose title-cased form does not resolve well -> better OpenAlex query.
SEARCH_NAME = {
    "j-william-goodwine": "Bill Goodwine",
}

# Used only if the people page can't be scraped (so we never wipe the graph).
# (slug, search_name, display_name)
FALLBACK_ROSTER = [
    ("edgar-bolivar-nieto", "Edgar Bolivar-Nieto", "Edgar Bolívar-Nieto"),
    ("tingyu-cheng", "Tingyu Cheng", "Tingyu Cheng"),
    ("nikolaus-correll", "Nikolaus Correll", "Nikolaus Correll"),
    ("j-william-goodwine", "Bill Goodwine", "Bill Goodwine"),
    ("mengxue-hou", "Mengxue Hou", "Mengxue Hou"),
    ("hai-lin", "Hai Lin", "Hai Lin"),
    ("margaret-coad", "Margaret Coad", "Margaret McGuinness"),
    ("yasemin-ozkan-aydin", "Yasemin Ozkan-Aydin", "Yasemin Ozkan-Aydin"),
    ("james-schmiedeler", "James Schmiedeler", "Jim Schmiedeler"),
    ("patrick-wensing", "Patrick Wensing", "Pat Wensing"),
    ("zhi-zheng", "Zhi Zheng", "Zhi Zheng"),
    ("panos-antsaklis", "Panos Antsaklis", "Panos Antsaklis"),
    ("toros-arikan", "Toros Arikan", "Toros Arikan"),
    ("jane-cleland-huang", "Jane Cleland-Huang", "Jane Cleland-Huang"),
    ("robert-landers", "Robert Landers", "Robert Landers"),
    ("michael-lemmon", "Michael Lemmon", "Mike Lemmon"),
]


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


def search_name_for(slug):
    if slug in SEARCH_NAME:
        return SEARCH_NAME[slug]
    return " ".join(w.capitalize() for w in slug.split("-"))


def scrape_people():
    """Return roster as list of dicts {slug, display, photo_url}.
    Only cards whose profile link is on an nd.edu domain are kept."""
    try:
        from bs4 import BeautifulSoup
    except Exception:
        print("[roster] beautifulsoup4 missing; using fallback", file=sys.stderr)
        return []
    try:
        html = http_get(PEOPLE_URL, as_json=False)
    except Exception as e:
        print(f"[roster] could not fetch people page: {e}", file=sys.stderr)
        return []
    soup = BeautifulSoup(html, "html.parser")
    seen, roster = set(), []
    for img in soup.select("img.image-circle"):
        node = img
        for _ in range(6):
            node = node.parent
            if node is None:
                break
            a = node.find("a", href=lambda h: h and re.search(r"nd\.edu/faculty/[a-z0-9-]+", h or ""))
            if not a:
                continue
            m = re.search(r"nd\.edu/faculty/([a-z0-9-]+)", a["href"])
            slug = m.group(1)
            if slug in seen:
                break
            seen.add(slug)
            src = img.get("src") or ""
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                src = PEOPLE_ORIGIN + src
            roster.append({"slug": slug, "display": a.get_text(strip=True), "photo_url": src})
            break
    return roster


def download_photo(url, slug):
    if not url:
        return None
    ext = os.path.splitext(url.split("?")[0])[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp"):
        ext = ".jpg"
    rel = f"assets/faculty/{slug}{ext}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": f"nd-pair-crawler ({MAILTO})"})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        with open(os.path.join(ROOT, rel), "wb") as f:
            f.write(data)
        return rel
    except Exception as e:
        print(f"   !! photo download failed for {slug}: {e}", file=sys.stderr)
        return None


def resolve_author(name, slug):
    """Best OpenAlex author for a name: override by id, else prefer ND + surname."""
    if slug in OVERRIDES:
        return http_get(f"{API}/authors/{OVERRIDES[slug]}?mailto={MAILTO}")
    sur = surname(name)
    q = urllib.parse.quote(name)
    ndid = ND.split("/")[-1]
    for url in (f"{API}/authors?filter=affiliations.institution.id:{ndid}&search={q}&per-page=25&mailto={MAILTO}",
                f"{API}/authors?search={q}&per-page=25&mailto={MAILTO}"):
        results = http_get(url).get("results", [])
        matched = [a for a in results if sur and sur in name_tokens(a.get("display_name", ""))]
        pool = matched or results
        nd = [a for a in pool
              if any(i.get("id") == ND for i in (a.get("last_known_institutions") or []))
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
            "select": "id,title,publication_year,publication_date,authorships",
            "per-page": 200, "cursor": cursor, "mailto": MAILTO,
        })
        data = http_get(f"{API}/works?{q}")
        for w in data.get("results", []):
            coauthors = [{"id": (a.get("author") or {}).get("id"),
                          "name": (a.get("author") or {}).get("display_name")}
                         for a in w.get("authorships", []) if (a.get("author") or {}).get("id")]
            works.append({"id": w["id"], "title": w.get("title"),
                          "year": w.get("publication_year"),
                          "date": w.get("publication_date"), "coauthors": coauthors})
        cursor = data.get("meta", {}).get("next_cursor")
        time.sleep(0.25)
    return works


def main():
    roster = scrape_people()
    live = len(roster) >= 5          # trust a live scrape only if it looks sane
    if not live:
        print(f"[roster] scrape returned {len(roster)}; using fallback (no pruning)")
        roster = [{"slug": s, "display": d, "photo_url": None, "search": q}
                  for (s, q, d) in FALLBACK_ROSTER]
    else:
        for c in roster:
            c["search"] = search_name_for(c["slug"])
        print(f"[roster] {len(roster)} ND faculty from people page: "
              + ", ".join(c["display"] for c in roster))
    json.dump([{"slug": c["slug"], "display": c["display"]} for c in roster],
              open(os.path.join(ROOT, "data", "faculty.json"), "w"), indent=2)

    current = set()
    for c in roster:
        slug, display, search = c["slug"], c["display"], c["search"]
        current.add(slug)
        path = os.path.join(OUT, f"{slug}.json")
        print(f"[resolve] {display}  (search: {search})")
        photo = download_photo(c.get("photo_url"), slug)
        try:
            author = resolve_author(search, slug)
            if not author:
                json.dump({"slug": slug, "display": display, "not_found": True, "photo": photo},
                          open(path, "w"), indent=2)
                print("   -- not found"); continue
            insts = author.get("last_known_institutions") or [{}]
            works = fetch_works(author["id"])
            json.dump({
                "slug": slug, "display": display, "query_name": search,
                "openalex_id": author["id"], "openalex_name": author["display_name"],
                "affiliation": insts[0].get("display_name"),
                "works_count": author.get("works_count"),
                "cited_by_count": author.get("cited_by_count"),
                "photo": photo,
                "num_works_fetched": len(works), "works": works,
            }, open(path, "w"), indent=2)
            print(f"   -> {author['display_name']} ({len(works)} works)"
                  f"{'  [photo]' if photo else ''}")
        except Exception as e:
            print(f"   !! error: {e}")
        time.sleep(0.4)

    # Prune faculty who left the roster -- only when we trust the live scrape.
    if live:
        keep_photos = set()
        for slug in current:
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                keep_photos.add(f"{slug}{ext}")
        for f in os.listdir(OUT):
            if f.endswith(".json") and f[:-5] not in current:
                os.remove(os.path.join(OUT, f)); print(f"[prune] {f}")
        for f in os.listdir(PHOTO_DIR):
            if f not in keep_photos:
                os.remove(os.path.join(PHOTO_DIR, f)); print(f"[prune] photo {f}")


if __name__ == "__main__":
    main()
