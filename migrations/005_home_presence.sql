CREATE TABLE home_credentials (
 token_hash VARCHAR(64) PRIMARY KEY,
 kind TEXT NOT NULL,
 family TEXT NOT NULL,
 expires_at TIMESTAMP,
 payload TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX ix_home_credentials_family ON home_credentials(family);
CREATE TABLE presence_state (
 id INTEGER PRIMARY KEY CHECK (id = 1),
 state TEXT NOT NULL CHECK (state IN ('HOME','AWAY','UNKNOWN')),
 auth_window TIMESTAMP,
 auth_failures INTEGER NOT NULL DEFAULT 0,
 updated_at TIMESTAMP
);
INSERT INTO presence_state(id, state) VALUES (1, 'UNKNOWN');
CREATE TABLE presence_events (
 id SERIAL PRIMARY KEY,
 state TEXT NOT NULL CHECK (state IN ('HOME','AWAY','UNKNOWN')),
 source TEXT NOT NULL,
 timestamp TIMESTAMP NOT NULL
);
CREATE INDEX ix_presence_events_timestamp ON presence_events(timestamp);
CREATE TABLE home_receipts (request_key VARCHAR(64) PRIMARY KEY, response TEXT NOT NULL);
