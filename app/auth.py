"""Authentication module using Supabase Auth.

Validates JWT access tokens by calling Supabase's /auth/v1/user endpoint.
Manages per-user data isolation for analyses, reports, and monitoring.
"""

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import requests
from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supabase configuration
# ---------------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")


@dataclass
class AuthUser:
    """Authenticated user from Supabase."""
    id: str
    email: str
    display_name: str = ""
    created_at: str = ""


def validate_token(access_token: str) -> AuthUser:
    """Validate a Supabase access token by calling the /auth/v1/user endpoint.

    Returns an AuthUser if valid, raises HTTPException if not.
    """
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise HTTPException(status_code=500, detail="Supabase not configured.")

    try:
        resp = requests.get(
            f"{SUPABASE_URL}/auth/v1/user",
            headers={
                "apikey": SUPABASE_KEY,
                "Authorization": f"Bearer {access_token}",
            },
            timeout=10,
        )
    except requests.RequestException as e:
        logger.error("Supabase auth request failed: %s", e)
        raise HTTPException(status_code=502, detail="Authentication service unavailable.")

    if resp.status_code == 401:
        raise HTTPException(status_code=401, detail="Invalid or expired token. Please log in again.")
    if resp.status_code != 200:
        logger.error("Supabase auth returned %d: %s", resp.status_code, resp.text[:200])
        raise HTTPException(status_code=502, detail="Authentication service error.")

    user_data = resp.json()
    user_id = user_data.get("id", "")
    email = user_data.get("email", "")
    display_name = user_data.get("user_metadata", {}).get("display_name", "")
    created_at = user_data.get("created_at", "")

    if not user_id:
        raise HTTPException(status_code=401, detail="Invalid user data.")

    return AuthUser(
        id=user_id,
        email=email,
        display_name=display_name or email.split("@")[0],
        created_at=created_at,
    )


async def get_current_user(request: Request) -> AuthUser:
    """Extract and validate the auth token from the request.

    Checks Authorization header (Bearer token) first, then falls back to
    a cookie named 'sb_access_token'.
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
        token = request.cookies.get("sb_access_token")

    if not token:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Please log in.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return validate_token(token)


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
