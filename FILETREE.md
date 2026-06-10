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
│   ├── FEC/                         # FEC ingestion experiments — currently placeholder
│   ├── graph/                       # Sponsor/cosponsor graph edges, nodes, stats
│   ├── runs/                        # Run manifests (do not delete)
│   ├── datasets/                    # Training/reference artifacts
│   ├── fixtures/                    # Sample data for offline testing
│   └── tests/                       # Unit tests
│
├── knowledge_graph/                 # KG data & documentation
│   ├── README.md                    # Data schema, join keys, limitations
│   └── graph_data/                  # Filtered Congress-only datasets
│
├── data/                            # Full AGORA corpus data
│   └── fulltext/                    # ~1,016 plaintext bill files
├── reports/                         # Generated analysis reports: markdown + HTML
├── exploratory reports/             # Exploratory tag/party alignment analyses
├── notebooks/                       # Jupyter notebooks for exploration
├── plans/                           # Planning documents
├── hooks/                           # Git/automation hooks
├── NER_AGENT.md                     # NER agent detailed documentation
├── FILETREE.md                      # This file
└── requirements.txt                 # Python dependencies
```
