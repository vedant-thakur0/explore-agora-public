"""
Build a standalone HTML dashboard from notebook figure exports.

Run AFTER all 4 analysis notebooks have been executed.

Usage:
    python3 notebooks/build_dashboard.py
"""

from pathlib import Path

OUTPUTS = Path(__file__).parent / "outputs"
DASHBOARD = Path(__file__).parent / "dashboard.html"

# Dashboard sections: (section_title, [(figure_title, filename), ...])
SECTIONS = [
    ("Sponsor Profiling", [
        ("Sponsor Degree Distribution", "fig_sponsor_degree_dist.html"),
        ("Specialist vs. Generalist", "fig_breadth_depth.html"),
        ("Chamber Asymmetry", "fig_chamber_asymmetry.html"),
        ("Taxonomy Fingerprints", "fig_taxonomy_fingerprints.html"),
    ]),
    ("Policy Area Networks", [
        ("Policy Co-occurrence Network", "fig_policy_network.html"),
        ("Policy Area Centrality", "fig_policy_centrality.html"),
        ("Strategies x Harms", "fig_strategies_harms.html"),
        ("Strategies x Applications", "fig_strategies_applications.html"),
        ("Domain Integration", "fig_policy_integration.html"),
    ]),
    ("Coalitions & Bipartisanship", [
        ("Bipartisanship Distribution", "fig_bipartisanship_dist.html"),
        ("Bipartisanship by Policy Area", "fig_bipartisanship_by_area.html"),
        ("Bridge Legislators", "fig_bridge_legislators.html"),
        ("Coalition Stability", "fig_coalition_stability.html"),
        ("Cosponsor Network", "fig_cosponsor_network.html"),
    ]),
    ("Taxonomy Deep-Dive", [
        ("Community Strategy Profiles", "fig_community_strategies.html"),
        ("Harm to Strategy Sankey", "fig_harm_strategy_sankey.html"),
        ("Application Coverage", "fig_application_coverage.html"),
        ("Application Radar by Community", "fig_application_radar.html"),
        ("Incentives by Party", "fig_incentives_by_party.html"),
        ("Risk Factor Treemap", "fig_risk_treemap.html"),
    ]),
]


def build_dashboard():
    """Assemble dashboard HTML with embedded iframes for each figure."""

    nav_items = []
    section_blocks = []

    for section_title, figures in SECTIONS:
        section_id = section_title.lower().replace(" ", "-").replace("&", "and")
        nav_items.append(f'<a href="#{section_id}" class="nav-link">{section_title}</a>')

        cards = []
        for fig_title, filename in figures:
            filepath = OUTPUTS / filename
            if filepath.exists():
                cards.append(f"""
                <div class="card">
                    <h3>{fig_title}</h3>
                    <iframe src="outputs/{filename}" loading="lazy"></iframe>
                </div>""")
            else:
                cards.append(f"""
                <div class="card missing">
                    <h3>{fig_title}</h3>
                    <p class="missing-msg">Run the notebook to generate this figure.</p>
                </div>""")

        section_blocks.append(f"""
        <section id="{section_id}">
            <h2>{section_title}</h2>
            <div class="grid">{"".join(cards)}</div>
        </section>""")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AGORA Sponsor Analysis Dashboard</title>
<style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f5f5f5; color: #333; }}
    header {{ background: #1a1a2e; color: white; padding: 1.5rem 2rem; position: sticky; top: 0; z-index: 100; }}
    header h1 {{ font-size: 1.4rem; font-weight: 600; }}
    header p {{ font-size: 0.85rem; opacity: 0.7; margin-top: 0.3rem; }}
    nav {{ background: #16213e; padding: 0.5rem 2rem; display: flex; gap: 1rem;
           position: sticky; top: 72px; z-index: 99; overflow-x: auto; }}
    .nav-link {{ color: #a8b2d1; text-decoration: none; font-size: 0.85rem;
                 padding: 0.4rem 0.8rem; border-radius: 4px; white-space: nowrap; }}
    .nav-link:hover {{ background: rgba(255,255,255,0.1); color: white; }}
    main {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem; }}
    section {{ margin-bottom: 2rem; }}
    section h2 {{ font-size: 1.2rem; margin-bottom: 1rem; padding-bottom: 0.5rem;
                  border-bottom: 2px solid #ddd; }}
    .grid {{ display: grid; grid-template-columns: 1fr; gap: 1rem; }}
    .card {{ background: white; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
             overflow: hidden; }}
    .card h3 {{ font-size: 0.9rem; padding: 0.8rem 1rem 0.5rem; color: #555; }}
    .card iframe {{ width: 100%; height: 500px; border: none; }}
    .card.missing {{ opacity: 0.5; }}
    .missing-msg {{ padding: 2rem; text-align: center; color: #999; font-style: italic; }}
    @media (min-width: 1000px) {{
        .grid {{ grid-template-columns: 1fr 1fr; }}
        .card iframe {{ height: 550px; }}
    }}
</style>
</head>
<body>
<header>
    <h1>AGORA Sponsor Analysis Dashboard</h1>
    <p>Comprehensive study of AI policy cosponsorship networks in the US Congress</p>
</header>
<nav>{"".join(nav_items)}</nav>
<main>{"".join(section_blocks)}</main>
</body>
</html>"""

    DASHBOARD.write_text(html)
    print(f"Dashboard written to {DASHBOARD}")
    print(f"  Open: file://{DASHBOARD.resolve()}")

    # Report which figures are missing
    missing = []
    for _, figures in SECTIONS:
        for _, filename in figures:
            if not (OUTPUTS / filename).exists():
                missing.append(filename)
    if missing:
        print(f"\n  Missing figures ({len(missing)}):")
        for m in missing:
            print(f"    - {m}")
    else:
        print("  All figures present.")


if __name__ == "__main__":
    build_dashboard()
