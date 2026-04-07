-- NER Entity Dictionary Table
-- Stores canonical entities extracted from legislation
CREATE TABLE IF NOT EXISTS ner_entities (
  entity_id              TEXT PRIMARY KEY,
  entity_type            TEXT NOT NULL,
  canonical_name         TEXT NOT NULL,
  acronym                TEXT,
  aliases                TEXT[] DEFAULT '{}',
  soft_aliases           TEXT[] DEFAULT '{}',
  metadata               JSONB DEFAULT '{}'::jsonb,
  mention_count          INTEGER DEFAULT 0,
  first_seen             TEXT,
  created_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  updated_at             TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  CONSTRAINT valid_entity_type CHECK (entity_type IN ('organizations', 'offices', 'roles', 'legislation_refs', 'named_docs'))
);

-- Document Entities Mapping Table
-- Maps entities found in each document to the canonical entity dictionary
CREATE TABLE IF NOT EXISTS doc_entities (
  doc_entity_id         BIGSERIAL PRIMARY KEY,
  agora_id              INTEGER NOT NULL REFERENCES agora_documents(agora_id) ON DELETE CASCADE,
  entity_id             TEXT NOT NULL REFERENCES ner_entities(entity_id) ON DELETE CASCADE,
  entity_type           TEXT NOT NULL,
  mention_count         INTEGER DEFAULT 1,
  char_positions        JSONB,
  contexts              JSONB,
  created_at            TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
  UNIQUE(agora_id, entity_id)
);

-- Indices for performance
CREATE INDEX IF NOT EXISTS idx_ner_entities_type ON ner_entities(entity_type);
CREATE INDEX IF NOT EXISTS idx_ner_entities_canonical ON ner_entities(canonical_name);
CREATE INDEX IF NOT EXISTS idx_doc_entities_agora ON doc_entities(agora_id);
CREATE INDEX IF NOT EXISTS idx_doc_entities_entity ON doc_entities(entity_id);
CREATE INDEX IF NOT EXISTS idx_doc_entities_type ON doc_entities(entity_type);
