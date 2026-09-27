-- Additional indexes for performance
CREATE INDEX IF NOT EXISTS idx_thermostat_timestamp ON thermostat_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_solar_timestamp ON solar_readings(timestamp);
CREATE INDEX IF NOT EXISTS idx_events_pubsub ON thermostat_events(pubsub_message_id);
