# AGORA File Tree

```
agora/
├── pipeline/                        # Main pipeline package
│   ├── cli.py                       # CLI entry point
│   ├── config.py                    # All path constants, LLM settings, thresholds
│   ├── models.py                    # Data classes: DocumentRecord, CandidateRecord
│   ├── knowledge_graph.py           # KG community detection, Louvain clustering
│   ├── graph_query.py               # Query KG structure
│   ├── agents/                      # Agent modules
│   │   ├── ner_agent.py             # Named entity extraction
│   │   ├── graph_builder.py         # Graph construction
│   │   ├── community_detector.py    # Community detection
│   │   ├── models_agent.py          # Agent data models
│   │   ├── sponsor_graph.py         # Sponsor relationship graph
│   │   ├── llm_client.py            # Shared LLM client (rate limiting)
│   │   ├── memory/                  # Persistent context across runs
│   │   ├── output/                  # Generated artifacts, entities
│   │   └── checkpoints/             # State saves for resumable runs
│   ├── multiplex_graph/             # Graph community detection output
│   ├── supabase/                    # Supabase integration
│   ├── web/                         # Annotation UI
│   ├── runs/                        # Run manifests (do not delete)
│   ├── datasets/                    # Training/reference artifacts
│   ├── fixtures/                    # Sample data for offline testing
│   └── tests/                       # Unit tests
│
├── knowledge_graph/                 # KG data & documentation
│   ├── README.md                    # Data schema, join keys, limitations
│   └── data/                        # Filtered Congress-only datasets
│
├── fulltext/                        # Plain-text bill fulltext files
├── notebooks/                       # Jupyter notebooks for exploration
├── hooks/                           # Git/automation hooks
├── NER_AGENT.md                     # NER agent detailed documentation
├── FILETREE.md                      # This file
└── requirements.txt                 # Python dependencies
```
