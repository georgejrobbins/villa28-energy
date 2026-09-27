import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from sqlalchemy import create_engine, text
from app import database

@pytest.mark.skipif(not os.getenv('TEST_POSTGRES_URL'), reason='PostgreSQL integration connection not supplied')
def test_postgres_migrations_repeat_and_serialize(monkeypatch):
    url = os.environ['TEST_POSTGRES_URL']
    schema = 'test_' + uuid.uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f'CREATE SCHEMA {schema}'))
    engine = create_engine(url, connect_args={'options': f'-c search_path={schema}'})
    monkeypatch.setattr(database, 'engine', engine)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            list(pool.map(lambda _: database.init_db(), range(2)))
        database.init_db()
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT COUNT(*) FROM schema_migrations')) == 4
            assert conn.scalar(text('SELECT COUNT(*) FROM thermostat_readings')) == 0
            conn.execute(text("INSERT INTO solar_readings(installation_id, installation_name, grid_import_daily, grid_export_daily, provider_time) VALUES ('test', 'Test plant', 1.5, 2.5, '20260927100000')"))
            conn.execute(text("INSERT INTO thermostat_readings(device_id, target_heat_temperature, source) VALUES ('test', 20, 'poll')"))
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()
