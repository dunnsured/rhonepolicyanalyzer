"""Local JWT-based authentication module.

Uses SQLite for persistent user storage, bcrypt for password hashing,
and PyJWT for token generation/validation. Manages per-user data isolation
for analyses, reports, and monitoring.
"""

import logging
import os
import secrets
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import bcrypt
import jwt
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# JWT configuration
# ---------------------------------------------------------------------------
# Secret key for signing JWTs — persisted to file so tokens survive restarts
def _load_or_create_jwt_secret() -> str:
    secret_file = Path(__file__).resolve().parent.parent / "data" / ".jwt_secret"
    secret_file.parent.mkdir(parents=True, exist_ok=True)
    if secret_file.exists():
        return secret_file.read_text().strip()
    secret = os.environ.get("JWT_SECRET", secrets.token_hex(32))
    secret_file.write_text(secret)
    return secret

JWT_SECRET = _load_or_create_jwt_secret()
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_SECONDS = 3600  # 1 hour
REFRESH_TOKEN_EXPIRE_SECONDS = 86400 * 7  # 7 days

# ---------------------------------------------------------------------------
# SQLite database
# ---------------------------------------------------------------------------
DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "users.db"


def _get_db() -> sqlite3.Connection:
    """Get a SQLite connection, creating the database and table if needed."""
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        )
    """)
    conn.commit()
    return conn


# Initialize database on module load
_get_db().close()
logger.info("User database initialized at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class AuthUser:
    """Authenticated user."""
    id: str
    email: str
    display_name: str = ""
    created_at: str = ""


# ---------------------------------------------------------------------------
# User CRUD operations
# ---------------------------------------------------------------------------

def create_user(email: str, password: str, display_name: str = "") -> AuthUser:
    """Create a new user account. Raises HTTPException on duplicate email."""
    email = email.strip().lower()
    if not email or "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")

    user_id = str(uuid.uuid4())
    now = time.time()
    password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

    conn = _get_db()
    try:
        conn.execute(
            "INSERT INTO users (id, email, password_hash, display_name, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, email, password_hash, display_name or email.split("@")[0], now),
        )
        conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="An account with this email already exists.")
    finally:
        conn.close()

    logger.info("Created user: %s (%s)", email, user_id)
    return AuthUser(
        id=user_id,
        email=email,
        display_name=display_name or email.split("@")[0],
        created_at=str(now),
    )


def authenticate_user(email: str, password: str) -> AuthUser:
    """Authenticate a user by email and password. Raises HTTPException on failure."""
    email = email.strip().lower()

    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    finally:
        conn.close()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    if not bcrypt.checkpw(password.encode("utf-8"), row["password_hash"].encode("utf-8")):
        raise HTTPException(status_code=401, detail="Invalid email or password.")

    return AuthUser(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        created_at=str(row["created_at"]),
    )


def get_user_by_id(user_id: str) -> Optional[AuthUser]:
    """Look up a user by ID. Returns None if not found."""
    conn = _get_db()
    try:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    return AuthUser(
        id=row["id"],
        email=row["email"],
        display_name=row["display_name"],
        created_at=str(row["created_at"]),
    )


# ---------------------------------------------------------------------------
# JWT token generation and validation
# ---------------------------------------------------------------------------

def generate_tokens(user: AuthUser) -> dict:
    """Generate access and refresh tokens for a user."""
    now = time.time()

    access_payload = {
        "sub": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "type": "access",
        "iat": now,
        "exp": now + ACCESS_TOKEN_EXPIRE_SECONDS,
    }
    refresh_payload = {
        "sub": user.id,
        "type": "refresh",
        "iat": now,
        "exp": now + REFRESH_TOKEN_EXPIRE_SECONDS,
    }

    access_token = jwt.encode(access_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    refresh_token = jwt.encode(refresh_payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_SECONDS,
    }


def validate_access_token(token: str) -> AuthUser:
    """Validate an access token and return the AuthUser. Raises HTTPException on failure."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token. Please log in again.")

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid token payload.")

    return AuthUser(
        id=user_id,
        email=payload.get("email", ""),
        display_name=payload.get("display_name", ""),
        created_at="",
    )


def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh token to generate new access and refresh tokens."""
    try:
        payload = jwt.decode(refresh_token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired. Please log in again.")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid refresh token.")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type.")

    user_id = payload.get("sub")
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found.")

    return generate_tokens(user)


# ---------------------------------------------------------------------------
# FastAPI dependency — extract and validate token from request
# ---------------------------------------------------------------------------

async def get_current_user(request: Request) -> AuthUser:
    """Extract and validate the auth token from the request.

    Checks Authorization header (Bearer token) first, then query parameter,
    then cookie.
    """
    token = None

    # Check Authorization header
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]

    # Fallback to query parameter (needed for SSE EventSource and <a> downloads)
    if not token:
        token = request.query_params.get("token")

    # Fallback to cookie
    if not token:
        token = request.cookies.get("access_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return validate_access_token(token)


# ---------------------------------------------------------------------------
# Per-user data store
# ---------------------------------------------------------------------------

@dataclass
class UserDataStore:
    """In-memory per-user data store for analyses and reports."""
    # analysis_id -> PolicyAnalysis
    analyses: dict = field(default_factory=dict)
    # analysis_id -> AnalysisStatusResponse
    statuses: dict = field(default_factory=dict)
    # analysis_id -> Path (local report)
    report_paths: dict = field(default_factory=dict)
    # analysis_id -> str (R2 key)
    report_r2_paths: dict = field(default_factory=dict)
    # analysis_id -> str (R2 key for uploaded policy)
    policy_r2_paths: dict = field(default_factory=dict)
    # analysis_id -> float (start time)
    start_times: dict = field(default_factory=dict)


class UserRegistry:
    """Registry of per-user data stores.

    Each authenticated user gets their own isolated data store.
    Users can only see and interact with their own analyses.
    """

    def __init__(self):
        self._stores: dict[str, UserDataStore] = {}
        # Map analysis_id -> user_id for reverse lookup
        self._analysis_owner: dict[str, str] = {}

    def get_store(self, user_id: str) -> UserDataStore:
        """Get or create a data store for a user."""
        if user_id not in self._stores:
            self._stores[user_id] = UserDataStore()
        return self._stores[user_id]

    def register_analysis(self, user_id: str, analysis_id: str) -> None:
        """Register an analysis as belonging to a user."""
        self._analysis_owner[analysis_id] = user_id

    def get_owner(self, analysis_id: str) -> Optional[str]:
        """Get the user_id that owns an analysis."""
        return self._analysis_owner.get(analysis_id)

    def verify_ownership(self, user_id: str, analysis_id: str) -> bool:
        """Check if a user owns a specific analysis."""
        return self._analysis_owner.get(analysis_id) == user_id


# Global user registry
user_registry = UserRegistry()
