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

# Agents / multiplex graph
AGENTS_DIR = BASE_DIR / "agents"
MEMORY_DIR = BASE_DIR / "agents" / "memory"
MULTIPLEX_GRAPH_DIR = BASE_DIR / "multiplex_graph"
AGENTS_OUTPUT_DIR = BASE_DIR / "agents" / "output"
AGENTS_CHECKPOINT_DIR = BASE_DIR / "agents" / "checkpoints"

# LLM
ANTHROPIC_MODEL_BULK = "claude-haiku-4-5-20251001"
ANTHROPIC_RATE_DELAY_SECONDS = 0.65  # ~92 RPM, safely under 100 RPM limit
ANTHROPIC_MAX_RETRIES = 3
ANTHROPIC_RETRY_BASE_DELAY = 2  # seconds; doubles each retry: 2, 4, 8

# Community detection
LOUVAIN_RESOLUTION = 1.5
SIMILARITY_THRESHOLD = 0.25   # minimum edge weight for Louvain graph
DENSE_EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers model
COMMUNITY_SIMILARITY_WEIGHTS = {
    "jaccard_taxonomy": 0.50,
    "cosine_summary": 0.25,
    "dense_cosine": 0.20,
    "cosponsor_jaccard": 0.05,
}
SUBCLUSTERING_SIZE_THRESHOLD = 80   # communities larger than this get sub-clustered
SUBCLUSTERING_RESOLUTION = 2.5      # higher resolution for pass 2

# NER agent
NER_CHUNK_SIZE = 6000          # max chars per section chunk
NER_MAX_PARSING_RULES = 7     # max active rules injected into prompt
NER_MEMORY_TOP_N = {          # max entities injected into prompt context per type
    "organizations": 20,
    "offices": 15,
    "roles": 10,
    "legislation_refs": 15,
    "named_docs": 10,
}

DEFAULT_API_URL = "https://api.congress.gov/v3/bill"
DEFAULT_SCORE_THRESHOLD = 0.35

KEYWORD_GROUPS = {
    "ai_terms": {
        "group_weight": 0.45,
        "min_hits_for_full_credit": 3.0,
        "max_credit": 1.0,
        "terms": [
            {
                "term": "artificial intelligence",
                "aliases": ["ai"],
                "match_type": "phrase",
                "weight": 1.0,
                "polarity": "positive",
            },
            {
                "term": "machine learning",
                "aliases": ["ml"],
                "match_type": "phrase",
                "weight": 1.0,
                "polarity": "positive",
            },
            {
                "term": "foundation model",
                "aliases": ["foundation models"],
                "match_type": "phrase",
                "weight": 1.0,
                "polarity": "positive",
            },
            {
                "term": "generative ai",
                "aliases": ["genai", "gen ai"],
                "match_type": "phrase",
                "weight": 1.0,
                "polarity": "positive",
            },
            {
                "term": "neural network",
                "aliases": ["neural networks"],
                "match_type": "phrase",
                "weight": 0.8,
                "polarity": "positive",
            },
            {
                "term": "algorithmic",
                "aliases": [],
                "match_type": "token",
                "weight": 0.6,
                "polarity": "positive",
            },
            {
                "term": "automated decision",
                "aliases": ["automated decision-making"],
                "match_type": "phrase",
                "weight": 0.9,
                "polarity": "positive",
            },
            {
                "term": "large language model",
                "aliases": ["large language models", "llm", "llms"],
                "match_type": "phrase",
                "weight": 1.0,
                "polarity": "positive",
            },
        ],
    },
    "governance_terms": {
        "group_weight": 0.35,
        "min_hits_for_full_credit": 3.0,
        "max_credit": 1.0,
        "terms": [
            {"term": "risk management", "aliases": [], "match_type": "phrase", "weight": 1.0, "polarity": "positive"},
            {
                "term": "evaluation",
                "aliases": ["conformity assessment", "impact assessment"],
                "match_type": "phrase",
                "weight": 0.9,
                "polarity": "positive",
            },
            {"term": "audit", "aliases": ["auditing"], "match_type": "token", "weight": 0.9, "polarity": "positive"},
            {"term": "standards", "aliases": ["standard"], "match_type": "token", "weight": 0.8, "polarity": "positive"},
            {"term": "transparency", "aliases": [], "match_type": "token", "weight": 0.8, "polarity": "positive"},
            {"term": "safety", "aliases": [], "match_type": "token", "weight": 0.8, "polarity": "positive"},
            {"term": "security", "aliases": ["cybersecurity"], "match_type": "token", "weight": 0.8, "polarity": "positive"},
            {"term": "oversight", "aliases": [], "match_type": "token", "weight": 0.8, "polarity": "positive"},
            {"term": "benchmark", "aliases": ["benchmarks"], "match_type": "token", "weight": 0.7, "polarity": "positive"},
            {
                "term": "federal agency",
                "aliases": ["federal agencies"],
                "match_type": "phrase",
                "weight": 0.8,
                "polarity": "positive",
            },
            {"term": "procurement", "aliases": [], "match_type": "token", "weight": 0.7, "polarity": "positive"},
        ],
    },
    "use_case_terms": {
        "group_weight": 0.20,
        "min_hits_for_full_credit": 2.0,
        "max_credit": 1.0,
        "terms": [
            {"term": "autonomous", "aliases": [], "match_type": "token", "weight": 0.8, "polarity": "positive"},
            {"term": "biometric", "aliases": ["biometrics"], "match_type": "token", "weight": 0.8, "polarity": "positive"},
            {
                "term": "facial recognition",
                "aliases": ["face recognition"],
                "match_type": "phrase",
                "weight": 1.0,
                "polarity": "positive",
            },
            {"term": "surveillance", "aliases": [], "match_type": "token", "weight": 0.9, "polarity": "positive"},
            {"term": "cybersecurity", "aliases": ["cyber security"], "match_type": "phrase", "weight": 0.8, "polarity": "positive"},
            {
                "term": "critical infrastructure",
                "aliases": [],
                "match_type": "phrase",
                "weight": 0.9,
                "polarity": "positive",
            },
            {"term": "workforce", "aliases": [], "match_type": "token", "weight": 0.6, "polarity": "positive"},
            {"term": "defense", "aliases": ["defence"], "match_type": "token", "weight": 0.7, "polarity": "positive"},
            {"term": "healthcare", "aliases": ["health care"], "match_type": "phrase", "weight": 0.8, "polarity": "positive"},
        ],
    },
}

METADATA_PRIOR_TERMS = {
    "committee": ["science", "technology", "judiciary", "homeland", "armed services", "commerce"],
    "bill_type": ["hr", "s", "hjres", "sjres"],
}
