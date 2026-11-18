"""Registration, login and sessions.

Design, kept deliberately small:
- Passwords: scrypt with a per-user salt (stdlib), minimum 12 characters.
- Sessions: an HMAC-signed cookie (HttpOnly, SameSite=Lax, Secure in production) holding the user id and expiry. The user row is
  re-read on every request, so disabling an account takes effect at once.
- Registration is limited to allowed email domains and every account starts `pending`; an admin approves it. There is no email
  verification, so approval is what stops someone registering with a made-up colleague address.
- The existing BASIC_AUTH_USER / BASIC_AUTH_PASSWORD still work as the break-glass admin: over HTTP Basic (scripts) and on the
  sign-in form (username instead of email). That is how the first admin approves everyone else.
- Five wrong passwords lock the account for 15 minutes.
- No email service, so no self-service "forgot password". An admin resets a password from the Users tab: that sets a one-off
  temporary password (shown to the admin once), clears any lockout, and the person changes it after signing in.
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import User

COOKIE = "fhi_session"
MIN_PASSWORD = 12
MAX_FAILS, LOCK_MINUTES = 5, 15
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
basic = HTTPBasic(auto_error=False)


def hash_password(pw: str) -> str:
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(pw.encode(), salt=salt, n=2 ** 14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(h).decode()


def check_password(pw: str, stored: str) -> bool:
    try:
        _, s, h = stored.split("$")
        got = hashlib.scrypt(pw.encode(), salt=base64.b64decode(s), n=2 ** 14, r=8, p=1, dklen=32)
        return hmac.compare_digest(got, base64.b64decode(h))
    except Exception:  # noqa: BLE001 - a malformed hash is simply a failed login
        return False


_DUMMY = hash_password("not-a-real-password")  # so an unknown email takes as long as a wrong password


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_token(uid: int) -> str:
    body = _b64(json.dumps({"u": uid, "e": int(time.time()) + settings.session_days * 86400}).encode())
    return body + "." + _b64(hmac.new(settings.session_secret, body.encode(), hashlib.sha256).digest())


def read_token(token: str | None) -> int | None:
    try:
        body, sig = (token or "").split(".")
        if not hmac.compare_digest(sig, _b64(hmac.new(settings.session_secret, body.encode(), hashlib.sha256).digest())):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return int(data["u"]) if data["e"] > time.time() else None
    except Exception:  # noqa: BLE001
        return None


@dataclass
class Principal:
    email: str
    name: str | None
    is_admin: bool
    via: str  # session | basic | open


def _admin_ok(user: str, password: str) -> bool:
    return bool(settings.basic_auth_user and settings.basic_auth_password) \
        and secrets.compare_digest(user, settings.basic_auth_user) and secrets.compare_digest(password, settings.basic_auth_password)


def principal(request: Request, creds: HTTPBasicCredentials | None = Depends(basic), db: Session = Depends(get_db)) -> Principal | None:
    if not settings.auth_required:
        return Principal("local", "Local development", True, "open")
    if creds is not None and _admin_ok(creds.username, creds.password):
        return Principal(settings.basic_auth_user, "Admin", True, "basic")
    token = request.cookies.get(COOKIE)
    uid = read_token(token)
    if uid == 0:
        return Principal(settings.basic_auth_user, "Admin", True, "session")
    if uid:
        u = db.get(User, uid)
        if u and u.status == "approved":
            return Principal(u.email, u.name, u.is_admin, "session")
    return None


def require_auth(p: Principal | None = Depends(principal)) -> Principal:
    if p is None:
        if settings.auth_required and not (settings.basic_auth_user and settings.basic_auth_password):
            raise HTTPException(503, "Auth is required but BASIC_AUTH_USER / BASIC_AUTH_PASSWORD are not set")
        raise HTTPException(401, "Sign in required")
    return p


def require_admin(p: Principal = Depends(require_auth)) -> Principal:
    if not p.is_admin:
        raise HTTPException(403, "Admins only")
    return p


def registration_allowed(email: str) -> bool:
    return email in settings.allowed_emails or email.rsplit("@", 1)[-1] in settings.allowed_email_domains


def register(db: Session, email: str, name: str, password: str) -> None:
    email = email.strip().lower()
    if not EMAIL_RE.match(email) or len(email) > 254:
        raise HTTPException(422, "Enter a valid email address")
    if not registration_allowed(email):
        raise HTTPException(403, "Registration is limited to FHI email addresses. Ask Jon to add yours.")
    if len(password) < MIN_PASSWORD:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD} characters")
    if db.execute(select(User).where(User.email == email)).scalar_one_or_none() is None:
        db.add(User(email=email, name=(name or "").strip()[:200] or None, password_hash=hash_password(password), status="pending"))
        db.commit()
    # same response whether or not the address already exists


def login(db: Session, ident: str, password: str) -> tuple[int, str]:
    """Returns (user id or 0 for the break-glass admin, display name). Raises 401/403 with generic messages."""
    ident = ident.strip()
    if _admin_ok(ident, password):
        return 0, "Admin"
    u = db.execute(select(User).where(User.email == ident.lower())).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if u is None:
        check_password(password, _DUMMY)
        raise HTTPException(401, "Wrong email or password")
    locked = u.locked_until and (u.locked_until if u.locked_until.tzinfo else u.locked_until.replace(tzinfo=timezone.utc)) > now
    if locked:
        raise HTTPException(429, f"Too many attempts. Try again in {LOCK_MINUTES} minutes.")
    if not check_password(password, u.password_hash):
        u.failed_logins = (u.failed_logins or 0) + 1
        if u.failed_logins >= MAX_FAILS:
            u.locked_until, u.failed_logins = now + timedelta(minutes=LOCK_MINUTES), 0
        db.commit()
        raise HTTPException(401, "Wrong email or password")
    if u.status == "pending":
        raise HTTPException(403, "Your account is waiting for an admin to approve it.")
    if u.status != "approved":
        raise HTTPException(403, "This account is disabled.")
    u.failed_logins, u.locked_until, u.last_login_at = 0, None, now
    db.commit()
    return u.id, u.name or u.email


def reset_password(db: Session, u: User) -> str:
    """Admin reset: set a random temporary password, clear any lockout, return the password once. Status is left as it is,
    so resetting a pending or disabled account does not approve it."""
    temp = secrets.token_urlsafe(12)  # 16 characters, above MIN_PASSWORD
    u.password_hash, u.failed_logins, u.locked_until = hash_password(temp), 0, None
    db.commit()
    return temp


def change_password(db: Session, u: User, current: str, new: str) -> None:
    """Self-service change. A wrong current password counts towards the same lockout as a wrong sign-in."""
    now = datetime.now(timezone.utc)
    if not check_password(current, u.password_hash):
        u.failed_logins = (u.failed_logins or 0) + 1
        if u.failed_logins >= MAX_FAILS:
            u.locked_until, u.failed_logins = now + timedelta(minutes=LOCK_MINUTES), 0
        db.commit()
        raise HTTPException(422, "Current password is wrong")  # not 401: the page treats 401 as "signed out"
    if len(new) < MIN_PASSWORD:
        raise HTTPException(422, f"Password must be at least {MIN_PASSWORD} characters")
    if new == current:
        raise HTTPException(422, "Choose a different password from the current one")
    u.password_hash, u.failed_logins, u.locked_until = hash_password(new), 0, None
    db.commit()
