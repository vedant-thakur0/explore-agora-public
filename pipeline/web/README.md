# AGORA Annotation Web UI

A local Flask app for manually tagging named entities and relationships in AI policy documents.

---

## Setup

```bash
# From the repo root
pip install -r requirements.txt
```

Optional: create a `.env` file in the repo root with Supabase credentials if you want cloud-backed document storage. Without them the app falls back to local files.

```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=your-anon-key
```

---

## Running

```bash
# From the repo root
python -m pipeline.web.app
```

The app starts at **http://localhost:5000**.

---

## Pages

| URL | Purpose |
|-----|---------|
| `/documents` | Browse and filter all documents |
| `/annotate/<agora_id>` | Annotate a specific document |
| `/dictionary` | Browse and manage the entity dictionary |

---

## Annotation Workflow

### 1. Open a document
Go to `/documents`, use the search/filter controls, then click **Annotate** on any row.

### 2. Tag entities
Select text in the left panel. A popover appears — choose the entity type, confirm the name, add any extra fields (acronym, citation, etc.), and click **Add**.

- The selected span is highlighted in the document using the type's color.
- The entity's exact character position is stored, so highlights survive reloads.

### 3. Auto-extract
Click **Auto-Extract** to run the LLM-based NER agent on the document. Results populate the entity panel. You can then edit, remove, or confirm each entity before saving.

### 4. Find related entities
Click any entity card to **select** it:
- The entity's span gets an amber outline (active).
- All entities connected to it via a relationship are highlighted with a dashed amber underline (related).
- Click the same card again to deselect.

### 5. Add relationships
Switch to **Relationship Mode** (toggle at the top of the text panel), then select a passage of text to open the relationship popover. Or stay in Entity Mode and click **+ Add** in the Relationships section.

### 6. Soft aliases (document-local)
Soft aliases let you mark references like "the Commission" or "the Agency" that refer to a specific entity within this document.

1. Click the **~** button on an entity card. A yellow banner appears at the top of the text panel.
2. Select the text in the document that is a soft reference to that entity.
3. The span is added as a soft alias — shown with a dotted underline in the entity's type color.
4. Selecting the entity card highlights all its soft alias spans too.
5. Press **Esc** at any time to cancel soft-alias capture mode.

Soft aliases are stored per-document (in `agents/output/manual_annotations/<agora_id>.json`) and are **not** added to the global entity dictionary.

### 7. Save
Click **Save**. The annotation is written to:
- `agents/output/manual_annotations/<agora_id>.json` — full annotation record
- `agents/output/entities.jsonl` — merged index of all annotations
- `agents/output/entity_dictionary.jsonl` — updated entity counts and aliases

---

## Best Practices

### Ideal workflow for a new document

**1. Skim before tagging.**
Read the document through once (or at least the first few paragraphs and any section headings) before tagging anything. This lets you identify the principal actors early and avoid duplicate or conflicting tags later.

**2. Run Auto-Extract first, then clean up.**
Click **Auto-Extract** to get an LLM-generated first pass. Review each entity card: remove hallucinations, fix names that were partially extracted (e.g. "the Commission" captured instead of the full "Federal Trade Commission"), and add anything the model missed. This is faster than tagging from scratch and catches entities you might skip on a manual read.

**3. Tag entities in order of importance: organizations first.**
Agencies and organizations are the backbone of AI policy documents. Tag them first so they are available when you create relationships and soft aliases. Offices, roles, and legislation refs follow naturally once the org structure is clear.

**4. Use the dictionary before adding a new entity.**
Type in the quick-add bar to see dictionary suggestions. If an entity already exists, select it from the dropdown rather than typing a new name — this keeps canonical names consistent across documents and prevents the dictionary from fragmenting (e.g. "Dept. of Commerce" vs "Department of Commerce").

**5. Handle comma-listed entities with Split mode.**
When the document introduces multiple entities in a list — *"the Bureau of AI, Cybersecurity, and Data"* — select the full list text, click **Split list…** in the popover, confirm the prefix (e.g. `Bureau of`), and add all at once. All resulting entities share the source span, which is accurate: they were introduced together.

**6. Mark soft aliases immediately after introduction.**
When an entity is introduced by full name and then referred to by a shorthand — *"the Commission"*, *"the Office"*, *"it"* — add the soft alias right away while the referent is still clear. Trying to reconstruct aliases at the end of a long document is error-prone. Use the **~** button on the entity card, then select the shorthand text.

**7. Add relationships while context is fresh.**
After tagging a section, switch to **Relationship Mode** and draw relationships from the passage you just read. Don't leave relationship tagging until the end — by then it's hard to remember which passage established the connection.

**8. Click entity cards to audit coverage.**
Select a card to highlight its span and all related entities. This is the fastest way to check: did I capture every mention of this entity? Are the relationships complete? If you see a passage that clearly involves an entity but isn't highlighted, tag it or add a soft alias.

**9. Save frequently.**
There is no autosave. Save after each logical section (e.g. after finishing the preamble, after each article). Losing a session's work is painful.

**10. After annotating a batch of documents, visit the Dictionary.**
Use the `/dictionary` page to merge any near-duplicate entries (e.g. two slightly different spellings of the same agency), set canonical names and acronyms, and export the `canonical_entity_map.json`. This map feeds back into auto-extraction, improving quality on the next batch.

---

## Dictionary

The `/dictionary` page lets you:
- Browse all known entities across all documents
- Edit canonical names, acronyms, and aliases
- Merge two entries into one (useful for deduplication)
- Export a `canonical_entity_map.json` for downstream NER refinement

---

## Data locations

All paths are controlled by `pipeline/config.py`.

| Data | Path |
|------|------|
| Document metadata | `data/documents.csv` or Supabase |
| Fulltexts | `data/fulltext/<agora_id>.txt` or Supabase Storage |
| Annotations | `pipeline/agents/output/manual_annotations/` |
| Entity index | `pipeline/agents/output/entities.jsonl` |
| Entity dictionary | `pipeline/agents/output/entity_dictionary.jsonl` |
| Community labels | `pipeline/agents/output/communities.json` |
