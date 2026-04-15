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

# Graph data
GRAPH_DATA_DIR = PROJECT_ROOT / "knowledge_graph" / "graph_data"
COSPONSOR_CSV_PATH = GRAPH_DATA_DIR / "agora_cosponsors_long.csv"
SPONSORS_CSV_PATH = GRAPH_DATA_DIR / "agora_comprehensive_data_with_cosponsor_lists.csv"

# Supabase
import os as _os
SUPABASE_URL = _os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = _os.getenv("SUPABASE_KEY", "")
SUPABASE_BUCKET_FULLTEXTS = "fulltexts"
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

# Shared memory system (canonical registry)
GLOBAL_REGISTRY_PATH = AGENTS_OUTPUT_DIR / "global_registry.json"
TYPE_AUTHORITY_PATH = AGENTS_OUTPUT_DIR / "type_authority.json"
CANONICAL_ENTITY_MAP_PATH = AGENTS_OUTPUT_DIR / "canonical_entity_map.json"
REVIEW_QUEUE_PATH = AGENTS_OUTPUT_DIR / "review_queue.jsonl"
CANONICALIZED_ENTITIES_PATH = AGENTS_OUTPUT_DIR / "entities_canonicalized.jsonl"
COMMUNITIES_PATH = AGENTS_OUTPUT_DIR / "communities.json"
CONTEXT_BUDGET_CHARS = 6000    # max chars for memory context injection (~1500 tokens)
CONFIDENCE_REVIEW_THRESHOLD = 0.5  # entities below this -> review queue

# Rule graduation thresholds
GRADUATION_THRESHOLD = 5       # consistent LLM disambiguations before rule graduation
GLOBAL_SCOPE_THRESHOLD = 3     # communities before community rule becomes global

# Hallucination probe (adversarial validation for rule graduation)
HALLUCINATION_PROBE_ENABLED = True
HALLUCINATION_TEMPERATURE = 1.0
HALLUCINATION_PASS_THRESHOLD = 0.8   # fraction of high-temp outputs matching candidate
HALLUCINATION_SAMPLE_DOCS = 3        # source docs to probe per candidate rule

