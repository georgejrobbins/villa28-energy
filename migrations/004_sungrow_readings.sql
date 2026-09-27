ALTER TABLE solar_readings ADD COLUMN IF NOT EXISTS installation_name VARCHAR;
ALTER TABLE solar_readings ADD COLUMN IF NOT EXISTS provider_time VARCHAR;
ALTER TABLE solar_readings ADD COLUMN IF NOT EXISTS grid_import_daily DOUBLE PRECISION;
ALTER TABLE solar_readings ADD COLUMN IF NOT EXISTS grid_export_daily DOUBLE PRECISION;
