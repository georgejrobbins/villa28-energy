"""A virtual Google Home switch. Never forwards commands to physical devices."""
import hashlib
import html
import json
import secrets
import uuid
from datetime import datetime, timedelta
from urllib.parse import urlencode, parse_qs
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy import select, delete, func
from app.config import get_settings
from app.database import SessionLocal
from app.models import HomeCredential, PresenceEvent, PresenceState, HomeReceipt
from app.security import require_owner

router = APIRouter()
DEVICE = 'villa28-presence'
CLIENT = 'villa28-google-home'

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def configured():
    s = get_settings()
    return bool(s.home_project_id and len(s.home_client_secret) >= 32)

def require_config():
    if not configured():
        raise HTTPException(503, 'Google Home presence connection is not configured')

def redirect_allowed(uri):
    project = get_settings().home_project_id
    return uri in {f'https://oauth-redirect.googleusercontent.com/r/{project}',
                   f'https://oauth-redirect-sandbox.googleusercontent.com/r/{project}'}

async def form_data(request):
    body = await request.body()
    if len(body) > 16384:
        raise HTTPException(413, 'Request too large')
    if request.headers.get('content-type','').split(';')[0] != 'application/x-www-form-urlencoded':
        raise HTTPException(415, 'Form encoding required')
    values = parse_qs(body.decode(), keep_blank_values=True)
    if any(len(v) != 1 for v in values.values()):
        raise HTTPException(400, 'Duplicate parameters')
    return {k:v[0] for k,v in values.items()}

def credential(db, kind, family, minutes=None, payload=None):
    raw = secrets.token_urlsafe(48)
    db.add(HomeCredential(token_hash=digest(raw), kind=kind, family=family,
        expires_at=datetime.utcnow()+timedelta(minutes=minutes) if minutes else None,
        payload=json.dumps(payload or {})))
    return raw

@router.get('/home/oauth/authorize', response_class=HTMLResponse)
def authorize(client_id: str, redirect_uri: str, state: str, response_type: str):
    require_config()
    if client_id != CLIENT or not redirect_allowed(redirect_uri) or response_type != 'code' or not state or len(state)>4096:
        raise HTTPException(400, 'Invalid authorization request')
    with SessionLocal() as db:
        db.execute(delete(HomeCredential).where(HomeCredential.expires_at < datetime.utcnow()))
        if db.scalar(select(func.count()).select_from(HomeCredential).where(HomeCredential.kind=='consent')) >= 200:
            raise HTTPException(429, 'Too many linking sessions. Try again in ten minutes.')
        nonce = credential(db,'consent',str(uuid.uuid4()),10,{'redirect':redirect_uri,'state':state})
        db.commit()
    response = HTMLResponse('''<!doctype html><html lang="en"><head><meta name="viewport" content="width=device-width,initial-scale=1"><title>Link Villa28 Presence</title><link rel="stylesheet" href="/static/style.css"></head><body><main class="container"><h1>Link Villa28 Presence to Google</h1><p>Sign in with your villa28-energy owner credentials.</p><p>By linking, you authorize Google to control the virtual Away indicator and query its state. Home/Away indicator updates will be stored in your energy dashboard. This does not control any thermostat, HVAC system or inverter.</p><form method="post" action="/home/oauth/authorize"><input type="hidden" name="nonce" value="'''+html.escape(nonce,quote=True)+'''"><p><label>Username <input name="username" autocomplete="username" required></label></p><p><label>Password <input name="password" type="password" autocomplete="current-password" required></label></p><button class="btn" type="submit">Agree and link to Google</button></form><p><a href="/">Cancel</a> · <a href="https://policies.google.com/privacy">Google privacy policy</a> · <a href="https://myaccount.google.com/connections">Manage linked accounts</a></p></main></body></html>''')
    # Preserve the browser's Origin on form POST; no-referrer can make it null.
    # Only the origin is shared, never the OAuth query or state.
    response.headers['Referrer-Policy'] = 'origin'
    response.headers['Cache-Control'] = 'no-store'
    response.set_cookie('home_consent',nonce,httponly=True,secure=get_settings().base_url.startswith('https:'),samesite='lax',max_age=600,path='/home/oauth/authorize')
    return response

@router.post('/home/oauth/authorize')
async def approve(request: Request):
    require_config()
    data = await form_data(request)
    nonce = data.get('nonce','')
    if not nonce or not secrets.compare_digest(nonce,request.cookies.get('home_consent','')) or request.headers.get('origin') != get_settings().base_url:
        raise HTTPException(403,'Invalid linking session. Start linking again.')
    with SessionLocal() as db:
        guard=db.scalar(select(PresenceState).where(PresenceState.id==1).with_for_update())
        now=datetime.utcnow()
        if guard.auth_window and guard.auth_window > now-timedelta(minutes=15) and guard.auth_failures>=10:
            raise HTTPException(429,'Too many sign-in attempts. Try again in 15 minutes.')
        if not guard.auth_window or guard.auth_window <= now-timedelta(minutes=15):
            guard.auth_window=now; guard.auth_failures=0
        record=db.scalar(select(HomeCredential).where(HomeCredential.token_hash==digest(nonce),HomeCredential.kind=='consent').with_for_update())
        if not record or record.expires_at < datetime.utcnow():
            raise HTTPException(400,'Linking session expired')
        details=json.loads(record.payload)
        family=record.family
        db.delete(record)
        # Consume each form nonce even on failure, limiting password attempts per session.
        s=get_settings()
        if not s.dashboard_password or not secrets.compare_digest(data.get('username','').encode(),s.dashboard_username.encode()) or not secrets.compare_digest(data.get('password','').encode(),s.dashboard_password.encode()):
            guard.auth_failures+=1
            db.commit()
            raise HTTPException(401,'Incorrect owner credentials. Start linking again.')
        guard.auth_failures=0
        code=credential(db,'code',family,5,details)
        db.commit()
    response=RedirectResponse(details['redirect']+'?'+urlencode({'code':code,'state':details['state']}),status_code=303)
    response.delete_cookie('home_consent',path='/home/oauth/authorize')
    return response

@router.post('/home/oauth/token')
async def token(request: Request):
    require_config()
    data=await form_data(request)
    if data.get('client_id')!=CLIENT or not secrets.compare_digest(data.get('client_secret','').encode(),get_settings().home_client_secret.encode()):
        return JSONResponse({'error':'invalid_client'},status_code=401)
    grant=data.get('grant_type')
    if grant not in ('authorization_code','refresh_token'):
        return JSONResponse({'error':'unsupported_grant_type'},status_code=400)
    kind='code' if grant=='authorization_code' else 'refresh'
    raw=data.get('code' if kind=='code' else 'refresh_token','')
    with SessionLocal() as db:
        db.scalar(select(PresenceState).where(PresenceState.id==1).with_for_update())
        record=db.scalar(select(HomeCredential).where(HomeCredential.token_hash==digest(raw),HomeCredential.kind==kind).with_for_update())
        if not record or (record.expires_at and record.expires_at<datetime.utcnow()) or (kind=='code' and data.get('redirect_uri')!=json.loads(record.payload)['redirect']):
            return JSONResponse({'error':'invalid_grant'},status_code=400)
        result={'token_type':'Bearer','expires_in':3600,'access_token':credential(db,'access',record.family,60)}
        if kind=='code':
            result['refresh_token']=credential(db,'refresh',record.family)
            db.delete(record)
        db.commit()
        return result

def bearer(request):
    auth=request.headers.get('authorization','')
    if not auth.startswith('Bearer ') or len(auth)>1024:
        raise HTTPException(401,'Invalid bearer token',headers={'WWW-Authenticate':'Bearer'})
    return digest(auth[7:])

@router.post('/home/fulfillment')
async def fulfillment(request: Request):
    require_config()
    token_hash=bearer(request)
    raw=await request.body()
    if len(raw)>65536: raise HTTPException(413,'Request too large')
    try:
        body=json.loads(raw)
        request_id=body['requestId']
        inputs=body['inputs']
        if not isinstance(request_id,str) or not request_id or len(request_id)>256 or len(inputs)!=1: raise ValueError()
        intent=inputs[0]['intent']
        payload=inputs[0].get('payload',{})
        if not isinstance(payload,dict): raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError):
        raise HTTPException(400,'Invalid smart home request')
    with SessionLocal() as db:
        state=db.scalar(select(PresenceState).where(PresenceState.id==1).with_for_update())
        token=db.scalar(select(HomeCredential).where(HomeCredential.token_hash==token_hash,HomeCredential.kind=='access'))
        if not token or token.expires_at<datetime.utcnow(): raise HTTPException(401,'Expired or invalid bearer token')
        # One house row serializes duplicate deliveries and ordering across workers/accounts.
        if not state: raise HTTPException(503,'Presence migration required')
        if intent=='action.devices.DISCONNECT':
            db.execute(delete(HomeCredential).where(HomeCredential.kind.in_(['access','refresh','code'])))
            state.state='UNKNOWN'; state.updated_at=datetime.utcnow()
            db.add(PresenceEvent(state='UNKNOWN',source='disconnect',timestamp=state.updated_at))
            db.commit()
            return {}
        if intent=='action.devices.SYNC':
            return {'requestId':request_id,'payload':{'agentUserId':'villa28-owner','devices':[{'id':DEVICE,'type':'action.devices.types.SWITCH','traits':['action.devices.traits.OnOff'],'name':{'name':'Villa28 Away Indicator'},'willReportState':False,'roomHint':'Monitoring','deviceInfo':{'manufacturer':'Villa28','model':'Presence indicator','swVersion':'1.5.0'}}]}}
        if intent=='action.devices.QUERY':
            result={}
            devices=payload.get('devices',[])
            if not isinstance(devices,list) or any(not isinstance(d,dict) or not isinstance(d.get('id'),str) for d in devices):
                raise HTTPException(400,'Malformed query')
            for d in devices:
                identifier=d.get('id')
                result[identifier]={'status':'SUCCESS','online':True,'on':state.state=='AWAY'} if identifier==DEVICE else {'status':'ERROR','errorCode':'deviceNotFound'}
            return {'requestId':request_id,'payload':{'devices':result}}
        if intent!='action.devices.EXECUTE':
            return {'requestId':request_id,'payload':{'errorCode':'functionNotSupported'}}
        key=digest(token.family+':'+request_id)
        receipt=db.get(HomeReceipt,key)
        if receipt: return json.loads(receipt.response)
        results=[]
        try:
            commands=payload['commands']
            if not isinstance(commands,list) or not 1<=len(commands)<=20: raise ValueError()
            for command in commands:
                executions=command['execution']
                for device in command['devices']:
                    identifier=device['id']
                    result={'ids':[identifier]}
                    if identifier!=DEVICE:
                        result.update(status='ERROR',errorCode='deviceNotFound')
                    elif len(executions)!=1 or executions[0].get('command')!='action.devices.commands.OnOff':
                        result.update(status='ERROR',errorCode='functionNotSupported')
                    elif type(executions[0].get('params',{}).get('on')) is not bool:
                        result.update(status='ERROR',errorCode='valueOutOfRange')
                    else:
                        on=executions[0]['params']['on']
                        state.state='AWAY' if on else 'HOME'; state.updated_at=datetime.utcnow()
                        db.add(PresenceEvent(state=state.state,source='google_home_virtual_switch',timestamp=state.updated_at))
                        result.update(status='SUCCESS',states={'online':True,'on':on})
                    results.append(result)
        except (KeyError,TypeError,ValueError,AttributeError):
            raise HTTPException(400,'Malformed command')
        response={'requestId':request_id,'payload':{'commands':results}}
        db.add(HomeReceipt(request_key=key,response=json.dumps(response)))
        db.commit()
        return response

@router.get('/api/presence',dependencies=[Depends(require_owner)])
def presence(day: str | None = None):
    from zoneinfo import ZoneInfo
    from datetime import timezone
    zone=ZoneInfo('Asia/Dubai')
    now=datetime.utcnow()
    try:
        selected=datetime.strptime(day,'%Y-%m-%d').date() if day else datetime.now(zone).date()
    except ValueError: raise HTTPException(422,'Use YYYY-MM-DD')
    start=datetime.combine(selected,datetime.min.time(),tzinfo=zone).astimezone(timezone.utc).replace(tzinfo=None)
    end=min(start+timedelta(days=1),now)
    if start>=end: raise HTTPException(422,'Choose today or an earlier date')
    with SessionLocal() as db:
        state=db.get(PresenceState,1)
        connected=db.scalar(select(HomeCredential.token_hash).where(HomeCredential.kind=='refresh').limit(1)) is not None
        prior=db.scalar(select(PresenceEvent).where(PresenceEvent.timestamp<start).order_by(PresenceEvent.timestamp.desc(),PresenceEvent.id.desc()).limit(1))
        rows=db.scalars(select(PresenceEvent).where(PresenceEvent.timestamp>=start,PresenceEvent.timestamp<=end).order_by(PresenceEvent.timestamp,PresenceEvent.id)).all()
        current=prior.state if prior else 'UNKNOWN'; cursor=start; segments=[]
        for event in rows:
            if event.timestamp>cursor: segments.append({'state':current,'start':cursor.isoformat()+'Z','end':event.timestamp.isoformat()+'Z'})
            current=event.state; cursor=event.timestamp
        if cursor<end: segments.append({'state':current,'start':cursor.isoformat()+'Z','end':end.isoformat()+'Z'})
        return {'configured':configured(),'connected':connected,'state':state.state if state else 'UNKNOWN','last_received':state.updated_at.isoformat()+'Z' if state and state.updated_at else None,'day':str(selected),'start':start.isoformat()+'Z','end':end.isoformat()+'Z','segments':segments,'events':[{'state':r.state,'timestamp':r.timestamp.isoformat()+'Z','source':r.source} for r in rows], 'note':'Last received virtual indicator state, held until the next event. Missed events are possible. Google does not identify whether a person, voice command or presence automation changed this switch.'}
