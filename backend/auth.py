import secrets
import time
from collections import defaultdict
from datetime import UTC, datetime
from functools import lru_cache
from ipaddress import ip_address, ip_network

from argon2 import PasswordHasher
from fastapi import HTTPException, Request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_config
from .models import Profile, UserIdentity

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


def ensure_pin_identity(db: Session, profile: Profile) -> UserIdentity:
    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == "pin", UserIdentity.user_id == profile.id
        )
    )
    if not identity:
        identity = UserIdentity(
            user_id=profile.id,
            provider="pin",
            provider_subject=f"profile:{profile.id}",
            provider_display_name=profile.display_name,
        )
        db.add(identity)
    return identity


def auth_mode() -> str:
    cfg = get_config()
    mode = cfg.auth_mode.lower()
    if mode not in {"pin", "home_assistant", "auto"}:
        raise RuntimeError("AUTH_MODE must be pin, home_assistant, or auto")
    return mode


def home_assistant_enabled() -> bool:
    cfg = get_config()
    return cfg.deployment_mode.lower() == "home_assistant" and auth_mode() in {
        "home_assistant",
        "auto",
    }


def trusted_home_assistant_request(request: Request) -> bool:
    if not home_assistant_enabled():
        return False
    host = request.client.host if request.client else ""
    trusted = [value.strip() for value in get_config().ha_trusted_proxies.split(",") if value.strip()]
    if host in trusted:
        return True
    try:
        address = ip_address(host)
        return any(address in ip_network(value, strict=False) for value in trusted)
    except ValueError:
        return False


def profile_for_home_assistant(request: Request, db: Session) -> Profile | None:
    if not trusted_home_assistant_request(request):
        return None
    subject = request.headers.get("X-Remote-User-Id", "").strip()
    if not subject:
        raise HTTPException(401, "Home Assistant identity is unavailable")
    identity = db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == "home_assistant",
            UserIdentity.provider_subject == subject,
        )
    )
    now = datetime.now(UTC)
    username = request.headers.get("X-Remote-User-Name")
    display_name = request.headers.get("X-Remote-User-Display-Name") or username
    if identity:
        identity.provider_username = username
        identity.provider_display_name = display_name
        identity.updated_at = now
        identity.last_login_at = now
        profile = db.get(Profile, identity.user_id)
        if display_name:
            profile.display_name = display_name.strip()[:80]
        db.commit()
        return profile
    profile = Profile(
        display_name=(display_name or "Home Assistant user").strip()[:80],
        timezone=get_config().default_timezone,
        timezone_source="default",
        is_admin=False,
        onboarding_completed=False,
        must_change_pin=False,
    )
    db.add(profile)
    db.flush()
    db.add(
        UserIdentity(
            user_id=profile.id,
            provider="home_assistant",
            provider_subject=subject,
            provider_username=username,
            provider_display_name=display_name,
            last_login_at=now,
        )
    )
    db.commit()
    return profile


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
        payload = serializer().loads(token, max_age=get_config().keep_signed_in_days * 86400)
    except (BadSignature, SignatureExpired) as exc:
        raise HTTPException(401, "Session expired") from exc
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        csrf = request.headers.get("X-CSRF-Token")
        cookie = request.cookies.get("health_csrf")
        if not csrf or not cookie or not secrets.compare_digest(csrf, cookie):
            raise HTTPException(403, "Invalid CSRF token")
    return payload
