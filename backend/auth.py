import secrets
import time
from collections import defaultdict
from functools import lru_cache

from argon2 import PasswordHasher
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_config
from .models import Profile

hasher = PasswordHasher()
attempts: dict[str, list[float]] = defaultdict(list)


@lru_cache
def configured_hash() -> str | None:
    pin = get_config().app_pin
    return hasher.hash(pin) if pin else None


def active_pin_hash(db: Session) -> str | None:
    profile_id = db.info.get("profile_id")
    profile = db.get(Profile, profile_id) if profile_id else db.scalar(select(Profile))
    return profile.pin_hash if profile and profile.pin_hash else configured_hash()


def profile_for_pin(db: Session, pin: str) -> Profile | None:
    for profile in db.scalars(select(Profile).where(Profile.onboarding_completed.is_(True))):
        if profile.pin_hash and verify_pin(pin, profile.pin_hash):
            return profile
    configured = configured_hash()
    if configured and verify_pin(pin, configured):
        return db.scalar(select(Profile).order_by(Profile.id))
    return None


def pin_is_available(db: Session, pin: str, excluding_profile_id: int | None = None) -> bool:
    return all(
        profile.id == excluding_profile_id
        or not profile.pin_hash
        or not verify_pin(pin, profile.pin_hash)
        for profile in db.scalars(select(Profile))
    )


def hash_pin(pin: str) -> str:
    return hasher.hash(pin)


def verify_pin(pin: str, pin_hash: str | None) -> bool:
    if not pin_hash:
        return True
    try:
        return hasher.verify(pin_hash, pin)
    except Exception:
        return False


def check_rate_limit(ip: str):
    cutoff = time.time() - 900
    attempts[ip] = [x for x in attempts[ip] if x > cutoff]
    if len(attempts[ip]) >= 5:
        raise HTTPException(429, "Too many failed attempts. Try again in 15 minutes.")


def record_failure(ip: str):
    attempts[ip].append(time.time())


def serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(get_config().session_secret, salt="health-os-session")


def csrf_token() -> str:
    return secrets.token_urlsafe(24)


def require_session(request: Request, pin_required: bool):
    if not pin_required:
        return
    token = request.cookies.get("health_session")
    if not token:
        raise HTTPException(401, "PIN required")
    try:
        return serializer().loads(token, max_age=get_config().keep_signed_in_days * 86400)
    except (BadSignature, SignatureExpired) as exc:
        raise HTTPException(401, "Session expired") from exc
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token")
        cookie = request.cookies.get("health_csrf")
        if not csrf or not cookie or not secrets.compare_digest(csrf, cookie):
            raise HTTPException(403, "Invalid CSRF token")
