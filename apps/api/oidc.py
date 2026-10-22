import base64
import hashlib
import secrets
from datetime import timedelta
from urllib.parse import urlencode
import httpx
import jwt
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, RedirectResponse
from packages.common.config import settings
from packages.common.db import Session, Tenant, now
from packages.common.service import account, Problem

router = APIRouter()


@router.get("/auth/config")
def config():
    return {"development": settings().environment == "development", "execution_mode": settings().execution_mode}


@router.get("/auth/oidc/start")
def start():
    cfg = settings()
    if not cfg.oidc_authorization_url or not cfg.oidc_client_id:
        raise Problem(503, "oidc_not_configured")
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(48)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    data = jwt.encode(
        {
            "state": state,
            "nonce": nonce,
            "verifier": verifier,
            "aud": "oidc-flow",
            "exp": now() + timedelta(minutes=10),
        },
        cfg.secret_key,
        algorithm="HS256",
    )
    url = (
        cfg.oidc_authorization_url
        + "?"
        + urlencode(
            {
                "client_id": cfg.oidc_client_id,
                "response_type": "code",
                "scope": "openid email profile",
                "redirect_uri": cfg.oidc_redirect_uri,
                "state": state,
                "nonce": nonce,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            }
        )
    )
    response = RedirectResponse(url, 303)
    response.set_cookie(
        "if_oidc_flow", data, max_age=600, httponly=True, secure=cfg.environment != "development", samesite="lax"
    )
    return response


@router.get("/auth/oidc/callback")
def callback(request: Request, code: str = "", state: str = ""):
    cfg = settings()
    try:
        flow = jwt.decode(
            request.cookies.get("if_oidc_flow", ""), cfg.secret_key, algorithms=["HS256"], audience="oidc-flow"
        )
        if not secrets.compare_digest(state, flow["state"]) or not code:
            raise ValueError("state")
        with httpx.Client(timeout=20, trust_env=False) as client:
            token_response = client.post(
                cfg.oidc_token_url,
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": cfg.oidc_redirect_uri,
                    "client_id": cfg.oidc_client_id,
                    "client_secret": cfg.oidc_client_secret,
                    "code_verifier": flow["verifier"],
                },
            )
            token_response.raise_for_status()
            raw = token_response.json()["id_token"]
        signing = jwt.PyJWKClient(cfg.oidc_jwks_url).get_signing_key_from_jwt(raw)
        claims = jwt.decode(
            raw,
            signing.key,
            algorithms=["RS256"],
            issuer=cfg.oidc_issuer,
            audience=cfg.oidc_audience,
            options={"require": ["exp", "iss", "sub", "aud", "nonce"]},
        )
        if not secrets.compare_digest(claims["nonce"], flow["nonce"]):
            raise ValueError("nonce")
    except Exception:
        raise Problem(401, "oidc_invalid")
    with Session.begin() as s:
        tenant = account(s, claims["iss"] + ":" + claims["sub"])
    csrf = secrets.token_urlsafe(32)
    session = jwt.encode(
        {"sub": tenant.id, "aud": "dashboard", "csrf": csrf, "exp": now() + timedelta(hours=8)},
        cfg.secret_key,
        algorithm="HS256",
    )
    response = RedirectResponse(cfg.dashboard_url, 303)
    response.delete_cookie("if_oidc_flow")
    response.set_cookie(
        "if_session", session, max_age=28800, httponly=True, secure=cfg.environment != "development", samesite="strict"
    )
    return response


@router.get("/auth/session")
def session(request: Request):
    try:
        claims = jwt.decode(
            request.cookies.get("if_session", ""), settings().secret_key, algorithms=["HS256"], audience="dashboard"
        )
    except jwt.PyJWTError:
        raise Problem(401, "dashboard_session_required")
    with Session.begin() as s:
        if s.get(Tenant, claims["sub"]) is None:
            response = JSONResponse(
                {"error": {"code": "session_expired", "message": "Sign in again", "retryable": False}}, status_code=401
            )
            response.delete_cookie("if_session")
            return response
    return JSONResponse({"csrf_token": claims["csrf"], "mode": settings().execution_mode})
