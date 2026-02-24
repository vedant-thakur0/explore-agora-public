from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent.parent
PIPELINE_DIR = BASE_DIR
RAW_DIR = BASE_DIR / "raw"
NORMALIZED_DIR = BASE_DIR / "normalized"
FULLTEXT_DIR = BASE_DIR / "fulltext"
RUNS_DIR = BASE_DIR / "runs"
REVIEW_EXPORTS_DIR = BASE_DIR / "review_exports"

DEFAULT_API_URL = "https://api.congress.gov/v3/bill"
DEFAULT_SCORE_THRESHOLD = 0.35

KEYWORD_GROUPS = {
    "ai_terms": {
        "weight": 0.45,
        "terms": [
            "artificial intelligence",
            "machine learning",
            "foundation model",
            "generative ai",
            "neural network",
            "algorithmic",
            "automated decision",
            "large language model",
        ],
    },
    "governance_terms": {
        "weight": 0.35,
        "terms": [
            "risk management",
            "evaluation",
            "audit",
            "standards",
            "transparency",
            "safety",
            "security",
            "oversight",
            "benchmark",
            "federal agency",
            "procurement",
        ],
    },
    "use_case_terms": {
        "weight": 0.20,
        "terms": [
            "autonomous",
            "biometric",
            "facial recognition",
            "surveillance",
            "cybersecurity",
            "critical infrastructure",
            "workforce",
            "defense",
            "healthcare",
        ],
    },
}

METADATA_PRIOR_TERMS = {
    "committee": ["science", "technology", "judiciary", "homeland", "armed services", "commerce"],
    "bill_type": ["hr", "s", "hjres", "sjres"],
}
