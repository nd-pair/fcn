#!/usr/bin/env python3
"""
Build data/graph.json (consumed by index.html) and assets/graph.png from the
crawled OpenAlex profiles in data/oa_profiles/.

Collaboration is exact: two faculty co-authored a work when one faculty's
OpenAlex author-id appears in the other's authorship list.
  node "publications" = that faculty's total works
  edge "weight"       = number of co-authored papers between the pair
"""
import glob, json, os, csv, itertools, datetime, math

import networkx as nx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROF = os.path.join(ROOT, "data", "oa_profiles")


def load():
    people = {}
    for path in sorted(glob.glob(os.path.join(PROF, "*.json"))):
        d = json.load(open(path))
        name = d.get("query_name")
        works = d.get("works") or []
        people[name] = {
            "author_id": d.get("openalex_id"),
            "num_works": d.get("num_works_fetched", len(works)),
            "affiliation": d.get("affiliation"),
            "cited_by": d.get("cited_by_count"),
            "openalex_id": d.get("openalex_id"),
            "not_found": d.get("not_found", False),
            "work_coauthors": {w["id"]: {c["id"] for c in w["coauthors"]} for w in works},
        }
    return people


def build(people):
    G = nx.Graph()
    for name, info in people.items():
        G.add_node(name, **{k: info[k] for k in
                            ("num_works", "affiliation", "cited_by", "openalex_id")})
    for a, b in itertools.combinations(people, 2):
        aid, bid = people[a]["author_id"], people[b]["author_id"]
        shared = set()
        if bid:
            shared |= {w for w, cos in people[a]["work_coauthors"].items() if bid in cos}
        if aid:
            shared |= {w for w, cos in people[b]["work_coauthors"].items() if aid in cos}
        if shared:
            G.add_edge(a, b, weight=len(shared))
    return G


def communities(G):
    """Assign a group id per node (greedy modularity on the connected part)."""
    groups = {}
    try:
        comms = nx.community.greedy_modularity_communities(G, weight="weight")
        for i, c in enumerate(comms):
            for n in c:
                groups[n] = i
    except Exception:
        for i, comp in enumerate(nx.connected_components(G)):
            for n in comp:
                groups[n] = i
    # isolated nodes each get their own "no collaboration" bucket = -1
    for n in G:
        if G.degree(n) == 0:
            groups[n] = -1
    return groups


def to_graph_json(G, groups):
    nodes = []
    for n in sorted(G, key=lambda n: -G.nodes[n]["num_works"]):
        d = G.nodes[n]
        nodes.append({
            "id": n,
            "publications": d["num_works"],
            "citedBy": d.get("cited_by"),
            "affiliation": d.get("affiliation"),
            "openalex": d.get("openalex_id"),
            "weightedDegree": int(G.degree(n, weight="weight")),
            "degree": G.degree(n),
            "group": groups.get(n, -1),
        })
    links = [{"source": u, "target": v, "weight": d["weight"]}
             for u, v, d in sorted(G.edges(data=True), key=lambda e: -e[2]["weight"])]
    return {
        "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "OpenAlex (https://openalex.org)",
        "description": "Robotics @ Notre Dame faculty collaboration network. "
                       "Node size = number of publications; edge weight = number of "
                       "co-authored papers between two faculty.",
        "nodeCount": G.number_of_nodes(),
        "edgeCount": G.number_of_edges(),
        "nodes": nodes,
        "links": links,
    }


def write_png(G, groups, out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    connected = [n for n in G if G.degree(n) > 0]
    isolates = sorted([n for n in G if G.degree(n) == 0], key=lambda n: -G.nodes[n]["num_works"])
    fig, ax = plt.subplots(figsize=(17, 12))
    pos = nx.kamada_kawai_layout(G.subgraph(connected), weight="weight") if connected else {}
    if pos:
        xs = [p[0] for p in pos.values()]; ys = [p[1] for p in pos.values()]
        left, top, bot = min(xs) - 1.1, max(ys), min(ys)
    else:
        left, top, bot = -1, 1, -1
    for i, n in enumerate(isolates):
        y = top - (top - bot) * (i / max(1, len(isolates) - 1)) if len(isolates) > 1 else 0
        pos[n] = (left, y)
    nsize = lambda w: 150 + 140 * math.sqrt(w)
    sizes = [nsize(G.nodes[n]["num_works"]) for n in G]
    if G.number_of_edges():
        ws = [G[u][v]["weight"] for u, v in G.edges()]; mx = max(ws)
        nx.draw_networkx_edges(G, pos, width=[1 + 8 * w / mx for w in ws], edge_color="#3B6EA5", alpha=0.55, ax=ax)
        nx.draw_networkx_edge_labels(G, pos, edge_labels={(u, v): G[u][v]["weight"] for u, v in G.edges()},
                                     font_size=9, font_color="#A11", rotate=False,
                                     bbox=dict(boxstyle="round,pad=0.15", fc="white", ec="#ccc", alpha=0.85), ax=ax)
    nodes = nx.draw_networkx_nodes(G, pos, node_size=sizes,
                                   node_color=[groups.get(n, -1) for n in G], cmap="tab10",
                                   edgecolors="#333", linewidths=1.1, ax=ax)
    nodes.set_zorder(3)
    for n, (x, y) in pos.items():
        ax.text(x, y - (0.05 + 0.0016 * math.sqrt(G.nodes[n]["num_works"])), n, fontsize=9,
                fontweight="bold", ha="center", va="top", zorder=5,
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.75))
    ax.set_title("Robotics @ Notre Dame — Faculty Collaboration Network\n"
                 "node size = # publications · edge label/width = # co-authored papers · source: OpenAlex",
                 fontsize=13, pad=14)
    ax.axis("off"); plt.tight_layout()
    plt.savefig(out, dpi=150, bbox_inches="tight", facecolor="white")


def write_csv(G, path):
    with open(path, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["faculty_a", "faculty_b", "coauthored_papers"])
        for u, v, d in sorted(G.edges(data=True), key=lambda e: -e[2]["weight"]):
            w.writerow([u, v, d["weight"]])


def main():
    people = load()
    G = build(people)
    groups = communities(G)
    print(f"graph: {G.number_of_nodes()} nodes, {G.number_of_edges()} edges")

    os.makedirs(os.path.join(ROOT, "data"), exist_ok=True)
    os.makedirs(os.path.join(ROOT, "assets"), exist_ok=True)
    json.dump(to_graph_json(G, groups), open(os.path.join(ROOT, "data", "graph.json"), "w"), indent=2)
    write_csv(G, os.path.join(ROOT, "data", "collaboration_edges.csv"))
    print("wrote data/graph.json and data/collaboration_edges.csv")
    try:
        write_png(G, groups, os.path.join(ROOT, "assets", "graph.png"))
        print("wrote assets/graph.png")
    except Exception as e:
        print(f"(png skipped: {e})")


if __name__ == "__main__":
    main()
