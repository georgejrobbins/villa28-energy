import os
from pathlib import Path
import sys
import pytest
from cryptography.fernet import Fernet
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(DATABASE_URL='sqlite://', DASHBOARD_PASSWORD='test-only-password', ENCRYPTION_KEY=Fernet.generate_key().decode(), GOOGLE_CLIENT_ID='test-client', GOOGLE_CLIENT_SECRET='test-secret', GOOGLE_DEVICE_ACCESS_PROJECT_ID='test-project', BACKGROUND_TASKS_ENABLED='false', PUBLIC_BASE_URL='http://testserver')
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from app import database
import app.models
from app.main import app
from fastapi.testclient import TestClient

@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread':False}, poolclass=StaticPool)
    database.Base.metadata.create_all(engine)
    database.SessionLocal.configure(bind=engine)
    monkeypatch.setattr(database,'engine',engine)
    import app.routes.health as health
    import app.main as main
    monkeypatch.setattr(health,'engine',engine)
    monkeypatch.setattr(main,'init_db',lambda:None)
    yield
    engine.dispose()

@pytest.fixture
def client():
    with TestClient(app) as client:
        client.auth=('owner','test-only-password')
        yield client
