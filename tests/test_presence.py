import re
from urllib.parse import urlparse, parse_qs
from datetime import datetime,timedelta
import pytest
from sqlalchemy import select,func
from app.config import get_settings
from app.database import SessionLocal
from app.models import PresenceState, PresenceEvent, HomeCredential
from app.home_presence import digest, DEVICE

@pytest.fixture(autouse=True)
def setup_presence(monkeypatch):
    monkeypatch.setattr(get_settings(),'home_project_id','test-presence')
    monkeypatch.setattr(get_settings(),'home_client_secret','x'*40)
    with SessionLocal() as db:
        db.add(PresenceState(id=1,state='UNKNOWN'));db.commit()

REDIRECT='https://oauth-redirect.googleusercontent.com/r/test-presence'
def link(client):
    r=client.get('/home/oauth/authorize',params={'client_id':'villa28-google-home','redirect_uri':REDIRECT,'state':'a&b','response_type':'code'})
    assert r.status_code==200
    assert r.headers['referrer-policy']=='origin'
    assert r.headers['cache-control']=='no-store'
    assert r.headers['content-security-policy'].endswith("form-action 'self' " + REDIRECT)
    nonce=re.search('name="nonce" value="([^"]+)"',r.text)[1]
    r=client.post('/home/oauth/authorize',data={'nonce':nonce,'username':'owner','password':'test-only-password'},headers={'Origin':'http://testserver'},follow_redirects=False)
    assert r.status_code==303
    qs=parse_qs(urlparse(r.headers['location']).query);assert qs['state']==['a&b']
    data={'client_id':'villa28-google-home','client_secret':'x'*40,'grant_type':'authorization_code','code':qs['code'][0],'redirect_uri':REDIRECT}
    r=client.post('/home/oauth/token',data=data);assert r.status_code==200
    assert client.post('/home/oauth/token',data=data).json()['error']=='invalid_grant'
    return r.json()
def call(client,tokens,intent,payload=None,request_id='r1'):
    return client.post('/home/fulfillment',auth=None,headers={'Authorization':'Bearer '+tokens['access_token']},json={'requestId':request_id,'inputs':[{'intent':'action.devices.'+intent,'payload':payload or {}}]})
def command(on,device=DEVICE):
    return {'commands':[{'devices':[{'id':device}],'execution':[{'command':'action.devices.commands.OnOff','params':{'on':on}}]}]}
def test_home_flow_and_dedup(client):
    t=link(client)
    assert call(client,t,'SYNC').json()['payload']['devices'][0]['id']==DEVICE
    assert client.get('/api/presence').json()['state']=='UNKNOWN'
    assert call(client,t,'EXECUTE',command(True)).json()['payload']['commands'][0]['status']=='SUCCESS'
    assert call(client,t,'EXECUTE',command(True)).status_code==200
    assert call(client,t,'EXECUTE',command(False),request_id='r2').status_code==200
    data=client.get('/api/presence').json()
    assert data['state']=='HOME'
    assert [e['state'] for e in data['events']]==['AWAY','HOME']
    assert data['segments'][0]['state']=='UNKNOWN'
    assert call(client,t,'QUERY',{'devices':[{'id':DEVICE}]}).json()['payload']['devices'][DEVICE]['on'] is False
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PresenceEvent))==2
        assert db.get(HomeCredential,digest(t['refresh_token'])).kind=='refresh'
    call(client,t,'DISCONNECT')
    assert call(client,t,'SYNC').status_code==401
    assert client.get('/api/presence').json()['state']=='UNKNOWN'
def test_rejects_other_devices_bad_values_and_expired_access(client):
    t=link(client)
    assert call(client,t,'EXECUTE',command(True,'thermostat')).json()['payload']['commands'][0]['errorCode']=='deviceNotFound'
    assert call(client,t,'EXECUTE',command('true'),request_id='r2').json()['payload']['commands'][0]['errorCode']=='valueOutOfRange'
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(PresenceEvent))==0
        db.get(HomeCredential,digest(t['access_token'])).expires_at=datetime.utcnow()-timedelta(seconds=1);db.commit()
    assert call(client,t,'SYNC').status_code==401
    refresh={'client_id':'villa28-google-home','client_secret':'x'*40,'grant_type':'refresh_token','refresh_token':t['refresh_token']}
    r=client.post('/home/oauth/token',data=refresh);assert r.status_code==200
    assert call(client,r.json(),'SYNC').status_code==200
    refresh['client_secret']='wrong';assert client.post('/home/oauth/token',data=refresh).status_code==401

def test_linking_security(client):
    args={'client_id':'villa28-google-home','redirect_uri':'https://evil.example','state':'abc','response_type':'code'}
    assert client.get('/home/oauth/authorize',params=args).status_code==400
    args['redirect_uri']=REDIRECT
    r=client.get('/home/oauth/authorize',params=args)
    nonce=re.search('name="nonce" value="([^"]+)"',r.text)[1]
    assert client.post('/home/oauth/authorize',data={'nonce':nonce,'username':'owner','password':'test-only-password'},headers={'Origin':'https://evil.example'}).status_code==403
    assert client.get('/api/presence',auth=None).status_code==401
    assert client.post('/home/fulfillment',auth=None,json={}).status_code==401
    assert client.get('/api/presence?day=bad').status_code==422
