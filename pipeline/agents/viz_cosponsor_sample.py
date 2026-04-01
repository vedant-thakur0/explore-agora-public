"""Visualize one document's full sponsor/cosponsor neighborhood."""
import csv
from pathlib import Path

import matplotlib.pyplot as plt
import networkx as nx

OUT = Path("pipeline/agents/output")
AGORA_ID = "2"  # NDAA FY2022 §226 — has 2 cosponsors in agora_cosponsors_long.csv

G = nx.DiGraph()
doc_node = f"document:{AGORA_ID}"
G.add_node(doc_node, label=f"Doc {AGORA_ID}", color="steelblue")

# Primary sponsor from sponsor_edges.csv
sponsor_edges_path = OUT / "sponsor_edges.csv"
if sponsor_edges_path.exists():
    for row in csv.DictReader(open(sponsor_edges_path)):
        if row["src_id"] == doc_node and row["relation"] == "SPONSORED_BY":
            G.add_node(row["dst_id"], label=row["dst_id"].split(":")[1][:10], color="orange")
            G.add_edge(doc_node, row["dst_id"], label="SPONSORED_BY")

# Active cosponsors
cosponsor_edges_path = OUT / "cosponsor_edges.csv"
if cosponsor_edges_path.exists():
    for row in csv.DictReader(open(cosponsor_edges_path)):
        if row["src_id"] == doc_node and row["relation"] == "COSPONSORED_BY":
            G.add_node(row["dst_id"], label=row["dst_id"].split(":")[1][:10], color="green")
            G.add_edge(doc_node, row["dst_id"], label="COSPONSORED_BY")

# Withdrawn cosponsors
withdrawn_edges_path = OUT / "withdrawn_cosponsor_edges.csv"
if withdrawn_edges_path.exists():
    for row in csv.DictReader(open(withdrawn_edges_path)):
        if row["src_id"] == doc_node and row["relation"] == "WITHDREW_COSPONSOR":
            G.add_node(row["dst_id"], label=row["dst_id"].split(":")[1][:10], color="red")
            G.add_edge(doc_node, row["dst_id"], label="WITHDREW_COSPONSOR")

if G.number_of_nodes() > 1:
    colors = [G.nodes[n].get("color", "grey") for n in G.nodes]
    pos = nx.spring_layout(G, seed=42)
    nx.draw(G, pos, node_color=colors, labels={n: G.nodes[n]["label"] for n in G.nodes},
            with_labels=True, font_size=8, arrows=True)
    edge_labels = nx.get_edge_attributes(G, "label")
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7)
    plt.title(f"Sponsor layers — Document {AGORA_ID}")
    plt.tight_layout()
    output_path = OUT / f"cosponsor_sample_{AGORA_ID}.png"
    plt.savefig(output_path, dpi=150)
    print(f"Saved: {output_path}")
else:
    print(f"Document {AGORA_ID} has no sponsor data. Check that sponsor_graph phase has run.")
