from datetime import datetime, timedelta
from threading import RLock
from urllib.parse import urlencode, quote
import secrets
import requests
from sqlalchemy import select, text
from app.config import get_settings
from app.database import SessionLocal
from app.models import OAuthToken
from app.utils.crypto import encrypt_token, decrypt_token
from app.utils.retry import retry_with_backoff

lock = RLock()

class GoogleOAuthFlow:
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    @staticmethod
    def get_authorization_url(state=None):
        settings = get_settings()
        state = state or secrets.token_urlsafe(32)
        params = {"client_id": settings.google_client_id, "redirect_uri": settings.google_callback_url,
                  "response_type": "code", "access_type": "offline", "prompt": "consent",
                  "scope": "https://www.googleapis.com/auth/sdm.service", "state": state}
        return f"https://nestservices.google.com/partnerconnections/{quote(settings.device_access_project_id, safe='')}/auth?{urlencode(params)}", state

    @staticmethod
    def exchange_code_for_token(code):
        settings = get_settings()
        # Authorization codes are single-use: do not automatically retry exchanges.
        response = requests.post(GoogleOAuthFlow.TOKEN_URL, data={"client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret, "code": code,
            "grant_type": "authorization_code", "redirect_uri": settings.google_callback_url}, timeout=20)
        response.raise_for_status()
        return response.json()

    @staticmethod
    def store_token(data):
        with lock, SessionLocal.begin() as db:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(280029)"))
            token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "google").order_by(OAuthToken.id))
            if token is None:
                token = OAuthToken(provider="google", user_id="primary")
                db.add(token)
            token.access_token = encrypt_token(data["access_token"])
            if data.get("refresh_token"):
                token.refresh_token = encrypt_token(data["refresh_token"])
            token.expires_at = datetime.utcnow() + timedelta(seconds=data.get("expires_in", 3600))

    @staticmethod
    def get_token():
        with SessionLocal() as db:
            token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "google").order_by(OAuthToken.id))
            if not token:
                return None
            return {"access_token": decrypt_token(token.access_token),
                    "refresh_token": decrypt_token(token.refresh_token) if token.refresh_token else None,
                    "expires_at": token.expires_at}

    @staticmethod
    @retry_with_backoff()
    def refresh_access_token():
        token = GoogleOAuthFlow.get_token()
        if not token or not token["refresh_token"]:
            raise ValueError("Reconnect Google Nest to obtain a refresh token")
        settings = get_settings()
        response = requests.post(GoogleOAuthFlow.TOKEN_URL, data={"client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret, "refresh_token": token["refresh_token"],
            "grant_type": "refresh_token"}, timeout=20)
        response.raise_for_status()
        GoogleOAuthFlow.store_token(response.json())

    @staticmethod
    def access_token(force_refresh=False):
        with lock:
            token = GoogleOAuthFlow.get_token()
            if not token:
                raise ValueError("Connect Google Nest first")
            if force_refresh or not token["expires_at"] or token["expires_at"] <= datetime.utcnow() + timedelta(seconds=60):
                GoogleOAuthFlow.refresh_access_token()
                token = GoogleOAuthFlow.get_token()
            return token["access_token"]
