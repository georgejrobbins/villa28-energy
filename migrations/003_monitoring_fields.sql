ALTER TABLE thermostat_readings ADD COLUMN IF NOT EXISTS target_heat_temperature FLOAT;
ALTER TABLE thermostat_readings ADD COLUMN IF NOT EXISTS target_cool_temperature FLOAT;
ALTER TABLE thermostat_readings ADD COLUMN IF NOT EXISTS eco_state VARCHAR(50);
ALTER TABLE thermostat_readings ADD COLUMN IF NOT EXISTS source VARCHAR(20) DEFAULT 'poll';
ALTER TABLE thermostat_events ADD COLUMN IF NOT EXISTS provider_event_id VARCHAR(255);
ALTER TABLE thermostat_events ADD COLUMN IF NOT EXISTS payload TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_events_provider_id ON thermostat_events(provider_event_id);
CREATE TABLE IF NOT EXISTS oauth_states (
    state_hash VARCHAR(64) PRIMARY KEY,
    expires_at TIMESTAMP NOT NULL
);
