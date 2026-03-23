from __future__ import annotations

from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
PIPELINE_DIR = BASE_DIR
RAW_DIR = BASE_DIR / "raw"
NORMALIZED_DIR = BASE_DIR / "normalized"
FULLTEXT_DIR = BASE_DIR.parent / "data" / "fulltext"
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

# Web / annotation UI
WEB_DIR = BASE_DIR / "web"
ENTITY_DICTIONARY_PATH = AGENTS_OUTPUT_DIR / "entity_dictionary.jsonl"
MANUAL_ANNOTATIONS_DIR = AGENTS_OUTPUT_DIR / "manual_annotations"
# AGORA dataset
DATA_DIR = PROJECT_ROOT / "data"
DOCUMENTS_CSV_PATH = DATA_DIR / "documents.csv"
SEGMENTS_CSV_PATH = DATA_DIR / "segments.csv"
AUTHORITIES_CSV_PATH = DATA_DIR / "authorities.csv"
COLLECTIONS_CSV_PATH = DATA_DIR / "collections.csv"

# Zenodo
ZENODO_RECORD_ID = "19046110"  # https://doi.org/10.5281/zenodo.19046110

# Supabase sync
SUPABASE_BATCH_SIZE = 500

# NER agent
NER_CHUNK_SIZE = 6000          # max chars per section chunk
NER_MAX_PARSING_RULES = 7     # max active rules injected into prompt

#split memory for entity specific ner -> v
NER_MEMORY_TOP_N = {          # max entities injected into prompt context per type
    "organizations": 20,
    "offices": 15,
    "roles": 10,
    "legislation_refs": 15,
    "named_docs": 10,
}

