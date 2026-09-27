import secrets
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from app.config import get_settings

basic = HTTPBasic(auto_error=False)

def require_owner(credentials: HTTPBasicCredentials | None = Depends(basic)):
    settings = get_settings()
    if not settings.dashboard_password:
        raise HTTPException(503, "Owner access is not configured. Set DASHBOARD_PASSWORD in Railway variables.")
    valid_user = secrets.compare_digest((credentials.username if credentials else "").encode(), settings.dashboard_username.encode())
    valid_password = secrets.compare_digest((credentials.password if credentials else "").encode(), settings.dashboard_password.encode())
    if not (valid_user and valid_password):
        raise HTTPException(401, "Owner sign-in required", headers={"WWW-Authenticate": 'Basic realm="villa28-energy"'})
