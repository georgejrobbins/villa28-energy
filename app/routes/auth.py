import hashlib
import secrets
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import delete
from app.config import get_settings
from app.database import SessionLocal
from app.models import OAuthState
from app.google.auth import GoogleOAuthFlow
from app.security import require_owner
from app.utils.crypto import encryption_ready
from app.sungrow.auth import SungrowOAuthFlow
from fastapi.responses import HTMLResponse
from html import escape
from urllib.parse import parse_qs
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/auth/google", dependencies=[Depends(require_owner)])
def google_auth():
    settings = get_settings()
    if not settings.google_configured or not encryption_ready():
        raise HTTPException(503, "Configure Google OAuth, Device Access project ID and a valid ENCRYPTION_KEY in Railway first")
    state = secrets.token_urlsafe(32)
    with SessionLocal.begin() as db:
        db.execute(delete(OAuthState).where(OAuthState.expires_at < datetime.utcnow()))
        db.add(OAuthState(state_hash=hashlib.sha256(state.encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(minutes=10)))
    url, _ = GoogleOAuthFlow.get_authorization_url(state)
    response = JSONResponse({"auth_url": url})
    response.set_cookie("google_oauth_state", state, max_age=600, httponly=True, secure=settings.base_url.startswith("https:"), samesite="lax", path="/auth/google/callback")
    response.headers["Cache-Control"] = "no-store"
    return response

@router.get("/auth/google/callback")
def google_callback(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    cookie = request.cookies.get("google_oauth_state", "")
    if not state or not cookie or not secrets.compare_digest(state, cookie):
        raise HTTPException(400, "Invalid OAuth state. Start Connect Google Nest again.")
    with SessionLocal.begin() as db:
        consumed = db.execute(delete(OAuthState).where(OAuthState.state_hash == hashlib.sha256(state.encode()).hexdigest(), OAuthState.expires_at > datetime.utcnow()).returning(OAuthState.state_hash)).scalar()
    if not consumed:
        raise HTTPException(400, "OAuth request expired or already used")
    if error or not code:
        raise HTTPException(400, "Google authorization was not completed")
    try:
        GoogleOAuthFlow.store_token(GoogleOAuthFlow.exchange_code_for_token(code))
    except Exception as exc:
        logger.error("Google OAuth exchange failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Google authorization failed. Check the registered callback URL and credentials.") from None
    response = RedirectResponse("/?connected=google", status_code=303)
    response.delete_cookie("google_oauth_state", path="/auth/google/callback")
    response.headers["Cache-Control"] = "no-store"
    return response

@router.get("/auth/sungrow", dependencies=[Depends(require_owner)])
def sungrow_auth():
    settings = get_settings()
    if not settings.sungrow_configured or not encryption_ready():
        raise HTTPException(503, "Configure Sungrow appkey, secret and international gateway in Railway first")
    state = secrets.token_urlsafe(32)
    with SessionLocal.begin() as db:
        db.execute(delete(OAuthState).where(OAuthState.expires_at < datetime.utcnow()))
        db.add(OAuthState(state_hash=hashlib.sha256(("sungrow:" + state).encode()).hexdigest(), expires_at=datetime.utcnow() + timedelta(minutes=10)))
    response = JSONResponse({"auth_url": SungrowOAuthFlow.get_authorization_url()})
    response.set_cookie("sungrow_oauth_state", state, max_age=600, httponly=True,
        secure=settings.base_url.startswith("https:"), samesite="lax", path="/auth/sungrow/callback")
    response.headers["Cache-Control"] = "no-store"
    return response

@router.get("/auth/sungrow/callback", dependencies=[Depends(require_owner)])
def sungrow_callback(request: Request, code: str | None = None):
    state = request.cookies.get("sungrow_oauth_state", "")
    if not state or not code or len(code) > 2048:
        raise HTTPException(400, "Start Connect Sungrow from the dashboard and complete authorization first")
    # Sungrow does not document OAuth state echo. Require an explicit same-origin
    # owner POST with a browser-bound nonce before exchanging a callback code.
    with SessionLocal() as db:
        saved = db.get(OAuthState, hashlib.sha256(("sungrow:" + state).encode()).hexdigest())
        if not saved or saved.expires_at <= datetime.utcnow():
            raise HTTPException(400, "Connection request expired. Start Connect Sungrow again.")
    response = HTMLResponse(f"""<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Connect Sungrow</title><link rel="stylesheet" href="/static/style.css"><main class="container"><h1>Confirm Sungrow connection</h1><p>Continue only if you just approved your own installation on iSolarCloud.</p><p>This application reads monitoring data only.</p><form method="post" action="/auth/sungrow/callback"><input type="hidden" name="code" value="{escape(code, quote=True)}"><input type="hidden" name="state" value="{escape(state, quote=True)}"><button class="btn" type="submit">Finish connecting Sungrow</button></form><p><a href="/">Cancel</a></p></main></html>""")
    response.headers.update({"Cache-Control": "no-store", "Referrer-Policy": "origin", "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'"})
    return response

@router.post("/auth/sungrow/callback", dependencies=[Depends(require_owner)])
async def sungrow_confirm(request: Request):
    if request.headers.get("origin") != get_settings().base_url:
        raise HTTPException(400, "Invalid connection origin")
    body = await request.body()
    if len(body) > 8192:
        raise HTTPException(400, "Invalid connection request")
    form = parse_qs(body.decode())
    state = form.get("state", [""])[0]
    code = form.get("code", [""])[0]
    cookie = request.cookies.get("sungrow_oauth_state", "")
    if not code or not state or not cookie or not secrets.compare_digest(state, cookie):
        raise HTTPException(400, "Invalid connection request")
    with SessionLocal.begin() as db:
        consumed = db.execute(delete(OAuthState).where(OAuthState.state_hash == hashlib.sha256(("sungrow:" + state).encode()).hexdigest(), OAuthState.expires_at > datetime.utcnow()).returning(OAuthState.state_hash)).scalar()
    if not consumed:
        raise HTTPException(400, "Connection expired or already used")
    import asyncio
    def exchange():
        SungrowOAuthFlow.store_token(SungrowOAuthFlow.exchange_code_for_token(code))
    try:
        await asyncio.to_thread(exchange)
    except Exception as exc:
        logger.error("Sungrow OAuth exchange failed (%s)", type(exc).__name__)
        raise HTTPException(502, "Sungrow rejected authorization. Start Connect Sungrow again and check Railway credentials.") from None
    response = RedirectResponse("/?connected=sungrow", status_code=303)
    response.delete_cookie("sungrow_oauth_state", path="/auth/sungrow/callback")
    response.headers["Cache-Control"] = "no-store"
    return response
