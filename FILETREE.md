# AGORA File Tree

```
./                                   # repository root (AGORA project)
├── .claude/                         # Claude Code skills & plans
├── docs/                            # Maintainer operations guide
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
│   ├── web/                         # Flask UI
│   │   ├── routes/                  # Flask UI routes
│   │   ├── static/                  # Flask UI static assets
│   │   └── templates/               # Flask UI HTML templates
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
│   └── fulltext/                    # ~1,031 plaintext bill files
├── reports/                         # Generated analysis reports: markdown + HTML
│   └── generated/                   # Dated report bundles
├── notebooks/                       # Jupyter notebooks for exploration
│   └── outputs/                     # Committed notebook artifacts
├── hooks/                           # Git/automation hooks
├── NER_AGENT.md                     # NER agent detailed documentation
├── FILETREE.md                      # This file
└── requirements.txt                 # Python dependencies
```
