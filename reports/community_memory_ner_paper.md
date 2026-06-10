# Community-Aware Named Entity Recognition with Hierarchical Shared Memory for Legislative Document Corpora

## Abstract

We present a community-aware named entity recognition (NER) system that leverages document clustering and hierarchical shared memory to extract domain-specific entities from U.S. federal legislative texts. Unlike standard NER approaches that treat documents independently, our system groups documents into thematic communities via graph-based clustering, then processes documents within each community in centrality order, accumulating a persistent memory of discovered entities, disambiguation rules, and structural parsing patterns. A three-tier memory hierarchy---global canonical registry, community-level memory, and ephemeral document context---enables deterministic pre-resolution of known entities before LLM invocation, reducing both token usage and extraction errors. We introduce a progressive rule graduation mechanism with adversarial validation that converts recurring LLM disambiguation patterns into deterministic rules, and a budget-aware context injection algorithm that replaces fixed entity limits with relevance-ranked selection under a token budget. We evaluate on a corpus of 535 AI-related legislative documents from the AGORA dataset across 243 automatically detected communities, with 13 expert-annotated documents spanning 5 entity types. [PLACEHOLDER: Report F1, precision, recall results. Report token savings from pre-resolution. Report graduation rates and hallucination probe rejection rates.]

## 1 Introduction

Named entity recognition in legislative text presents challenges distinct from general-domain NER. Legislative documents reference a dense network of government agencies, offices, roles, statutory citations, and named policy documents, often using ambiguous shorthand forms that require contextual resolution. "The Department" may refer to the Department of Defense in one bill and the Department of Energy in another; "the Secretary" shifts referent across legislative clusters. Standard NER systems---whether fine-tuned sequence labelers or LLM-based extractors---lack the mechanism to accumulate and leverage cross-document context within thematically related document groups.

We address this gap with a community-aware NER architecture that integrates document clustering with persistent, hierarchical memory. Our contributions are:

1. **Community-aware processing order**: Documents are grouped into thematic communities via Louvain clustering over a weighted similarity graph incorporating taxonomy overlap, summary similarity, dense embeddings, and cosponsor overlap. Within each community, documents are processed in centrality order, ensuring high-connectivity documents seed the memory with key entities early.

2. **Three-tier hierarchical memory**: A global canonical registry provides deterministic, rule-based entity resolution; community-level memory accumulates entities and disambiguation rules within each cluster; ephemeral document context tracks in-progress extraction across text chunks. Information flows downward (global knowledge resolves ambiguity locally) and upward (LLM-discovered patterns graduate to deterministic rules after validation).

3. **Progressive rule graduation with adversarial validation**: When an LLM makes the same disambiguation decision $k$ times within a community ($k=5$ by default), the pattern becomes a candidate for deterministic rule graduation. An adversarial hallucination probe---a high-temperature ($T=1.0$) LLM call without memory bias---validates robustness before graduation, preventing the encoding of systematic LLM errors as permanent rules.

4. **Budget-aware context injection**: Rather than injecting a fixed number of entities per type into the LLM prompt (the standard approach), we introduce a character-budget algorithm that ranks context elements across four priority tiers and fills the prompt up to a configurable limit ($B=6000$ characters, approximately 1500 tokens).

5. **Rule-based confidence scoring with human review routing**: A heuristic confidence scorer flags low-confidence extractions for human review without additional LLM calls, enabling efficient annotation triage.

## 2 Related Work

### 2.1 NER in Legislative and Legal Text

[PLACEHOLDER: Cite prior work on legal NER---e.g., Cardellino et al. 2017 on legal NER with CRF; Leitner et al. 2019 on German legal NER; Kalamkar et al. 2022 on Indian legal NER. Discuss domain-specific challenges: nested entities, cross-reference resolution, jurisdiction-specific terminology.]

### 2.2 LLM-Based NER

[PLACEHOLDER: Cite GPT-NER (Wang et al. 2023), PromptNER (Ashok and Lipton 2023), and UniversalNER (Zhou et al. 2023). Discuss limitations: no persistent memory, each document processed independently, context window constraints for long documents.]

### 2.3 Document Clustering for Information Extraction

[PLACEHOLDER: Cite work on cluster-aware IE, topic-conditioned extraction, and community detection in document networks. Louvain method (Blondel et al. 2008). Discuss how document grouping has been used for coreference resolution and entity linking but rarely for NER itself.]

### 2.4 Memory-Augmented Language Models

[PLACEHOLDER: Cite retrieval-augmented generation (Lewis et al. 2020), memory networks (Sukhbaatar et al. 2015), and agent memory systems. Discuss distinction between parametric memory (model weights), non-parametric retrieval (RAG), and our approach of structured, accumulating task memory.]

## 3 System Architecture

### 3.1 Pipeline Overview

The NER agent operates as Phase 3 of a multiplex knowledge graph construction pipeline:

$$\text{Phase 1: Sponsor Graph} \rightarrow \text{Phase 2: Community Detection} \rightarrow \textbf{Phase 3: NER} \rightarrow \text{Phase 4: Graph Assembly}$$

Phase 1 constructs a bipartite sponsor--document graph from congressional sponsorship data. Phase 2 applies Louvain clustering ($\gamma=1.5$) over a weighted document similarity graph to detect 243 thematic communities from 535 documents. The similarity graph combines four signals with learned weights:

| Signal | Weight | Description |
|--------|--------|-------------|
| Jaccard taxonomy overlap | 0.50 | Overlap in AGORA policy tags |
| Cosine summary similarity | 0.25 | TF-IDF vectors of bill summaries |
| Dense embedding cosine | 0.20 | all-MiniLM-L6-v2 sentence embeddings |
| Cosponsor Jaccard | 0.05 | Overlap in congressional cosponsors |

Communities exceeding 80 members undergo sub-clustering at $\gamma=2.5$. The resulting communities range from singletons (204 communities) to groups of 15+ documents, with taxonomy signatures indicating dominant policy themes (e.g., "cybersecurity, defense, intelligence" or "healthcare, AI, data privacy").

### 3.2 Three-Tier Memory Hierarchy

```
Global Canonical Registry (singleton, persisted)
   |  Deterministic rule lookups, entity IDs, type authority
   |
   +-- Rule Engine (aliases, acronyms, graduated disambiguation rules)
   |
Community Memory (per-community, persisted after each document)
   |  Entity roster, local disambiguation, parsing rules, oddities
   |
Document Context (ephemeral, per-document, per-chunk)
      Pre-resolved entities, in-progress extraction state
```

**Global Canonical Registry.** A singleton `GlobalCanonicalRegistry` provides O(1) entity lookup via an inverted index mapping lowercase text variations (canonical names, acronyms, aliases) to canonical entity records. Each `CanonicalEntity` carries:

- `entity_id`: type-prefixed slug (e.g., `org:department_of_defense`)
- `entity_type`: one of 5 types
- `canonical_name`, `acronym`, `aliases`: deterministic lookup keys
- `type_constraints`: enforced type (prevents cross-type confusion)
- `source`: provenance (`seed`, `manual_annotation`, `entity_dictionary`, `llm_graduated`)
- `confidence`: $[0, 1]$, with seeds and manual annotations at 1.0

The registry is seeded from five data sources in priority order: (1) 16 hardcoded federal agency acronym mappings, (2) a curated entity dictionary (29 entries with mention counts and document cross-references), (3) a canonical entity map (text variation $\rightarrow$ entity ID), (4) 13 expert-annotated documents, and (5) a type authority file specifying type corrections (e.g., "Secretary of Defense" must be `roles`, not `organizations`). The seeding pipeline applies type corrections by migrating misclassified entities and setting `type_constraints` to prevent recurrence.

**Community Memory.** Each community maintains a `CommunityMemory` object persisted as JSON after each document:

- `entity_roster`: per-type lists of discovered entities with mention counts and first-seen document IDs
- `disambiguation_rules`: phrase $\rightarrow$ resolved name mappings discovered by the LLM within this community
- `parsing_rules`: up to 7 active structural patterns (e.g., "Bills in this cluster cite existing statutes in subsection (a)"), with older rules archived via 70% token-overlap deduplication
- `oddities`: unusual document structures flagged for review
- `llm_disambiguation_log`: full log of LLM disambiguation decisions, enabling rule graduation analysis
- `entity_confidence`: per-entity confidence scores from heuristic scoring

**Document Context.** Within a single document, ephemeral state tracks: (a) pre-resolved entities identified by regex matching against the registry before LLM invocation, and (b) in-progress entity names accumulated across text chunks for cross-chunk context.

### 3.3 Entity Types

The system extracts five entity types specific to the legislative domain:

| Type | Fields | Graph Relation |
|------|--------|----------------|
| `organizations` | name, acronym, context | MENTIONS\_ORG |
| `offices` | name, parent\_org, context | MENTIONS\_OFFICE |
| `roles` | title, org, context | INVOLVES\_ROLE |
| `legislation_refs` | name, citation, ref\_type, context | REFERENCES\_LEGISLATION |
| `named_docs` | name, doc\_type, owner\_org, context | INVOLVES\_NAMED\_DOC |

The `ref_type` field captures the nature of legislative cross-references (cites, amends, enacts, repeals), enabling downstream graph analysis of legislative dependency chains. The `doc_type` field categorizes named documents (strategy, report, plan, initiative, program).

## 4 Processing Algorithm

### 4.1 Section-Boundary Chunking

Legislative documents follow a structured format with numbered sections (`SEC. 1.`, `SECTION 2.`, etc.) and lettered subsections (`(a)`, `(b)`, etc.). We exploit this structure for semantically coherent chunking:

1. Identify section boundaries via regex: `SEC(?:TION)?\s+\d+[A-Z]?\.`
2. If sections are found, split at section boundaries; sections exceeding $C=6000$ characters are further split at subsection boundaries `\([a-z]\)`.
3. If no section structure is detected, fall back to subsection splitting, then hard character-limit splitting.

This hierarchical approach preserves legislative context within chunks---a section typically addresses a single policy provision, making it a natural extraction unit.

### 4.2 Pre-Resolution

Before invoking the LLM, the system scans each document's full text against the global registry using a compiled regex pattern:

$$P = \texttt{\textbackslash b(?:}t_1|t_2|\ldots|t_n\texttt{)\textbackslash b}$$

where $t_i$ are escaped canonical names, acronyms ($\geq 2$ characters), and aliases ($\geq 3$ characters), sorted by length (longest first) for greedy matching. The regex is compiled once per registry state and cached.

Pre-resolved entities are injected into the LLM prompt as "entities already extracted from earlier sections," reducing the extraction burden to genuinely novel entities. This saves approximately [PLACEHOLDER: measure and report] completion tokens per document for texts with well-known entities.

### 4.3 Budget-Aware Context Injection

The memory context injected into the LLM system prompt is constructed under a character budget $B = 6000$ (~1500 tokens) using a four-tier priority system:

**Tier 1 (Always):** Disambiguation rules from both the global registry (scoped to the current community) and community memory. Format: `"phrase" = resolved_name`. These directly prevent the most common extraction errors.

**Tier 2 (Compact):** Registry entities present in the community's entity roster, rendered in a compact one-line format: `"Department of Defense (DOD) [organization]"`. This provides canonical name resolution context at approximately 20 characters per entity.

**Tier 3 (Fill):** Community-specific entities not in the registry, ranked by mention count. These are entities discovered within the community but not yet globally recognized. Format includes mention counts to signal importance.

**Tier 4 (If Room):** Active parsing rules (up to 7) and recent structural oddities (last 3). These provide document-structure awareness but are deprioritized when the entity context is large.

Each tier fills remaining budget greedily, with per-entry budget checks preventing overflow. This replaces a prior fixed-limit approach that injected up to 70 entity names regardless of relevance (20 organizations + 15 offices + 10 roles + 15 legislation references + 10 named documents).

### 4.4 LLM Extraction

Each chunk is processed by Claude Haiku 4.5 with a domain-specific system prompt instructing JSON-only output, canonical name preference, acronym separation, and agency association for roles. The user prompt includes: document title, summary, the text chunk, and previously extracted entities (pre-resolved + in-progress from earlier chunks).

Output validation requires all five entity type keys with list values. A generic-term filter removes entities with names shorter than 5 characters or matching known generic stems ("federal agencies", "the committee", etc.). A retry mechanism handles JSON parse failures by prepending a strict "return only JSON" instruction.

Rate limiting enforces a 0.65-second delay between API calls (~92 requests per minute), with exponential backoff (2, 4, 8 seconds) on transient errors and a maximum of 3 retries.

### 4.5 Memory Update and Rule Graduation

After each document, the community memory is updated:

1. **Entity merging**: New entities are appended to the roster; known entities have their mention count incremented. The `compute_is_new` function checks both direct name matching and canonical resolution via the registry.

2. **Disambiguation logging**: Each LLM disambiguation decision (from the `disambiguation_updates` field) is appended to `llm_disambiguation_log` with document ID and community ID.

3. **Graduation check**: For each unique (phrase, resolution) pair in the log, if the count $\geq k$ (graduation threshold, default $k=5$):

   a. **Adversarial hallucination probe** (if enabled): A single high-temperature ($T=1.0$) LLM call asks for all plausible interpretations of the ambiguous phrase, given only the community's label and taxonomy signature---critically, *without* the memory context that biased original disambiguations. If the candidate resolution dominates the high-temperature output (appears first or is the only interpretation), the rule passes. If alternative interpretations surface, the rule is routed to a human review queue instead of graduating. If the candidate is entirely absent from the probe output, graduation is rejected.

   b. On passing, a `DisambiguationRule` is created with scope limited to the current community, confidence $\min(0.95, 0.6 + 0.05c)$ where $c$ is the occurrence count, and source `llm_graduated`.

4. **Parsing rules**: New structural patterns are added with 70% token-overlap deduplication; when active rules exceed 7, oldest are archived.

5. **Confidence scoring**: Each extracted entity receives a heuristic confidence score (Section 4.6) and low-confidence entities are queued for review.

The registry is persisted after each community completes, capturing any graduated rules.

### 4.6 Confidence Scoring

A rule-based confidence scorer assigns each extracted entity a score in $[0, 1]$ without additional LLM calls:

| Signal | Weight | Rationale |
|--------|--------|-----------|
| In global registry | +0.3 | Entity is canonically known |
| In community memory | +0.1 | Previously seen in related docs |
| Has acronym | +0.1 | Well-established entities have acronyms |
| Name $<$ 8 characters | $-$0.2 | Short names are often abbreviations or generic |
| Type conflicts with registry | $-$0.3 | Likely misclassification |
| Base score | 0.5 | |

Entities scoring below $\theta = 0.5$ are written to a review queue with explanations, enabling targeted human annotation. This creates an active learning signal: the most uncertain extractions are surfaced for expert review, improving the registry and memory for subsequent runs.

### 4.7 Soft Alias Scoping

A critical design decision concerns the scoping of soft aliases---shortened or contextual references to entities (e.g., "the Secretary," "the Department," "the Director"). These are inherently ambiguous at the corpus level:

- "the Secretary" $\rightarrow$ Secretary of Defense (in defense bills)
- "the Secretary" $\rightarrow$ Secretary of Homeland Security (in DHS bills)
- "the Director" $\rightarrow$ Director of National Intelligence (in intelligence bills)
- "the Director" $\rightarrow$ Director of OMB (in budget bills)

We enforce strict scoping: soft aliases are **never** promoted to the global registry or used as entity aliases. They exist only in: (a) the original annotation files as document-level context, and (b) community memory's `disambiguation_rules` when the LLM discovers the pattern in context. Even graduated rules are initially community-scoped, requiring appearance in $\geq 3$ communities before global promotion.

This prevents a class of silent errors where a disambiguation correct for one legislative cluster contaminates extraction in unrelated clusters.

## 5 Dataset

### 5.1 AGORA Corpus

We use the AGORA dataset (Automated Governance Research and Analysis), a curated collection of U.S. federal legislative documents related to artificial intelligence policy. The corpus contains 1,016 full-text documents, of which 535 are assigned to the 243 communities detected by the clustering pipeline. Documents include bills, resolutions, committee reports, and executive orders, with full text ranging from [PLACEHOLDER: report min/median/max document lengths in tokens].

Each document carries metadata including: official name, short summary, AGORA taxonomy tags (policy area labels such as "cybersecurity," "defense," "healthcare," "transportation"), sponsor information, and cosponsor lists.

### 5.2 Community Structure

[PLACEHOLDER: Report community statistics---size distribution, number of singletons (204), largest communities, taxonomy diversity within communities. Include histogram of community sizes.]

### 5.3 Expert Annotations

We use 13 expert-annotated documents as gold standard, containing:

| Entity Type | Annotated Instances |
|-------------|-------------------|
| Organizations | 36 |
| Offices | 3 |
| Roles | 27 |
| Legislation refs | 3 |
| Named docs | 6 |
| **Total** | **75** |

Annotations include character-level spans (`char_start`, `char_end`), verbatim context snippets, and structured metadata (parent organizations for offices, associated agencies for roles, citation codes for legislation references, document types for named documents). Soft aliases are annotated separately with source entity and type.

[PLACEHOLDER: Report inter-annotator agreement if multiple annotators. Describe annotation guidelines. Report time per document.]

## 6 Experiments

### 6.1 Experimental Setup

[PLACEHOLDER: Describe hardware, API costs, total runtime. Report number of API calls per configuration.]

We evaluate the following configurations:

1. **Baseline (No Memory):** Standard LLM extraction with the system prompt and document text only. No community context, no pre-resolution, no memory accumulation.

2. **Community Memory Only:** Community-level entity roster and disambiguation rules injected into the prompt using the fixed top-N limits (20 orgs, 15 offices, 10 roles, 15 legislation refs, 10 named docs). No global registry.

3. **Full System (Registry + Budget + Graduation):** Three-tier hierarchy with pre-resolution, budget-aware context injection, and progressive rule graduation.

4. **Full System + Hallucination Probe:** Configuration 3 with adversarial validation enabled for rule graduation.

### 6.2 Entity Extraction Quality

[PLACEHOLDER: Table with Precision, Recall, F1 per entity type and per configuration]

| Configuration | Org P/R/F1 | Office P/R/F1 | Role P/R/F1 | Legis P/R/F1 | Doc P/R/F1 | Macro F1 |
|---------------|-----------|--------------|------------|-------------|-----------|----------|
| Baseline | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| +Community Memory | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| +Registry+Budget | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |
| +Hallucination | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |

### 6.3 Type Correctness

[PLACEHOLDER: Report type accuracy---fraction of matched entities with correct type. Focus on the "Secretary of Defense" org/role confusion class. Report improvement from type authority constraints.]

### 6.4 Token Efficiency

[PLACEHOLDER: Report prompt and completion token usage per configuration. Measure pre-resolution savings (entities correctly identified by regex vs. LLM). Report context injection sizes: budget-aware vs. fixed top-N.]

| Configuration | Avg Prompt Tokens | Avg Completion Tokens | Total Cost |
|---------------|------------------|----------------------|------------|
| Baseline | [TBD] | [TBD] | [TBD] |
| +Community Memory | [TBD] | [TBD] | [TBD] |
| +Registry+Budget | [TBD] | [TBD] | [TBD] |

### 6.5 Rule Graduation Analysis

[PLACEHOLDER: Report number of candidate rules generated, graduation rate, hallucination probe rejection rate, review queue size. Analyze graduated rules qualitatively---which disambiguations were correctly graduated? Which were correctly rejected? Any false graduations or false rejections?]

### 6.6 Confidence Scoring Calibration

[PLACEHOLDER: Plot confidence score distribution. Report precision/recall at different confidence thresholds. Measure whether low-confidence entities are disproportionately incorrect. Report review queue effectiveness: of entities flagged for review, what fraction were genuinely problematic?]

### 6.7 Processing Order Effects

[PLACEHOLDER: Compare centrality-first ordering vs. random ordering within communities. Measure how quickly community memory converges (entities stabilized after N documents). Report memory growth curves.]

## 7 Analysis

### 7.1 Community Memory Accumulation Dynamics

[PLACEHOLDER: Analyze how community memory evolves as documents are processed. Plot entity roster size over documents processed. Identify the "seeding phase" (first few high-centrality documents) vs. "refinement phase" (later documents). Show that centrality-first ordering seeds memory faster.]

### 7.2 Disambiguation Rule Quality

[PLACEHOLDER: Manually inspect graduated disambiguation rules. Categorize as: correct and useful, correct but obvious, incorrect (false graduation). Analyze hallucination probe decisions---concordance with human judgment.]

### 7.3 Cross-Community Entity Overlap

[PLACEHOLDER: Analyze which entities appear across multiple communities. Report coverage of the global registry vs. community-specific entities. How many entities are truly community-specific vs. corpus-wide? This motivates the three-tier hierarchy.]

### 7.4 Error Analysis

[PLACEHOLDER: Categorize extraction errors by type: missed entities, hallucinated entities, type confusion, disambiguation failures. Identify systematic patterns. Report per-community error rates---do singleton communities have higher error rates? Do larger communities benefit more from memory?]

### 7.5 Limitations

The current system has several limitations:

1. **Small evaluation set**: 13 annotated documents (2.4% of corpus) limits statistical power. The evaluation serves as a baseline; ongoing annotation of the human review queue will expand coverage.

2. **Community independence**: Communities are currently processed independently. Cross-community entity linking (promotion of community-scoped rules to global scope after appearing in $\geq 3$ communities) is designed but not yet evaluated.

3. **No relationship extraction**: The `relationships` field in entity records exists but is not populated. Adding relationship extraction to the same LLM call is architecturally possible but may reduce entity extraction quality due to attention splitting.

4. **Single-model evaluation**: All experiments use Claude Haiku 4.5. Generalization to other LLMs is untested.

5. **Domain specificity**: The entity types, chunking heuristics, and generic-term filters are designed for U.S. federal legislative text. Adaptation to other legislative systems or legal domains would require schema and prompt modifications.

## 8 Conclusion

We have presented a community-aware NER system that integrates document clustering with hierarchical shared memory to extract domain-specific entities from legislative text. The three-tier memory hierarchy---global canonical registry, community-level memory, and ephemeral document context---enables deterministic pre-resolution of known entities, budget-aware context injection, and progressive rule graduation with adversarial validation. The system processes documents in centrality order within automatically detected communities, accumulating knowledge that improves extraction quality across related documents.

[PLACEHOLDER: Summarize key quantitative results. State improvement over baseline.]

The architecture demonstrates that structured, persistent memory---rather than larger context windows or more powerful models---can substantially improve extraction quality and efficiency in domain-specific NER tasks. The progressive rule graduation mechanism offers a principled path from LLM-dependent disambiguation to deterministic rule-based resolution, with adversarial validation preventing the encoding of systematic errors.

Future work includes: (a) expanding the evaluation set via the active learning review queue, (b) enabling cross-community rule promotion, (c) adding relationship extraction within the existing LLM call, and (d) evaluating generalization to other legislative corpora and legal domains.

## References

[PLACEHOLDER: Add references. Key citations to include:

- AGORA dataset (Engel et al.)
- Blondel, V. D., et al. (2008). Fast unfolding of communities in large networks. (Louvain method)
- Lewis, P., et al. (2020). Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks.
- Wang, S., et al. (2023). GPT-NER: Named Entity Recognition via Large Language Models.
- Zhou, W., et al. (2023). UniversalNER: Targeted Distillation from Large Language Models for Open Named Entity Recognition.
- Anthropic. (2025). Claude model documentation.
- Leitner, E., et al. (2019). Fine-grained Named Entity Recognition in Legal Documents.
- Sukhbaatar, S., et al. (2015). End-To-End Memory Networks.
- Reimers, N. and Gurevych, I. (2019). Sentence-BERT. (for all-MiniLM-L6-v2)
]

## A Appendix: System Prompt

The complete system prompt used for entity extraction:

```
You are a named entity extractor for U.S. federal legislative documents.
You have access to a community memory of entities already found in related documents.
Rules:
1. Return ONLY valid JSON. No prose, no markdown fences.
2. Use the community context to resolve ambiguous references ("the Department", "the Director").
3. Only extract explicitly named entities --- skip generic terms like "federal agencies".
4. Add disambiguation_updates ONLY for phrases you resolved using this document's text.
5. Prefer full canonical names; put acronyms in the acronym field.
6. For roles: always include the associated agency.
7. Return empty lists for types with no entities found.
8. If you observe a new structural pattern, include it in new_parsing_rule.
9. If the document has unusual structure, describe it in oddity.
```

## B Appendix: Hallucination Probe Prompt

The adversarial validation prompt used to challenge candidate disambiguation rules:

```
System: You are analyzing ambiguous phrases in U.S. federal legislative documents.
Given an ambiguous phrase and the document context, list ALL plausible entity
interpretations with confidence scores (0-1). Be exhaustive --- consider every
possible referent.

User: Legislative cluster: "{community_label}"
Topics: {taxonomy_tags}

The phrase "{phrase}" appears in documents from this cluster.

List all plausible entities this phrase could refer to, with confidence scores:
Format: ENTITY_NAME (confidence: 0.X)
```

## C Appendix: Entity Output Schema

```json
{
  "organizations": [{"name": "...", "acronym": "...", "context": "verbatim <= 100 chars"}],
  "offices": [{"name": "...", "parent_org": "...", "context": "..."}],
  "roles": [{"title": "...", "org": "...", "context": "..."}],
  "legislation_refs": [{"name": "...", "citation": "...",
                         "ref_type": "cites|amends|enacts|repeals|other",
                         "context": "..."}],
  "named_docs": [{"name": "...",
                   "doc_type": "strategy|report|plan|initiative|program|other",
                   "owner_org": "...", "context": "..."}],
  "disambiguation_updates": {"phrase": "resolved_name"},
  "new_parsing_rule": null,
  "oddity": null
}
```

## D Appendix: Confidence Scoring Formula

$$\text{conf}(e) = \text{clamp}\left(0.5 + 0.3 \cdot \mathbb{1}[\text{registry}] + 0.1 \cdot \mathbb{1}[\text{memory}] + 0.1 \cdot \mathbb{1}[\text{acronym}] - 0.2 \cdot \mathbb{1}[|e| < 8] - 0.3 \cdot \mathbb{1}[\text{type\_conflict}], \ 0, \ 1\right)$$

where $\mathbb{1}[\cdot]$ denotes indicator functions for each condition.
