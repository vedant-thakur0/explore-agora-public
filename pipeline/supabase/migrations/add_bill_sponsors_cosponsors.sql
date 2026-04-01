CREATE TABLE IF NOT EXISTS bill_sponsors (
  agora_id              INTEGER PRIMARY KEY REFERENCES agora_documents(agora_id),
  api_call_url          TEXT,
  party_code            TEXT,
  party_name            TEXT,
  policy_area           TEXT,
  latest_action         TEXT,
  cosponsor_count       INTEGER,
  cosponsor_count_all   INTEGER,
  cosponsor_count_current INTEGER,
  cosponsor_names_current TEXT,
  cosponsor_list_json   JSONB
);

CREATE TABLE IF NOT EXISTS bill_cosponsors (
  id          SERIAL PRIMARY KEY,
  agora_id    INTEGER NOT NULL REFERENCES agora_documents(agora_id),
  bioguide_id TEXT NOT NULL,
  full_name   TEXT,
  first_name  TEXT,
  middle_name TEXT,
  last_name   TEXT,
  party       TEXT,
  state       TEXT,
  district    TEXT,
  sponsorship_date DATE,
  is_original      BOOLEAN,
  withdrawn_date   DATE,
  is_withdrawn     BOOLEAN NOT NULL DEFAULT FALSE,
  UNIQUE (agora_id, bioguide_id)
);
