from datetime import datetime, timedelta
from unittest.mock import Mock
import re
import pytest
from sqlalchemy import select
from app.config import get_settings
from app.database import SessionLocal
from app.models import OAuthToken
from app.sungrow.auth import SungrowOAuthFlow, SungrowError, post
from app.sungrow.api_client import SungrowAPIClient

@pytest.fixture
def configured(monkeypatch):
    settings=get_settings()
    monkeypatch.setattr(settings,'sungrow_client_id','test-appkey')
    monkeypatch.setattr(settings,'sungrow_client_secret','test-secret')
    monkeypatch.setattr(settings,'sungrow_api_url','https://gateway.isolarcloud.com.hk')


def test_official_exchange_headers(configured, monkeypatch):
    request=Mock(return_value=Mock(status_code=200,json=lambda:{'result_code':'1','result_data':{'access_token':'test-token'}}))
    monkeypatch.setattr('app.sungrow.auth.requests.post',request)
    SungrowOAuthFlow.exchange_code_for_token('one-time')
    args,kwargs=request.call_args
    assert args[0]=='https://gateway.isolarcloud.com.hk/openapi/apiManage/token'
    assert kwargs['headers']['x-access-key']=='test-secret'
    assert kwargs['json']['appkey']=='test-appkey'
    assert kwargs['json']['token_scope_mode']=='authorization_bound'
    assert kwargs['allow_redirects'] is False
    assert 'test-secret' not in args[0]


def test_callback_requires_confirmation_and_replay_blocked(client, configured, monkeypatch):
    exchange=Mock(return_value={'access_token':'private-access','refresh_token':'private-refresh','expires_in':3600})
    monkeypatch.setattr(SungrowOAuthFlow,'exchange_code_for_token',exchange)
    assert client.get('/auth/sungrow/callback?code=bad').status_code==400
    start=client.get('/auth/sungrow')
    assert 'applicationId=4161' in start.json()['auth_url']
    state=client.cookies.get('sungrow_oauth_state')
    callback=client.get('/auth/sungrow/callback?code=one-time')
    assert callback.status_code==200
    assert callback.headers["referrer-policy"]=="origin"
    assert not exchange.called
    assert client.post('/auth/sungrow/callback',data={'code':'one-time','state':state},headers={'Origin':'https://attacker.invalid'}).status_code==400
    response=client.post('/auth/sungrow/callback',data={'code':'one-time','state':state},headers={'Origin':'http://testserver'},follow_redirects=False)
    assert response.status_code==303
    with SessionLocal() as db:
        token=db.scalar(select(OAuthToken).where(OAuthToken.provider=='sungrow'))
        assert token.access_token!='private-access' and token.refresh_token!='private-refresh'
    assert client.post('/auth/sungrow/callback',data={'code':'one-time','state':state},headers={'Origin':'http://testserver'}).status_code==400
    assert exchange.call_count==1


def test_reading_units_missing_and_zero():
    row=SungrowAPIClient.parse_reading({'ps_id':42,'p83033':'0','p83022':'12500','p83102':'1000','p83072':None,'p83129':'NaN'})
    assert row['instantaneous_power']==0
    assert row['daily_generation']==12.5
    assert row['grid_import_daily']==1
    assert row['grid_export_daily'] is None and row['battery_soc'] is None
    assert 'grid_import_power' not in row


def test_rotating_refresh_is_encrypted(configured, monkeypatch):
    SungrowOAuthFlow.store_token({'access_token':'old','refresh_token':'old-refresh','expires_in':0})
    request=Mock(return_value={'access_token':'new','refresh_token':'new-refresh','expires_in':3600})
    monkeypatch.setattr('app.sungrow.auth.post',request)
    assert SungrowOAuthFlow.access_token()=='new'
    assert SungrowOAuthFlow.get_token()['refresh_token']=='new-refresh'
    assert request.call_args.args[0]=='/openapi/apiManage/refreshToken'


def test_pagination_and_read_only_allowlist(monkeypatch):
    read=Mock(side_effect=[{'pageList':[{'ps_id':i} for i in range(10)],'row_count':11},{'pageList':[{'ps_id':10}],'row_count':11}])
    monkeypatch.setattr(SungrowAPIClient,'read',read)
    assert len(SungrowAPIClient.get_installations())==11
    assert read.call_args.args[1]['page']==2


def test_errors_do_not_expose_provider_secrets(configured,monkeypatch):
    monkeypatch.setattr('app.sungrow.auth.requests.post',Mock(return_value=Mock(status_code=200,json=lambda:{'result_code':'2','result_msg':'private-auth-code'})))
    with pytest.raises(SungrowError) as error:
        SungrowOAuthFlow.exchange_code_for_token('private-auth-code')
    assert 'private-auth-code' not in str(error.value)

@pytest.mark.parametrize('path', ['/openapi/apiManage/token', '/openapi/apiManage/refreshToken'])
@pytest.mark.parametrize('wrapped', [False, True])
def test_both_documented_token_response_formats(configured, monkeypatch, path, wrapped):
    tokens={'access_token':'private-access','refresh_token':'private-refresh','expires_in':172799}
    data={'result_code':'1','result_data':tokens} if wrapped else {'result_code':'1', **tokens}
    monkeypatch.setattr('app.sungrow.auth.requests.post',Mock(return_value=Mock(status_code=200,json=lambda:data)))
    assert post(path,{})['access_token']=='private-access'


def test_failure_with_token_field_is_not_accepted(configured,monkeypatch):
    data={'result_code':'4','result_msg':'secret detail','access_token':'untrusted'}
    monkeypatch.setattr('app.sungrow.auth.requests.post',Mock(return_value=Mock(status_code=200,json=lambda:data)))
    with pytest.raises(SungrowError) as error:
        post('/openapi/apiManage/token',{})
    assert error.value.diagnostic=='result_code_4'
    assert 'secret detail' not in str(error.value)
