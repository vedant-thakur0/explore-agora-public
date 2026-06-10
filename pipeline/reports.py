"""
pipeline/reports.py — Build a self-contained, dated HTML report bundle.

Usage (via CLI):
    python3 -m pipeline.cli reports [--execute] [--allow-errors] [--timeout SECONDS]

Output: reports/generated/<YYYY-MM-DD>/index.html  (plus all copied artifacts)
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import textwrap
import warnings
from datetime import date
from pathlib import Path
from typing import Any

from .config import (
    AGENTS_OUTPUT_DIR,
    GRAPH_DATA_DIR,
    MULTIPLEX_GRAPH_DIR,
    REPORTS_DIR,
    REPORTS_GENERATED_DIR,
    PROJECT_ROOT,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
NOTEBOOKS_DIR = PROJECT_ROOT / "notebooks"
NOTEBOOKS_OUTPUTS_DIR = NOTEBOOKS_DIR / "outputs"

NOTEBOOK_FILES = [
    ("01_sponsor_profiling.ipynb", "Sponsor Profiling"),
    ("02_policy_networks.ipynb",   "Policy Networks"),
    ("03_coalitions.ipynb",        "Coalitions"),
    ("04_taxonomy.ipynb",          "Taxonomy"),
]

# Plain-English descriptions for non-technical readers
NOTEBOOK_DESCRIPTIONS = {
    "01_sponsor_profiling.ipynb": (
        "Shows which legislators are most active on AI-related bills, their party "
        "affiliation, and the policy areas they focus on."
    ),
    "02_policy_networks.ipynb": (
        "Maps how different AI policy topics are connected through shared sponsorship "
        "and co-sponsorship patterns across Congress."
    ),
    "03_coalitions.ipynb": (
        "Identifies clusters of legislators who consistently work together on AI "
        "legislation, revealing cross-party and cross-chamber alliances."
    ),
    "04_taxonomy.ipynb": (
        "Breaks down the AGORA taxonomy of AI policy categories — strategies, "
        "applications, harms — and shows how bills are distributed across them."
    ),
}

VIZ_DESCRIPTIONS = {
    "fig_breadth_depth.html":           "Breadth vs. depth of each sponsor's AI policy portfolio.",
    "fig_chamber_asymmetry.html":       "Difference in AI bill activity between House and Senate.",
    "fig_policy_centrality.html":       "Which policy areas sit at the center of the legislative network.",
    "fig_policy_integration.html":      "How tightly different policy domains are connected to each other.",
    "fig_policy_network.html":          "Interactive map of all policy-area connections in the dataset.",
    "fig_sponsor_degree_dist.html":     "Distribution of how many bills each sponsor has championed.",
    "fig_strategies_applications.html": "Relationship between strategic approaches and application domains.",
    "fig_strategies_harms.html":        "How legislative strategies address different AI-related harms.",
    "fig_taxonomy_fingerprints.html":   "Unique 'fingerprint' of each legislator's AI policy focus areas.",
}

REPORT_MD_DESCRIPTIONS = {
    "community_memory_ner_paper.md":    "NER (named-entity recognition) findings compiled for the research paper.",
    "cosponsor_entity_cooccurrence.md": "Which organizations and roles appear together in co-sponsored bills.",
    "entity_tag_cooccurrence.md":       "How named entities align with the AGORA taxonomy tags.",
    "ner_initial_analysis.md":          "First-pass analysis of entities extracted from the bill corpus.",
}

COMMUNITY_HTML_DESCRIPTIONS = {
    "community_001_network.html": (
        "Interactive network visualization of the largest cosponsor community "
        "(Health policy cluster)."
    ),
}

IMAGE_DESCRIPTIONS = {
    "community_2_detail.png":      "Detailed network diagram for Community 2 (Science & Technology).",
    "cosponsor_sample_2.png":      "Sample of cosponsor relationships in Community 2.",
    "communities_2_5_network.png": "Combined network view of communities detected at resolution 2.5.",
}

CSV_DESCRIPTIONS = {
    "agora_comprehensive_data_with_cosponsor_lists.csv": (
        "Main dataset: 622 AI-related bills with policy areas, sponsor info, "
        "and full cosponsor lists."
    ),
    "agora_cosponsors_long.csv": (
        "Long-format cosponsor table — one row per bill-cosponsor pair, "
        "suitable for network analysis."
    ),
    "agora_with_sponsors.csv": (
        "Bills with primary sponsor details pulled from the Congress.gov API."
    ),
    "bill_sponsors.csv": (
        "205 unique sponsors with party, state, bill counts, and top policy areas."
    ),
    "agora_comprehensive_data.csv": (
        "Full AGORA dataset with taxonomy tags, policy areas, and metadata."
    ),
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _warn(msg: str) -> None:
    print(f"[reports] WARNING: {msg}", file=sys.stderr)


def _copy(src: Path, dst: Path) -> bool:
    """Copy src to dst, returning True on success. Warns and returns False if missing."""
    if not src.exists():
        _warn(f"Skipping missing artifact: {src}")
        return False
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    return True


def _md_to_html_fragment(md_path: Path) -> str:
    """Convert a Markdown file to a minimal HTML fragment (no framework, stdlib only)."""
    lines = md_path.read_text(encoding="utf-8").splitlines()
    html_lines: list[str] = []
    in_code = False
    for line in lines:
        if line.startswith("```"):
            if in_code:
                html_lines.append("</pre>")
                in_code = False
            else:
                html_lines.append("<pre>")
                in_code = True
            continue
        if in_code:
            html_lines.append(line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
            continue
        # Headings
        if line.startswith("### "):
            html_lines.append(f"<h4>{line[4:]}</h4>")
        elif line.startswith("## "):
            html_lines.append(f"<h3>{line[3:]}</h3>")
        elif line.startswith("# "):
            html_lines.append(f"<h2>{line[2:]}</h2>")
        elif line.startswith("- ") or line.startswith("* "):
            html_lines.append(f"<li>{line[2:]}</li>")
        elif line.strip() == "":
            html_lines.append("<br>")
        else:
            html_lines.append(f"<p>{line}</p>")
    return "\n".join(html_lines)


def _render_notebook(nb_path: Path, out_dir: Path, execute: bool,
                     allow_errors: bool, timeout: int) -> tuple[bool, Path | None]:
    """
    Render a notebook to HTML via nbconvert.
    Returns (success, output_html_path).
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    out_html = out_dir / (nb_path.stem + ".html")
    cmd = [
        sys.executable, "-m", "nbconvert",
        "--to", "html",
        "--output-dir", str(out_dir),
        "--output", nb_path.stem,
    ]
    if execute:
        cmd += ["--execute", f"--ExecutePreprocessor.timeout={timeout}"]
        if allow_errors:
            cmd += ["--allow-errors"]
    cmd.append(str(nb_path))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 60)
        if result.returncode != 0:
            _warn(f"nbconvert failed for {nb_path.name}: {result.stderr[:500]}")
            return False, None
        if out_html.exists():
            return True, out_html
        _warn(f"nbconvert ran but output not found: {out_html}")
        return False, None
    except subprocess.TimeoutExpired:
        _warn(f"nbconvert timed out for {nb_path.name} after {timeout}s")
        return False, None
    except Exception as exc:
        _warn(f"nbconvert exception for {nb_path.name}: {exc}")
        return False, None


# ---------------------------------------------------------------------------
# Summary generators (inline HTML tables for index)
# ---------------------------------------------------------------------------

def _cosponsor_communities_table(json_path: Path) -> str:
    """Build an HTML table summarising the 5 cosponsor communities."""
    if not json_path.exists():
        return "<p><em>cosponsor_communities.json not found.</em></p>"
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        communities = data.get("communities", [])[:5]
        rows = ""
        for c in communities:
            rows += (
                f"<tr><td>{c['id']}</td>"
                f"<td>{c['size']}</td>"
                f"<td>{c.get('top_policy', '—')}</td></tr>\n"
            )
        return textwrap.dedent(f"""\
            <table>
              <thead><tr><th>Community ID</th><th>Sponsors</th><th>Top Policy Area</th></tr></thead>
              <tbody>
            {rows}  </tbody>
            </table>
            <p class="footnote">Source: <code>pipeline/agents/output/cosponsor_communities.json</code></p>
        """)
    except Exception as exc:
        return f"<p><em>Could not parse cosponsor_communities.json: {exc}</em></p>"


def _multiplex_stats_table(json_path: Path) -> str:
    """Build an HTML table from multiplex_stats.json."""
    if not json_path.exists():
        return "<p><em>multiplex_stats.json not found.</em></p>"
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
        combined = data.get("combined", {})
        layers = data.get("layers", {})
        rows = f"""\
<tr><td><strong>All layers combined</strong></td><td>{combined.get('nodes','—')}</td><td>{combined.get('edges','—')}</td></tr>
"""
        for layer_name, stats in layers.items():
            label = layer_name.replace("_", " ").title()
            rows += (
                f"<tr><td>{label}</td>"
                f"<td>{stats.get('nodes','—')}</td>"
                f"<td>{stats.get('edges','—')}</td></tr>\n"
            )
        return textwrap.dedent(f"""\
            <table>
              <thead><tr><th>Layer</th><th>Nodes</th><th>Edges</th></tr></thead>
              <tbody>
            {rows}  </tbody>
            </table>
            <p class="footnote">Source: <code>pipeline/multiplex_graph/multiplex_stats.json</code></p>
        """)
    except Exception as exc:
        return f"<p><em>Could not parse multiplex_stats.json: {exc}</em></p>"


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

_CSS = """\
/* AGORA Report — minimal, clean, no JS frameworks */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
  font-size: 15px; line-height: 1.65;
  color: #1a1a2e; background: #f8f9fb;
}
header {
  background: #1a1a2e; color: #fff;
  padding: 2rem 3rem;
}
header h1 { font-size: 1.8rem; font-weight: 700; letter-spacing: -.02em; }
header .meta { font-size: 0.9rem; color: #a0aab8; margin-top: .4rem; }
nav {
  background: #fff; border-bottom: 1px solid #e2e8f0;
  padding: .6rem 3rem; position: sticky; top: 0; z-index: 10;
}
nav a {
  display: inline-block; margin-right: 1.4rem;
  color: #2563eb; text-decoration: none; font-size: .88rem;
}
nav a:hover { text-decoration: underline; }
main { max-width: 980px; margin: 2rem auto; padding: 0 2rem 4rem; }
section { background: #fff; border: 1px solid #e2e8f0; border-radius: 8px;
          padding: 1.8rem 2rem; margin-bottom: 2rem; }
h2 { font-size: 1.25rem; color: #1a1a2e; margin-bottom: .4rem; }
h3 { font-size: 1rem; color: #374151; margin: 1.2rem 0 .3rem; }
h4 { font-size: .9rem; color: #6b7280; margin: .8rem 0 .2rem; }
.desc { color: #4b5563; font-size: .93rem; margin-bottom: 1rem; }
ul.file-list { list-style: none; padding: 0; }
ul.file-list li { padding: .35rem 0; border-bottom: 1px solid #f1f5f9; }
ul.file-list li:last-child { border-bottom: none; }
ul.file-list a { color: #2563eb; text-decoration: none; font-weight: 500; }
ul.file-list a:hover { text-decoration: underline; }
ul.file-list .sub-desc { color: #6b7280; font-size: .85rem; display: block; }
.badge {
  display: inline-block; font-size: .72rem; font-weight: 600;
  padding: .15rem .5rem; border-radius: 4px;
  margin-left: .5rem; vertical-align: middle;
}
.badge-pending { background: #fef3c7; color: #92400e; }
.badge-ready   { background: #d1fae5; color: #065f46; }
.badge-missing { background: #fee2e2; color: #991b1b; }
table {
  width: 100%; border-collapse: collapse;
  margin-top: .6rem; font-size: .9rem;
}
th { background: #f1f5f9; text-align: left; padding: .5rem .8rem;
     font-size: .82rem; color: #374151; letter-spacing: .04em; text-transform: uppercase; }
td { padding: .45rem .8rem; border-top: 1px solid #e2e8f0; }
tr:hover td { background: #f8fafc; }
.footnote { font-size: .78rem; color: #9ca3af; margin-top: .5rem; }
.warning-box {
  background: #fffbeb; border: 1px solid #fcd34d;
  border-radius: 6px; padding: .7rem 1rem;
  font-size: .88rem; color: #78350f; margin-bottom: 1rem;
}
pre { background: #f1f5f9; border-radius: 4px; padding: .8rem 1rem;
      font-size: .82rem; overflow-x: auto; }
li { margin-left: 1.2rem; margin-bottom: .2rem; }
"""

# ---------------------------------------------------------------------------
# HTML builder
# ---------------------------------------------------------------------------

def build_report(
    out_root: Path,
    execute: bool = False,
    allow_errors: bool = False,
    nb_timeout: int = 300,
) -> Path:
    """
    Build the report bundle. Returns the path to index.html.
    """
    today = date.today().isoformat()
    bundle_dir = out_root / today
    bundle_dir.mkdir(parents=True, exist_ok=True)

    # Sub-dirs inside the bundle
    nb_out_dir = bundle_dir / "notebooks"
    viz_out_dir = bundle_dir / "visualizations"
    reports_out_dir = bundle_dir / "analyses"
    images_out_dir = bundle_dir / "images"

    # -----------------------------------------------------------------------
    # 1. Render notebooks
    # -----------------------------------------------------------------------
    print("[reports] Rendering notebooks …")
    notebook_items: list[dict[str, Any]] = []
    for fname, label in NOTEBOOK_FILES:
        nb_path = NOTEBOOKS_DIR / fname
        if not nb_path.exists():
            _warn(f"Notebook not found, skipping: {nb_path}")
            notebook_items.append({"fname": fname, "label": label, "status": "missing", "rel": None})
            continue

        ok, out_html = _render_notebook(nb_path, nb_out_dir, execute, allow_errors, nb_timeout)
        if ok and out_html:
            rel = f"notebooks/{out_html.name}"
            status = "ready" if execute else "pending"
        else:
            rel = None
            status = "missing" if not nb_path.exists() else "pending"
        notebook_items.append({"fname": fname, "label": label, "status": status, "rel": rel})

    # -----------------------------------------------------------------------
    # 2. Copy interactive visualizations (notebooks/outputs/*.html)
    # -----------------------------------------------------------------------
    print("[reports] Copying interactive visualizations …")
    viz_out_dir.mkdir(parents=True, exist_ok=True)
    viz_items: list[dict] = []
    for html_file in sorted(NOTEBOOKS_OUTPUTS_DIR.glob("*.html")):
        dst = viz_out_dir / html_file.name
        ok = _copy(html_file, dst)
        if ok:
            viz_items.append({
                "name": html_file.name,
                "rel": f"visualizations/{html_file.name}",
                "desc": VIZ_DESCRIPTIONS.get(html_file.name, "Interactive Plotly visualization."),
            })

    # -----------------------------------------------------------------------
    # 3. Copy reports/*.md and reports/*.html
    # -----------------------------------------------------------------------
    print("[reports] Copying analysis reports …")
    reports_out_dir.mkdir(parents=True, exist_ok=True)
    analysis_items: list[dict] = []

    for md_file in sorted(REPORTS_DIR.glob("*.md")):
        # Render md -> simple html
        html_name = md_file.stem + ".html"
        dst = reports_out_dir / html_name
        try:
            fragment = _md_to_html_fragment(md_file)
            title = md_file.stem.replace("_", " ").title()
            page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{title} — AGORA</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2rem auto;padding:0 1.5rem;line-height:1.6;color:#222}}
h2,h3,h4{{margin:1.2rem 0 .4rem}}pre{{background:#f4f4f4;padding:.8rem;border-radius:4px;overflow-x:auto}}
a{{color:#2563eb}}</style></head><body>
<p><a href="../index.html">← Back to report index</a></p>
{fragment}
</body></html>"""
            dst.write_text(page, encoding="utf-8")
            analysis_items.append({
                "name": md_file.name,
                "rel": f"analyses/{html_name}",
                "desc": REPORT_MD_DESCRIPTIONS.get(md_file.name, "Analysis report."),
                "kind": "md",
            })
        except Exception as exc:
            _warn(f"Could not convert {md_file.name}: {exc}")

    for html_file in sorted(REPORTS_DIR.glob("*.html")):
        dst = reports_out_dir / html_file.name
        ok = _copy(html_file, dst)
        if ok:
            analysis_items.append({
                "name": html_file.name,
                "rel": f"analyses/{html_file.name}",
                "desc": COMMUNITY_HTML_DESCRIPTIONS.get(
                    html_file.name, "Community network visualization."
                ),
                "kind": "html",
            })

    # -----------------------------------------------------------------------
    # 4. Copy network images
    # -----------------------------------------------------------------------
    print("[reports] Copying network images …")
    images_out_dir.mkdir(parents=True, exist_ok=True)
    image_items: list[dict] = []
    for pattern in ("community_*_detail.png", "community_*_sample.png", "*.png"):
        for img in sorted(AGENTS_OUTPUT_DIR.glob(pattern)):
            dst = images_out_dir / img.name
            if dst.exists():
                continue  # already copied by a previous pattern
            ok = _copy(img, dst)
            if ok:
                image_items.append({
                    "name": img.name,
                    "rel": f"images/{img.name}",
                    "desc": IMAGE_DESCRIPTIONS.get(img.name, "Network visualization image."),
                })

    # -----------------------------------------------------------------------
    # 5. Inline summaries from JSON files
    # -----------------------------------------------------------------------
    print("[reports] Building inline data summaries …")
    community_table_html = _cosponsor_communities_table(
        AGENTS_OUTPUT_DIR / "cosponsor_communities.json"
    )
    multiplex_table_html = _multiplex_stats_table(
        MULTIPLEX_GRAPH_DIR / "multiplex_stats.json"
    )

    # -----------------------------------------------------------------------
    # 6. CSV links (no copy — large files)
    # -----------------------------------------------------------------------
    csv_items: list[dict] = []
    for csv_file in sorted(GRAPH_DATA_DIR.glob("*.csv")):
        csv_items.append({
            "name": csv_file.name,
            "path": str(csv_file),
            "desc": CSV_DESCRIPTIONS.get(csv_file.name, "Data CSV."),
        })

    # -----------------------------------------------------------------------
    # 7. Build index.html
    # -----------------------------------------------------------------------
    print("[reports] Writing index.html …")

    def _section_id(label: str) -> str:
        return label.lower().replace(" ", "-").replace("/", "-")

    # --- Notebook section HTML ---
    nb_rows = ""
    for item in notebook_items:
        badge_class = {
            "ready": "badge-ready",
            "pending": "badge-pending",
            "missing": "badge-missing",
        }.get(item["status"], "badge-pending")
        badge_text = {
            "ready": "rendered",
            "pending": "pending regeneration",
            "missing": "not found",
        }.get(item["status"], "pending")
        desc = NOTEBOOK_DESCRIPTIONS.get(item["fname"], "")
        if item["rel"]:
            link = f'<a href="{item["rel"]}">{item["label"]}</a>'
        else:
            link = item["label"]
        nb_rows += f"""\
      <li>
        {link} <span class="badge {badge_class}">{badge_text}</span>
        <span class="sub-desc">{desc}</span>
      </li>\n"""

    # --- Viz section HTML ---
    viz_rows = ""
    for v in viz_items:
        viz_rows += f"""\
      <li>
        <a href="{v['rel']}">{v['name']}</a>
        <span class="sub-desc">{v['desc']}</span>
      </li>\n"""
    if not viz_rows:
        viz_rows = "      <li><em>No visualizations found.</em></li>\n"

    # --- Analysis section HTML ---
    analysis_rows = ""
    for a in analysis_items:
        analysis_rows += f"""\
      <li>
        <a href="{a['rel']}">{a['name']}</a>
        <span class="sub-desc">{a['desc']}</span>
      </li>\n"""
    if not analysis_rows:
        analysis_rows = "      <li><em>No analysis reports found.</em></li>\n"

    # --- Images section HTML ---
    image_rows = ""
    for img in image_items:
        image_rows += f"""\
      <li>
        <a href="{img['rel']}">{img['name']}</a>
        <span class="sub-desc">{img['desc']}</span>
      </li>\n"""
    if not image_rows:
        image_rows = "      <li><em>No network images found.</em></li>\n"

    # --- CSV section HTML ---
    csv_rows = ""
    for c in csv_items:
        csv_rows += f"""\
      <li>
        <strong>{c['name']}</strong>
        <span class="sub-desc">{c['desc']}</span>
        <span class="sub-desc" style="color:#9ca3af">Path: <code>{c['path']}</code></span>
      </li>\n"""
    if not csv_rows:
        csv_rows = "      <li><em>No CSV files found.</em></li>\n"

    execute_note = (
        ""
        if execute
        else """<div class="warning-box">
      <strong>Note:</strong> Notebooks were rendered <em>without execution</em> —
      outputs may be empty or stale. To regenerate with live outputs, run:<br>
      <code>python3 -m pipeline.cli reports --execute --allow-errors</code>
    </div>"""
    )

    index_html = f"""\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AGORA Report — {today}</title>
  <style>
{_CSS}
  </style>
</head>
<body>
<header>
  <h1>AGORA AI Policy Research — Internal Report</h1>
  <div class="meta">Generated {today} &nbsp;|&nbsp; Explore-AGORA toolkit &nbsp;|&nbsp; For internal distribution only</div>
</header>

<nav>
  <a href="#notebooks">Notebooks</a>
  <a href="#visualizations">Interactive Charts</a>
  <a href="#analyses">Analyses</a>
  <a href="#images">Network Images</a>
  <a href="#communities">Sponsor Communities</a>
  <a href="#graph-stats">Graph Stats</a>
  <a href="#data">Source Data</a>
</nav>

<main>

  <!-- ── Notebooks ─────────────────────────────────────────────────────── -->
  <section id="notebooks">
    <h2>Analytical Notebooks</h2>
    <p class="desc">
      Four core research notebooks covering sponsor profiling, policy networks, coalition
      detection, and taxonomy analysis. Open any link to read the full notebook with charts
      and commentary.
    </p>
    {execute_note}
    <ul class="file-list">
{nb_rows}    </ul>
  </section>

  <!-- ── Interactive Visualizations ────────────────────────────────────── -->
  <section id="visualizations">
    <h2>Interactive Charts</h2>
    <p class="desc">
      Plotly-based interactive charts exported from the analytical notebooks.
      Click any chart to explore it — hover over data points for details.
    </p>
    <ul class="file-list">
{viz_rows}    </ul>
  </section>

  <!-- ── Analysis Reports ───────────────────────────────────────────────── -->
  <section id="analyses">
    <h2>Written Analyses &amp; Network Visualizations</h2>
    <p class="desc">
      Narrative write-ups and community network maps produced during the research process.
      Markdown reports have been converted to HTML for easy reading.
    </p>
    <ul class="file-list">
{analysis_rows}    </ul>
  </section>

  <!-- ── Network Images ────────────────────────────────────────────────── -->
  <section id="images">
    <h2>Network Diagrams</h2>
    <p class="desc">
      Static network diagrams showing clusters of legislators and their co-sponsorship
      relationships, generated by the community-detection pipeline.
    </p>
    <ul class="file-list">
{image_rows}    </ul>
  </section>

  <!-- ── Sponsor Communities Summary ───────────────────────────────────── -->
  <section id="communities">
    <h2>Sponsor Communities — Quick Summary</h2>
    <p class="desc">
      The pipeline grouped legislators into communities based on who co-sponsors
      bills together. Each row is one community; the top policy area shows where
      that group focuses most of its AI legislation work.
    </p>
    {community_table_html}
  </section>

  <!-- ── Multiplex Graph Stats ─────────────────────────────────────────── -->
  <section id="graph-stats">
    <h2>Knowledge Graph — Node &amp; Edge Counts</h2>
    <p class="desc">
      The AGORA knowledge graph connects bills, sponsors, organizations, and policy
      concepts. These counts reflect the latest built graph.
    </p>
    {multiplex_table_html}
  </section>

  <!-- ── Source Data CSVs ───────────────────────────────────────────────── -->
  <section id="data">
    <h2>Source Data Files</h2>
    <p class="desc">
      The underlying CSV datasets. These files are large and are <strong>not included
      in this bundle</strong> — links show the file location on the shared drive or
      local copy of the repository.
    </p>
    <ul class="file-list">
{csv_rows}    </ul>
    <p class="footnote">
      Column descriptions: see
      <code>knowledge_graph/graph_data/bill_sponsors_README.md</code>
      in the repository.
    </p>
  </section>

</main>
</body>
</html>
"""
    index_path = bundle_dir / "index.html"
    index_path.write_text(index_html, encoding="utf-8")
    print(f"[reports] Bundle complete: {bundle_dir}")
    print(f"[reports] Open: {index_path}")
    return index_path
