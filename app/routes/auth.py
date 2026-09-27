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
from app.sungrow.api_client import REQUIRED_DOCUMENTATION
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
@router.get("/auth/sungrow/callback", dependencies=[Depends(require_owner)])
def sungrow_deferred():
    return JSONResponse(status_code=503, content={"status": "deferred", "message": "Sungrow is paused until its official Developer API details are verified.", "required_documentation": REQUIRED_DOCUMENTATION})
