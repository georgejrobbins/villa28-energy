from datetime import datetime, timedelta
from urllib.parse import urlparse,parse_qs
from unittest.mock import Mock
from pathlib import Path
import json
import pytest
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import ThermostatReading, ThermostatEvent, SolarReading, OAuthToken
from app.google.sdm_client import SDMClient
from app.google.auth import GoogleOAuthFlow
from app.google.pubsub_handler import process_event, message_callback
from app.utils.crypto import encrypt_token, decrypt_token, encryption_ready


def reading(**kwargs):
    result=dict(device_id='zone1', device_name='Living room', ambient_temperature=24, target_temperature=22,target_heat_temperature=None,target_cool_temperature=22,humidity=50,hvac_status='COOLING',mode='COOL',eco_mode=False,eco_state='OFF',connectivity='ONLINE',timestamp=datetime.utcnow(),source='poll')
    result.update(kwargs);return ThermostatReading(**result)

def event(stamp=None, event_id='event-1', traits=None):
    return {'eventId':event_id,'timestamp':(stamp or datetime.utcnow()).isoformat()+'Z','resourceUpdate':{'name':'enterprises/project/devices/zone1','traits':traits or {'sdm.devices.traits.Temperature':{'ambientTemperatureCelsius':25}}}}

def test_health(client):
    client.auth=None
    assert client.get('/health').json()=={'status':'healthy','database':'connected'}

def test_health_failure_returns_503(client,monkeypatch):
    import app.routes.health as module
    monkeypatch.setattr(module.engine,'connect',Mock(side_effect=RuntimeError('private database credentials')))
    response=client.get('/health');assert response.status_code==503
    assert 'private' not in response.text

def test_owner_gate(client):
    assert client.get('/').status_code==200
    client.auth=None
    for path in ['/','/api/current','/api/history','/api/status','/auth/google']:
        assert client.get(path).status_code==401

def test_missing_password_fails_closed(client,monkeypatch):
    monkeypatch.setattr(get_settings(),'dashboard_password','')
    assert client.get('/').status_code==503
    assert client.get('/health').status_code==200

def test_sungrow_paused_no_http(client,monkeypatch):
    import requests
    monkeypatch.setattr(requests,'get',Mock(side_effect=AssertionError('Unexpected request')))
    for path in ['/auth/sungrow','/auth/sungrow/callback']:
        response=client.get(path);assert response.status_code==503
        assert response.json()['status']=='deferred'

def test_current_multiple_zones_and_nulls(client):
    with SessionLocal.begin() as db:
        db.add_all([reading(timestamp=datetime.utcnow()-timedelta(minutes=5)), reading(ambient_temperature=26),reading(device_id='zone2',ambient_temperature=None)])
    rows=client.get('/api/current').json()['thermostats']
    assert len(rows)==2
    assert rows[0]['ambient_temperature']==26
    assert rows[1]['ambient_temperature'] is None
    assert rows[0]['timestamp'].endswith('Z')

def test_history_order_and_validation(client):
    with SessionLocal.begin() as db:
        db.add_all([reading(),reading(timestamp=datetime.utcnow()-timedelta(hours=1))])
    rows=client.get('/api/history?device_id=zone1').json()['thermostats']
    assert len(rows)==2 and rows[0]['timestamp']<=rows[1]['timestamp']
    assert client.get('/api/history?hours=-1').status_code==422
    assert client.get('/api/daily-summary?days=10000').status_code==422

def test_daily_summary_preserves_zero_and_sums_installations(client):
    with SessionLocal.begin() as db:
        for site,generation,power in [('A',5,0),('A',10,100),('B',20,200)]:
            db.add(SolarReading(installation_id=site,daily_generation=generation,instantaneous_power=power,timestamp=datetime.utcnow()))
    summary=client.get('/api/daily-summary').json()['summaries'][0]
    assert summary['total_generation']==30
    assert summary['avg_power']==250

def test_google_official_authorization_and_state(client,monkeypatch):
    response=client.get('/auth/google');assert response.status_code==200
    url=urlparse(response.json()['auth_url']);params=parse_qs(url.query)
    assert url.netloc=='nestservices.google.com'
    assert url.path=='/partnerconnections/test-project/auth'
    state=params['state'][0]
    monkeypatch.setattr(GoogleOAuthFlow,'exchange_code_for_token',lambda code:{'access_token':'test-token','refresh_token':'test-refresh','expires_in':3600})
    assert client.get('/auth/google/callback',params={'code':'test-code','state':'wrong'}).status_code==400
    response=client.get('/auth/google/callback',params={'code':'test-code','state':state},follow_redirects=False)
    assert response.status_code==303
    assert GoogleOAuthFlow.get_token()['refresh_token']=='test-refresh'
    assert client.get('/auth/google/callback',params={'code':'test-code','state':state}).status_code==400
    with SessionLocal() as db:
        token=db.scalar(select(OAuthToken))
        assert 'test-refresh' not in token.refresh_token and 'test-token' not in token.access_token

def test_expired_state(client):
    from app.models import OAuthState
    response=client.get('/auth/google');state=parse_qs(urlparse(response.json()['auth_url']).query)['state'][0]
    with SessionLocal.begin() as db:
        for row in db.scalars(select(OAuthState)):row.expires_at=datetime.utcnow()-timedelta(seconds=1)
    assert client.get('/auth/google/callback',params={'code':'test','state':state}).status_code==400

def test_token_refresh(client,monkeypatch):
    GoogleOAuthFlow.store_token({'access_token':'old','refresh_token':'refresh','expires_in':-1})
    response=Mock();response.json.return_value={'access_token':'new','expires_in':3600}
    import app.google.auth as auth
    monkeypatch.setattr(auth.requests,'post',Mock(return_value=response))
    assert GoogleOAuthFlow.access_token()=='new'
    assert GoogleOAuthFlow.get_token()['refresh_token']=='refresh'

def test_encryption_key_validation(monkeypatch):
    assert decrypt_token(encrypt_token('test'))=='test'
    monkeypatch.setattr(get_settings(),'encryption_key','')
    assert not encryption_ready()
    monkeypatch.setattr(get_settings(),'encryption_key','a'*32)
    assert not encryption_ready()
    monkeypatch.setattr(get_settings(),'encryption_key','test-only-long-secret-1234567890-ABCDE')
    assert decrypt_token(encrypt_token('test'))=='test'

def test_documented_thermostat_fields():
    device={'name':'enterprises/p/devices/id','traits':{
        'sdm.devices.traits.Info':{'customName':'Kitchen'},
        'sdm.devices.traits.ThermostatMode':{'mode':'HEATCOOL'},
        'sdm.devices.traits.ThermostatTemperatureSetpoint':{'heatCelsius':20,'coolCelsius':24}}}
    result=SDMClient.parse_thermostat_reading(device)
    assert result['device_name']=='Kitchen'
    assert result['target_temperature'] is None
    assert result['target_heat_temperature']==20 and result['target_cool_temperature']==24
    assert isinstance(result['timestamp'],datetime)
    device['traits']['sdm.devices.traits.ThermostatMode']['mode']='COOL'
    assert SDMClient.parse_thermostat_reading(device)['target_temperature']==24

def test_event_dedup_and_partial_merge():
    with SessionLocal.begin() as db:db.add(reading(timestamp=datetime.utcnow()-timedelta(minutes=1)))
    data=event()
    assert process_event(data,'message-1')
    assert not process_event(data,'message-1')
    assert not process_event(data,'message-2')
    with SessionLocal() as db:
        assert len(db.scalars(select(ThermostatEvent)).all())==1
        rows=db.scalars(select(ThermostatReading).order_by(ThermostatReading.timestamp)).all()
        assert len(rows)==2 and rows[-1].ambient_temperature==25
        assert rows[-1].humidity==50 and rows[-1].source=='event'

def test_late_event_does_not_overwrite_current():
    with SessionLocal.begin() as db:db.add(reading())
    assert process_event(event(datetime.utcnow()-timedelta(hours=1)),'late')
    with SessionLocal() as db:assert len(db.scalars(select(ThermostatReading)).all())==1

def test_pubsub_ack_after_commit():
    with SessionLocal.begin() as db:db.add(reading(timestamp=datetime.utcnow()-timedelta(minutes=1)))
    message=Mock(data=json.dumps(event()).encode(),message_id='m1')
    message_callback(message);message.ack.assert_called_once();message.nack.assert_not_called()
    invalid=Mock(data=b'not json',message_id='m2')
    message_callback(invalid);invalid.nack.assert_called_once();invalid.ack.assert_not_called()

def test_poll_only_thermostats(monkeypatch):
    response=Mock();response.status_code=200;response.json.return_value={'devices':[{'type':'sdm.devices.types.THERMOSTAT','name':'thermostat'},{'type':'sdm.devices.types.CAMERA','name':'camera'}]}
    monkeypatch.setattr(GoogleOAuthFlow,'access_token',lambda **kw:'test')
    import app.google.sdm_client as module
    monkeypatch.setattr(module.requests,'get',Mock(return_value=response))
    assert len(SDMClient.list_devices())==1
    assert module.requests.get.call_args.args[0]=='https://smartdevicemanagement.googleapis.com/v1/enterprises/test-project/devices'

def test_static_headers(client):
    response=client.get('/')
    assert response.headers['Cache-Control']=='no-store'
    assert response.headers['Referrer-Policy']=='no-referrer'
    assert "frame-ancestors 'none'" in response.headers['Content-Security-Policy']

def test_postgresql_sql_parses():
    from pglast import parse_sql
    for path in (Path(__file__).parents[1]/'migrations').glob('*.sql'):assert parse_sql(path.read_text())

def test_html_and_css_parse():
    import html5lib,tinycss2
    static=Path(__file__).parents[1]/'app/static'
    parser=html5lib.HTMLParser(strict=True);parser.parse((static/'index.html').read_text())
    rules=tinycss2.parse_stylesheet((static/'style.css').read_text(),skip_whitespace=True,skip_comments=True)
    assert all(rule.type!='error' for rule in rules)
