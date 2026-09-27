"""Official international OAuth V2. Credentials never enter URLs or logs."""
from datetime import datetime, timedelta
from threading import RLock
from urllib.parse import urlencode
import requests
from sqlalchemy import select, text
from app.config import get_settings
from app.database import SessionLocal
from app.models import OAuthToken
from app.utils.crypto import encrypt_token, decrypt_token

lock = RLock()

class SungrowError(Exception):
    pass


def post(path, payload, access_token=None):
    settings = get_settings()
    if not settings.sungrow_configured:
        raise SungrowError("Sungrow configuration required")
    headers = {"Content-Type": "application/json", "x-access-key": settings.sungrow_client_secret}
    if access_token:
        headers["Authorization"] = "Bearer " + access_token
    response = requests.post(settings.sungrow_api_url.rstrip("/") + path,
        headers=headers, json={"appkey": settings.sungrow_client_id, **payload}, timeout=25,
        allow_redirects=False)
    response.raise_for_status()
    if response.status_code != 200:
        raise SungrowError("Unexpected Sungrow HTTP response")
    data = response.json()
    if data.get("error") == "invalid_token":
        raise SungrowError("Reconnect Sungrow: token rejected")
    if str(data.get("result_code")) != "1" or not isinstance(data.get("result_data"), dict):
        # Provider error messages may contain credentials or authorization codes.
        raise SungrowError("Sungrow rejected the request")
    return data["result_data"]


class SungrowOAuthFlow:
    @staticmethod
    def get_authorization_url():
        settings = get_settings()
        return "https://web3.isolarcloud.com.hk/#/authorized-app?" + urlencode({
            "cloudId": "2", "applicationId": settings.sungrow_application_id,
            "redirectUrl": settings.sungrow_callback_url})

    @staticmethod
    def exchange_code_for_token(code):
        # One-time codes must never be automatically retried.
        return post("/openapi/apiManage/token", {"grant_type": "authorization_code",
            "code": code, "redirect_uri": get_settings().sungrow_callback_url,
            "token_scope_mode": "authorization_bound"})

    @staticmethod
    def store_token(data):
        if not data.get("access_token"):
            raise SungrowError("Missing access token")
        with lock, SessionLocal.begin() as db:
            if db.bind.dialect.name == "postgresql":
                db.execute(text("SELECT pg_advisory_xact_lock(280030)"))
            token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "sungrow"))
            if token is None:
                token = OAuthToken(provider="sungrow", user_id=str(data.get("auth_user", "primary")))
                db.add(token)
            token.access_token = encrypt_token(data["access_token"])
            if data.get("refresh_token"):
                token.refresh_token = encrypt_token(data["refresh_token"])
            token.expires_at = datetime.utcnow() + timedelta(seconds=int(data.get("expires_in", 3600)))

    @staticmethod
    def get_token():
        with SessionLocal() as db:
            token = db.scalar(select(OAuthToken).where(OAuthToken.provider == "sungrow"))
            if not token:
                return None
            return {"access_token": decrypt_token(token.access_token),
                    "refresh_token": decrypt_token(token.refresh_token) if token.refresh_token else None,
                    "expires_at": token.expires_at}

    @staticmethod
    def access_token():
        with lock:
            token = SungrowOAuthFlow.get_token()
            if not token:
                raise SungrowError("Connect Sungrow first")
            if not token["expires_at"] or token["expires_at"] <= datetime.utcnow() + timedelta(minutes=5):
                if not token["refresh_token"]:
                    raise SungrowError("Reconnect Sungrow")
                # Refresh tokens may rotate: do not retry uncertain submissions.
                data = post("/openapi/apiManage/refreshToken", {"refresh_token": token["refresh_token"]})
                SungrowOAuthFlow.store_token(data)
                token = SungrowOAuthFlow.get_token()
            return token["access_token"]
