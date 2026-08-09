-- Hermes sales pipeline CRM schema. Idempotent: safe to run on every pipeline start.
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS companies (
    id            INTEGER PRIMARY KEY,
    name          TEXT NOT NULL,
    domain        TEXT NOT NULL UNIQUE,          -- dedupe key
    website       TEXT,
    industry      TEXT,
    size          TEXT,                          -- e.g. "11-50", "200+"
    location      TEXT,
    services      TEXT,                          -- what they sell/do, short summary
    source_query  TEXT,                          -- search query that surfaced them
    discovered_at TEXT NOT NULL DEFAULT (datetime('now')),
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS contacts (
    id           INTEGER PRIMARY KEY,
    company_id   INTEGER NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    name         TEXT,
    role         TEXT,
    email        TEXT,
    phone        TEXT,
    linkedin     TEXT,
    email_status TEXT NOT NULL DEFAULT 'unverified',  -- unverified|format_ok|domain_ok|mx_ok|invalid
    phone_status TEXT NOT NULL DEFAULT 'unverified',  -- unverified|format_ok|invalid
    is_primary   INTEGER NOT NULL DEFAULT 0,
    source_url   TEXT,                                -- public page the contact came from
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(company_id, email)
);

CREATE TABLE IF NOT EXISTS leads (
    id              INTEGER PRIMARY KEY,
    company_id      INTEGER NOT NULL UNIQUE REFERENCES companies(id) ON DELETE CASCADE,
    stage           TEXT NOT NULL DEFAULT 'discovered',
    -- discovered -> researched -> verified -> qualified | rejected
    -- -> outreach_drafted -> outreach_sent -> replied_interested | replied_not_now
    --    | replied_reject -> won | lost | unsubscribed
    score           INTEGER,                     -- 0-100
    tier            TEXT,                        -- hot|warm|cold
    icp_pass        INTEGER,                     -- 1 pass / 0 reject
    icp_reasons     TEXT,                        -- JSON array of matched/failed rules
    pain_hypothesis TEXT,                        -- from sales-researcher
    do_not_contact  INTEGER NOT NULL DEFAULT 0,  -- opt-out flag: never draft/send when 1
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS outreach (
    id            INTEGER PRIMARY KEY,
    lead_id       INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    contact_id    INTEGER REFERENCES contacts(id),
    channel       TEXT NOT NULL,                 -- email|whatsapp|linkedin
    sequence_step INTEGER NOT NULL DEFAULT 0,    -- 0=first touch, 1=day3, 2=day7, 3=day14
    subject       TEXT,
    body          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'draft', -- draft|approved|sent|failed|discarded
    outbox_path   TEXT,                          -- staged file in $HERMES_HOME/outbox/
    drafted_at    TEXT NOT NULL DEFAULT (datetime('now')),
    approved_at   TEXT,
    sent_at       TEXT
);

CREATE TABLE IF NOT EXISTS responses (
    id          INTEGER PRIMARY KEY,
    lead_id     INTEGER NOT NULL REFERENCES leads(id) ON DELETE CASCADE,
    channel     TEXT,
    received_at TEXT NOT NULL DEFAULT (datetime('now')),
    body        TEXT,
    intent      TEXT,                            -- interested|not_now|reject|unsubscribe|other
    handled     INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    id          INTEGER PRIMARY KEY,
    run_at      TEXT NOT NULL DEFAULT (datetime('now')),
    discovered  INTEGER NOT NULL DEFAULT 0,
    researched  INTEGER NOT NULL DEFAULT 0,
    verified    INTEGER NOT NULL DEFAULT 0,
    qualified   INTEGER NOT NULL DEFAULT 0,
    rejected    INTEGER NOT NULL DEFAULT 0,
    hot         INTEGER NOT NULL DEFAULT 0,
    warm        INTEGER NOT NULL DEFAULT 0,
    cold        INTEGER NOT NULL DEFAULT 0,
    drafts      INTEGER NOT NULL DEFAULT 0,
    notes       TEXT
);

CREATE INDEX IF NOT EXISTS idx_leads_stage       ON leads(stage);
CREATE INDEX IF NOT EXISTS idx_leads_tier        ON leads(tier);
CREATE INDEX IF NOT EXISTS idx_outreach_status   ON outreach(status);
CREATE INDEX IF NOT EXISTS idx_outreach_lead     ON outreach(lead_id, sequence_step);
CREATE INDEX IF NOT EXISTS idx_contacts_company  ON contacts(company_id);
CREATE INDEX IF NOT EXISTS idx_responses_lead    ON responses(lead_id);

-- Keep updated_at fresh on lead transitions.
CREATE TRIGGER IF NOT EXISTS trg_leads_updated
AFTER UPDATE ON leads
BEGIN
    UPDATE leads SET updated_at = datetime('now') WHERE id = NEW.id;
END;
