CREATE TABLE IF NOT EXISTS thermostat_readings (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL,
    device_name VARCHAR(255),
    ambient_temperature FLOAT,
    target_temperature FLOAT,
    humidity FLOAT,
    hvac_status VARCHAR(50),
    mode VARCHAR(50),
    eco_mode BOOLEAN DEFAULT FALSE,
    connectivity VARCHAR(50),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_device_timestamp ON thermostat_readings(device_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_thermostat_device ON thermostat_readings(device_id);

CREATE TABLE IF NOT EXISTS thermostat_events (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255) NOT NULL,
    event_type VARCHAR(100),
    old_value VARCHAR(255),
    new_value VARCHAR(255),
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    pubsub_message_id VARCHAR(255) UNIQUE
);

CREATE INDEX IF NOT EXISTS idx_events_device ON thermostat_events(device_id);
CREATE INDEX IF NOT EXISTS idx_events_timestamp ON thermostat_events(timestamp);

CREATE TABLE IF NOT EXISTS solar_readings (
    id SERIAL PRIMARY KEY,
    device_id VARCHAR(255),
    installation_id VARCHAR(255) NOT NULL,
    available_generation FLOAT,
    instantaneous_power FLOAT,
    daily_generation FLOAT,
    grid_import_power FLOAT,
    grid_export_power FLOAT,
    battery_power FLOAT,
    battery_soc FLOAT,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_installation_timestamp ON solar_readings(installation_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_solar_device ON solar_readings(device_id);

CREATE TABLE IF NOT EXISTS oauth_tokens (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,
    user_id VARCHAR(255),
    access_token TEXT,
    refresh_token TEXT,
    expires_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_provider ON oauth_tokens(provider);
