from datetime import datetime,timedelta
from types import SimpleNamespace
from app.thermostat_timeline import build_timeline

def row(time,state='COOLING',eco='OFF'):
    return SimpleNamespace(timestamp=time,hvac_status=state,eco_state=eco,connectivity='ONLINE',target_cool_temperature=24,source='poll')

def test_gaps_and_cooling_runtime_are_not_off():
    start=datetime(2026,9,27)
    data=build_timeline([row(start),row(start+timedelta(minutes=5),'OFF'),row(start+timedelta(minutes=30),'COOLING','MANUAL_ECO')],start,start+timedelta(hours=1),600)
    assert data['minutes']=={'COOLING':15,'HEATING':0,'OFF':10,'UNKNOWN':35,'ECO':10}
    assert sum(data['minutes'][x] for x in ['COOLING','HEATING','OFF','UNKNOWN'])==60

def test_carry_in_and_initial_unknown():
    start=datetime(2026,9,27)
    assert build_timeline([],start,start+timedelta(hours=1),600)['minutes']['UNKNOWN']==60
    data=build_timeline([row(start-timedelta(minutes=5))],start,start+timedelta(minutes=10),600)
    assert data['minutes']['COOLING']==5 and data['minutes']['UNKNOWN']==5

def test_offline_is_unknown():
    start=datetime(2026,9,27);r=row(start);r.connectivity='OFFLINE'
    assert build_timeline([r],start,start+timedelta(minutes=5),600)['minutes']['UNKNOWN']==5

def test_timeline_endpoint_validation_and_auth(client):
    assert client.get('/api/thermostat-timeline?day=bad').status_code==422
    assert client.get('/api/thermostat-timeline?day=2999-01-01').status_code==422
    data=client.get('/api/thermostat-timeline?day=2026-01-01').json()
    assert data['timezone']=='Asia/Dubai' and not data['stages_available']
    client.auth=None
    assert client.get('/api/thermostat-timeline').status_code==401
