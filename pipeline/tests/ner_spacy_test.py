"""
ner_spacy_test.py — spaCy NER comparison against pipeline entity output.

Samples N documents at random, runs spaCy en_core_web_lg over the fulltext,
then computes overlap/divergence with the pipeline's extracted entities.

Usage:
    python3 -m agora.pipeline.tests.ner_spacy_test [--n 20] [--model en_core_web_lg] [--seed 42]

Model setup (first time):
    python3 -m spacy download en_core_web_lg
    # or en_core_web_sm for a lighter model
"""

import spacy  # requires: pip install spacy + python -m spacy download en_core_web_lg

import argparse
import json
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
FULLTEXT_DIR = ROOT / "data" / "fulltext"
ENTITIES_JSONL = ROOT / "pipeline" / "agents" / "output" / "entities.jsonl"

# spaCy entity types we care about (maps spaCy label -> pipeline field)
SPACY_TO_PIPELINE = {
    "ORG": "organizations",
    "LAW": "legislation_refs",
    "PERSON": "roles",        # people often correspond to role holders
    "GPE": "organizations",   # geo-political entities (agencies named by state etc.)
    "NORP": "organizations",  # nationalities/orgs (e.g. "Congressional Democrats")
}

# Pipeline entity fields and the name key for each
PIPELINE_FIELDS = {
    "organizations": "name",
    "offices":       "name",
    "roles":         "title",
    "legislation_refs": "name",
    "named_docs":    "name",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_pipeline_entities() -> dict[str, dict]:
    """Return {agora_id: {field: [name, ...]}} from entities.jsonl."""
    records = {}
    with open(ENTITIES_JSONL) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            aid = str(r["agora_id"])
            records[aid] = {}
            for field, name_key in PIPELINE_FIELDS.items():
                records[aid][field] = [
                    ent[name_key].strip()
                    for ent in r.get(field, [])
                    if isinstance(ent, dict) and ent.get(name_key, "").strip()
                ]
    return records


def fulltext_path(agora_id: str) -> Optional[Path]:
    p = FULLTEXT_DIR / f"{agora_id}.txt"
    return p if p.exists() else None


def spacy_entities(nlp, text: str) -> dict[str, list[str]]:
    """Run spaCy on text, return {spacy_label: [entity_text, ...]} deduplicated."""
    doc = nlp(text[:1_000_000])  # cap at 1M chars to avoid memory issues
    result: dict[str, list[str]] = defaultdict(list)
    seen: dict[str, set] = defaultdict(set)
    for ent in doc.ents:
        label = ent.label_
        text_clean = ent.text.strip()
        if text_clean and text_clean.lower() not in seen[label]:
            result[label].append(text_clean)
            seen[label].add(text_clean.lower())
    return dict(result)


def normalize(name: str) -> str:
    """Lowercase + strip for fuzzy matching."""
    return name.lower().strip()


def overlap(pipeline_names: list[str], spacy_names: list[str]) -> tuple[int, int, int]:
    """Return (matched, pipeline_only, spacy_only) counts using normalized exact match."""
    p_set = {normalize(n) for n in pipeline_names}
    s_set = {normalize(n) for n in spacy_names}
    matched = len(p_set & s_set)
    return matched, len(p_set) - matched, len(s_set) - matched


def partial_match(name: str, name_set: set[str]) -> bool:
    """True if name is a substring of any name in name_set, or vice versa."""
    n = normalize(name)
    for candidate in name_set:
        if n in candidate or candidate in n:
            return True
    return False


# ── Main ───────────────────────────────────────────────────────────────────────

def run(n: int, model: str, seed: int) -> None:
    print(f"spaCy NER Test — model={model}  n={n}  seed={seed}")
    print("=" * 70)

    # Load spaCy model
    try:
        nlp = spacy.load(model)
    except OSError:
        print(f"\n[ERROR] Model '{model}' not found.")
        print(f"  Install with: python3 -m spacy download {model}")
        sys.exit(1)

    # Load pipeline entities and filter to docs with fulltext
    print("Loading pipeline entity records …")
    all_records = load_pipeline_entities()
    available = [
        aid for aid in all_records
        if fulltext_path(aid) is not None
    ]
    print(f"  Pipeline records: {len(all_records)}")
    print(f"  With fulltext: {len(available)}")

    # Sample
    rng = random.Random(seed)
    sample = rng.sample(available, min(n, len(available)))
    print(f"  Sampled: {len(sample)} docs\n")

    # Per-doc results
    results = []
    all_pipeline_only: Counter = Counter()
    all_spacy_only: Counter = Counter()
    all_matched: Counter = Counter()

    for aid in sample:
        fpath = fulltext_path(aid)
        text = fpath.read_text(encoding="utf-8", errors="ignore")
        pipeline = all_records[aid]

        # Run spaCy
        spacy_ents = spacy_entities(nlp, text)

        # Aggregate spaCy ORG/LAW/PERSON into comparison sets
        spacy_orgs = spacy_ents.get("ORG", []) + spacy_ents.get("GPE", []) + spacy_ents.get("NORP", [])
        spacy_law  = spacy_ents.get("LAW", [])
        spacy_per  = spacy_ents.get("PERSON", [])

        # Pipeline sets (flatten all org-like fields)
        pipeline_orgs = pipeline.get("organizations", []) + pipeline.get("offices", [])
        pipeline_law  = pipeline.get("legislation_refs", [])
        pipeline_roles = pipeline.get("roles", [])

        # Overlap counts
        org_m, org_p, org_s = overlap(pipeline_orgs, spacy_orgs)
        law_m, law_p, law_s = overlap(pipeline_law, spacy_law)
        rol_m, rol_p, rol_s = overlap(pipeline_roles, spacy_per)

        # Partial match examples (pipeline entities spaCy missed, with partial hit)
        p_orgs_norm = {normalize(n) for n in pipeline_orgs}
        spacy_miss_exact  = [n for n in pipeline_orgs if normalize(n) not in {normalize(s) for s in spacy_orgs}]
        spacy_miss_partial = [n for n in spacy_miss_exact if not partial_match(n, {normalize(s) for s in spacy_orgs})]

        res = {
            "aid": aid,
            "text_chars": len(text),
            "pipeline": {
                "orgs": len(pipeline_orgs),
                "law": len(pipeline_law),
                "roles": len(pipeline_roles),
            },
            "spacy": {
                "ORG+GPE+NORP": len(spacy_orgs),
                "LAW": len(spacy_law),
                "PERSON": len(spacy_per),
                "all_labels": {k: len(v) for k, v in spacy_ents.items()},
            },
            "overlap": {
                "orgs":  {"matched": org_m, "pipeline_only": org_p, "spacy_only": org_s},
                "law":   {"matched": law_m, "pipeline_only": law_p, "spacy_only": law_s},
                "roles": {"matched": rol_m, "pipeline_only": rol_p, "spacy_only": rol_s},
            },
            "pipeline_orgs_missed_by_spacy": spacy_miss_partial[:10],
            "spacy_orgs_not_in_pipeline": [
                s for s in spacy_orgs
                if not partial_match(s, p_orgs_norm)
            ][:10],
        }
        results.append(res)

        # Aggregate counters
        for name in pipeline_orgs:
            if normalize(name) not in {normalize(s) for s in spacy_orgs}:
                all_pipeline_only[name] += 1
        for name in spacy_orgs:
            if not partial_match(name, {normalize(p) for p in pipeline_orgs}):
                all_spacy_only[name] += 1
        for name in pipeline_orgs:
            if normalize(name) in {normalize(s) for s in spacy_orgs}:
                all_matched[name] += 1

    # ── Print per-doc results ──────────────────────────────────────────────────
    print(f"{'Aid':>6}  {'Chars':>7}  {'P_orgs':>6}  {'S_orgs':>6}  {'Match':>5}  {'P_only':>6}  {'S_only':>6}  {'P_law':>5}  {'S_law':>5}")
    print("-" * 80)
    for r in results:
        o = r["overlap"]
        print(
            f"{r['aid']:>6}  "
            f"{r['text_chars']:>7,}  "
            f"{r['pipeline']['orgs']:>6}  "
            f"{r['spacy']['ORG+GPE+NORP']:>6}  "
            f"{o['orgs']['matched']:>5}  "
            f"{o['orgs']['pipeline_only']:>6}  "
            f"{o['orgs']['spacy_only']:>6}  "
            f"{r['pipeline']['law']:>5}  "
            f"{r['spacy']['LAW']:>5}"
        )

    # ── Aggregate stats ────────────────────────────────────────────────────────
    total_p_orgs = sum(r["pipeline"]["orgs"] for r in results)
    total_s_orgs = sum(r["spacy"]["ORG+GPE+NORP"] for r in results)
    total_match  = sum(r["overlap"]["orgs"]["matched"] for r in results)
    total_p_law  = sum(r["pipeline"]["law"] for r in results)
    total_s_law  = sum(r["spacy"]["LAW"] for r in results)
    total_m_law  = sum(r["overlap"]["law"]["matched"] for r in results)
    total_p_rol  = sum(r["pipeline"]["roles"] for r in results)
    total_s_per  = sum(r["spacy"]["PERSON"] for r in results)
    total_m_rol  = sum(r["overlap"]["roles"]["matched"] for r in results)

    print("\n" + "=" * 70)
    print("AGGREGATE SUMMARY")
    print("=" * 70)
    print(f"\nOrganizations (pipeline orgs+offices  vs  spaCy ORG+GPE+NORP):")
    print(f"  Pipeline total:  {total_p_orgs}")
    print(f"  spaCy total:     {total_s_orgs}")
    print(f"  Exact matches:   {total_match}  ({100*total_match/max(total_p_orgs,1):.1f}% of pipeline)")
    print(f"\nLegislation refs (pipeline  vs  spaCy LAW):")
    print(f"  Pipeline total:  {total_p_law}")
    print(f"  spaCy total:     {total_s_law}")
    print(f"  Exact matches:   {total_m_law}  ({100*total_m_law/max(total_p_law,1):.1f}% of pipeline)")
    print(f"\nRoles (pipeline roles  vs  spaCy PERSON):")
    print(f"  Pipeline total:  {total_p_rol}")
    print(f"  spaCy total:     {total_s_per}")
    print(f"  Exact matches:   {total_m_rol}  ({100*total_m_rol/max(total_p_rol,1):.1f}% of pipeline)")

    # ── Most common pipeline entities missed by spaCy ──────────────────────────
    print(f"\n{'─'*70}")
    print("PIPELINE ORGS/OFFICES MISSED BY spaCy (top 20, across all sampled docs)")
    print(f"{'─'*70}")
    for name, cnt in all_pipeline_only.most_common(20):
        print(f"  {cnt:3d}x  {name}")

    print(f"\n{'─'*70}")
    print("spaCy ORGS NOT IN PIPELINE (top 20, partial-match filtered)")
    print(f"{'─'*70}")
    for name, cnt in all_spacy_only.most_common(20):
        print(f"  {cnt:3d}x  {name}")

    # ── Per-doc spotlight: biggest gaps ───────────────────────────────────────
    print(f"\n{'─'*70}")
    print("PER-DOC SPOTLIGHT — docs with most pipeline entities missed by spaCy")
    print(f"{'─'*70}")
    biggest_gaps = sorted(results, key=lambda r: r["overlap"]["orgs"]["pipeline_only"], reverse=True)[:5]
    for r in biggest_gaps:
        o = r["overlap"]["orgs"]
        print(f"\n  doc {r['aid']}  pipeline_only={o['pipeline_only']}  matched={o['matched']}  spacy_only={o['spacy_only']}")
        if r["pipeline_orgs_missed_by_spacy"]:
            print(f"  Pipeline entities spaCy missed (no partial match):")
            for name in r["pipeline_orgs_missed_by_spacy"][:8]:
                print(f"    - {name}")
        if r["spacy_orgs_not_in_pipeline"]:
            print(f"  spaCy entities not in pipeline:")
            for name in r["spacy_orgs_not_in_pipeline"][:8]:
                print(f"    + {name}")

    # ── spaCy label distribution across all docs ───────────────────────────────
    print(f"\n{'─'*70}")
    print("spaCy ENTITY LABEL DISTRIBUTION (totals across sample)")
    print(f"{'─'*70}")
    label_totals: Counter = Counter()
    for r in results:
        for label, cnt in r["spacy"]["all_labels"].items():
            label_totals[label] += cnt
    for label, cnt in label_totals.most_common():
        print(f"  {cnt:5d}  {label}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="spaCy vs pipeline NER comparison")
    parser.add_argument("--n",     type=int, default=20, help="Number of docs to sample (default 20)")
    parser.add_argument("--model", type=str, default="en_core_web_lg", help="spaCy model name")
    parser.add_argument("--seed",  type=int, default=42, help="Random seed")
    args = parser.parse_args()
    run(args.n, args.model, args.seed)
