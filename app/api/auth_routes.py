"""Sign-up, sign-in and account endpoints."""

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from app.api.rate_limit import limiter
from app.api.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    MeResponse,
    RegisterRequest,
    TokenResponse,
)
from app.api.security import require_principal
from app.auth import service
from app.auth.service import AuthError, Principal
from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _token_response(principal: Principal, token: str, expires_at) -> dict:
    return {
        "access_token": token,
        "token_type": "bearer",
        "expires_at": expires_at.isoformat(),
        "username": principal.username,
        "display_name": principal.username,
    }


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.login_rate_limit)
def register(request: Request, response: Response, payload: RegisterRequest):
    """Create an account and sign in immediately."""

    try:
        service.register(payload.username, payload.password, payload.display_name)
        principal, token, expires_at = service.authenticate(payload.username, payload.password)
    except AuthError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    result = _token_response(principal, token, expires_at)
    result["display_name"] = payload.display_name or principal.username

    return result


@router.post("/login", response_model=TokenResponse)
@limiter.limit(settings.login_rate_limit)
def login(request: Request, response: Response, payload: LoginRequest):
    """Exchange a username and password for a bearer token."""

    try:
        principal, token, expires_at = service.authenticate(payload.username, payload.password)
    except AuthError as error:
        # 401, not 400: the credentials were understood and rejected.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(error),
            headers={"WWW-Authenticate": "Bearer"},
        ) from error

    return _token_response(principal, token, expires_at)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    authorization: str | None = Header(default=None),
    _principal: Principal = Depends(require_principal),
):
    """Revoke the presented token."""

    scheme, _, token = (authorization or "").partition(" ")

    if scheme.lower() == "bearer" and token.strip():
        service.revoke_token(token.strip())

    return None


@router.get("/me", response_model=MeResponse)
def me(principal: Principal = Depends(require_principal)):
    return {
        "username": principal.username,
        "display_name": principal.username,
        "is_service_account": principal.is_machine,
    }


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit(settings.login_rate_limit)
def change_password(
    request: Request,
    response: Response,
    payload: ChangePasswordRequest,
    principal: Principal = Depends(require_principal),
):
    """Change the signed-in user's password, invalidating other sessions."""

    if principal.is_machine:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Service accounts have no password to change.",
        )

    try:
        service.change_password(principal.user_id, payload.current_password, payload.new_password)
    except AuthError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error

    return None
