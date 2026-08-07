# Robotics @ Notre Dame — Faculty Collaboration Network

An interactive graph of who co-authors with whom among the
[Robotics @ Notre Dame](https://robotics.nd.edu/people/) faculty.

- **Node** = a faculty member, sized by number of publications.
- **Edge** = the two faculty have co-authored papers; thickness and the number
  label are how many.
- **Color** = collaboration cluster (grey = no co-authorships with other ND
  robotics faculty).

**Live site:** https://nd-pair.github.io/web/

![collaboration graph](assets/graph.png)

## How it works

```
robotics.nd.edu/people/   →  crawl_openalex.py  →  data/oa_profiles/*.json
                                     │
                                     ▼
                              build_site.py      →  data/graph.json  (+ assets/graph.png)
                                     │
                                     ▼
                               index.html         →  interactive D3 force graph
```

1. **`scripts/crawl_openalex.py`** scrapes the current faculty roster from
   `robotics.nd.edu/people/`, resolves each person to an
   [OpenAlex](https://openalex.org) author id (preferring a Notre Dame
   affiliation and a matching surname), and downloads every work with its
   co-authors. Output: one JSON per faculty in `data/oa_profiles/`.
2. **`scripts/build_site.py`** turns those profiles into `data/graph.json`.
   Two faculty are linked when one's OpenAlex author id appears in the other's
   authorship list; the edge weight is the number of such shared papers.
3. **`index.html`** loads `data/graph.json` and renders the interactive graph
   (drag nodes, hover for details, click a node to open its OpenAlex profile).

### Why OpenAlex instead of Google Scholar?

Google Scholar has no public API and serves a CAPTCHA to automated / datacenter
traffic, so it cannot run unattended in CI. OpenAlex is an open, crawlable
scholarly graph that exposes the same co-authorship signal.
`scripts/crawl_scholar.py` keeps a Google Scholar version for **manual** runs
from a residential connection, if you want to cross-check.

## Run locally

```bash
pip install -r scripts/requirements.txt
python scripts/crawl_openalex.py     # refresh data/oa_profiles/
python scripts/build_site.py         # rebuild data/graph.json + assets/graph.png
python -m http.server 8000           # then open http://localhost:8000
```

## Automation

`.github/workflows/update.yml` runs the crawl + build and deploys to GitHub
Pages:

- **weekly** (Mondays 06:17 UTC),
- **on every push to `main`**, and
- **on demand** (Actions → *Run workflow*).

Refreshed data is committed back to the repo with the `GITHUB_TOKEN`, which by
design does **not** retrigger the workflow, so there is no loop.

### One-time setup

1. **Settings → Pages → Build and deployment → Source: GitHub Actions.**
2. (Optional) add a repo secret **`OPENALEX_MAILTO`** with a contact email to
   join OpenAlex's faster "polite pool".
3. If the repo is **private**, GitHub Pages requires a GitHub Team/Enterprise
   plan; otherwise make the repo public.

## Data notes / caveats

- Author disambiguation is automated. A few names are common: `Zhi Zheng` is
  pinned to the correct ND author via an override in `crawl_openalex.py`; add
  more overrides there if a faculty member resolves to the wrong person.
- Very common names (e.g. `Hai Lin`) can map to an over-merged OpenAlex profile,
  which inflates that node's publication count. The *co-authorship* links are
  still valid.
- `Toros Arikan` may show a previous institution until OpenAlex catches up.

Data source: [OpenAlex](https://openalex.org). Graph rendered with
[D3](https://d3js.org).
