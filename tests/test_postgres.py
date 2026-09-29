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
            assert conn.scalar(text('SELECT COUNT(*) FROM schema_migrations')) == 5
            assert conn.scalar(text('SELECT COUNT(*) FROM thermostat_readings')) == 0
            conn.execute(text("INSERT INTO solar_readings(installation_id, installation_name, grid_import_daily, grid_export_daily, provider_time) VALUES ('test', 'Test plant', 1.5, 2.5, '20260927100000')"))
            assert conn.scalar(text("SELECT state FROM presence_state WHERE id=1")) == 'UNKNOWN'
            conn.execute(text("INSERT INTO thermostat_readings(device_id, target_heat_temperature, source) VALUES ('test', 20, 'poll')"))
        # Exercise the actual fulfillment handler concurrently against PostgreSQL.
        import asyncio, json
        from datetime import datetime, timedelta
        from starlette.requests import Request
        from app.home_presence import fulfillment, digest
        from app.models import HomeCredential
        from app.config import get_settings
        monkeypatch.setattr(get_settings(), 'home_project_id', 'test-presence')
        monkeypatch.setattr(get_settings(), 'home_client_secret', 'x'*40)
        database.SessionLocal.configure(bind=engine)
        with database.SessionLocal() as db:
            db.add(HomeCredential(token_hash=digest('test-access'),kind='access',family='test',expires_at=datetime.utcnow()+timedelta(hours=1),payload='{}'))
            db.commit()
        body=json.dumps({'requestId':'duplicate','inputs':[{'intent':'action.devices.EXECUTE','payload':{'commands':[{'devices':[{'id':'villa28-presence'}],'execution':[{'command':'action.devices.commands.OnOff','params':{'on':True}}]}]}}]}).encode()
        def deliver(_):
            async def receive(): return {'type':'http.request','body':body,'more_body':False}
            request=Request({'type':'http','headers':[(b'authorization',b'Bearer test-access')]}, receive)
            return asyncio.run(fulfillment(request))
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses=list(pool.map(deliver,range(4)))
        assert all(r==responses[0] for r in responses)
        with engine.connect() as conn:
            assert conn.scalar(text('SELECT COUNT(*) FROM presence_events')) == 1
            assert conn.scalar(text('SELECT COUNT(*) FROM home_receipts')) == 1
            assert conn.scalar(text('SELECT state FROM presence_state WHERE id=1')) == 'AWAY'
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f'DROP SCHEMA {schema} CASCADE'))
        admin.dispose()
