"""Database abstraction layer.

Provides a unified interface for user and analysis storage.
Uses Supabase (via REST API with service_role key) when configured,
falls back to local SQLite for development/offline use.

Environment variables:
    SUPABASE_URL              — Supabase project URL
    SUPABASE_SERVICE_ROLE_KEY — Service role key (bypasses RLS)
    SUPABASE_KEY              — Anon key (fallback, less privileged)
"""

import logging
import os
import sqlite3
import time
import uuid
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract interface
# ---------------------------------------------------------------------------

class DatabaseBackend(ABC):
    """Abstract database backend for users and analyses."""

    # -- Users --
    @abstractmethod
    def create_user(self, email: str, password_hash: str, display_name: str) -> dict:
        """Create a user. Returns dict with id, email, password_hash, display_name, created_at."""
        ...

    @abstractmethod
    def get_user_by_email(self, email: str) -> Optional[dict]:
        """Look up user by email. Returns dict or None."""
        ...

    @abstractmethod
    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        """Look up user by ID. Returns dict or None."""
        ...

    # -- Analyses --
    @abstractmethod
    def create_analysis(self, analysis_id: str, user_id: str, client_name: str,
                        filename: str, file_size_bytes: int = 0) -> dict:
        """Create an analysis record. Returns dict."""
        ...

    @abstractmethod
    def update_analysis(self, analysis_id: str, **fields) -> None:
        """Update fields on an analysis record."""
        ...

    @abstractmethod
    def get_analysis(self, analysis_id: str) -> Optional[dict]:
        """Get a single analysis by ID."""
        ...

    @abstractmethod
    def list_user_analyses(self, user_id: str, limit: int = 50) -> list[dict]:
        """List analyses for a user, most recent first."""
        ...


# ---------------------------------------------------------------------------
# Supabase backend (REST API via httpx)
# ---------------------------------------------------------------------------

# Columns that actually exist in the Supabase `analyses` table.
# Any update fields not in this set will be silently dropped.
_SUPABASE_ANALYSES_COLUMNS = {
    "id", "user_id", "client_name", "file_name", "status",
    "overall_score", "rating", "binding_recommendation",
    "red_flag_count", "critical_gap_count", "created_at", "completed_at",
}

# Map from internal field names to Supabase column names
_FIELD_TO_SUPABASE = {
    "filename": "file_name",
    "overall_rating": "rating",
}

# Map from Supabase column names to internal field names (for reads)
_SUPABASE_TO_FIELD = {
    "file_name": "filename",
    "rating": "overall_rating",
}


class SupabaseBackend(DatabaseBackend):
    """Supabase backend using the REST API with the service_role key."""

    def __init__(self, url: str, key: str):
        self.url = url.rstrip("/")
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        self._available: Optional[bool] = None

    def _rest(self, method: str, path: str, json: Any = None,
              params: dict | None = None) -> Any:
        """Make a REST API call to Supabase PostgREST."""
        import httpx
        url = f"{self.url}/rest/v1/{path}"
        resp = httpx.request(method, url, headers=self.headers, json=json,
                             params=params, timeout=15.0)
        if resp.status_code >= 400:
            logger.error("Supabase REST error: %s %s -> %s %s",
                         method, path, resp.status_code, resp.text[:300])
            raise RuntimeError(f"Supabase error {resp.status_code}: {resp.text[:200]}")
        if resp.status_code == 204 or not resp.text:
            return None
        return resp.json()

    def is_available(self) -> bool:
        """Check if Supabase tables exist and are accessible."""
        if self._available is not None:
            return self._available
        try:
            self._rest("GET", "app_users", params={"select": "id", "limit": "0"})
            self._rest("GET", "analyses", params={"select": "id", "limit": "0"})
            self._available = True
            logger.info("Supabase backend available (tables: app_users, analyses)")
        except Exception as e:
            self._available = False
            logger.warning("Supabase backend not available: %s", e)
        return self._available

    def _map_fields_to_supabase(self, fields: dict) -> dict:
        """Map internal field names to Supabase column names and filter unsupported columns."""
        mapped = {}
        for k, v in fields.items():
            col = _FIELD_TO_SUPABASE.get(k, k)
            if col in _SUPABASE_ANALYSES_COLUMNS:
                mapped[col] = v
        return mapped

    def _normalize_analysis(self, row: dict) -> dict:
        """Normalize a Supabase analysis row to internal field names."""
        result = {}
        for k, v in row.items():
            internal = _SUPABASE_TO_FIELD.get(k, k)
            result[internal] = v
        return result

    # -- Users --

    def create_user(self, email: str, password_hash: str, display_name: str) -> dict:
        rows = self._rest("POST", "app_users", json={
            "email": email,
            "password_hash": password_hash,
            "display_name": display_name,
        })
        if rows and isinstance(rows, list):
            return self._normalize_user(rows[0])
        raise RuntimeError("Failed to create user in Supabase")

    def get_user_by_email(self, email: str) -> Optional[dict]:
        rows = self._rest("GET", "app_users", params={
            "select": "*",
            "email": f"eq.{email}",
            "limit": "1",
        })
        if rows and isinstance(rows, list) and len(rows) > 0:
            return self._normalize_user(rows[0])
        return None

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        rows = self._rest("GET", "app_users", params={
            "select": "*",
            "id": f"eq.{user_id}",
            "limit": "1",
        })
        if rows and isinstance(rows, list) and len(rows) > 0:
            return self._normalize_user(rows[0])
        return None

    def _normalize_user(self, row: dict) -> dict:
        """Normalize a Supabase user row to a standard dict."""
        return {
            "id": str(row["id"]),
            "email": row["email"],
            "password_hash": row["password_hash"],
            "display_name": row.get("display_name", ""),
            "created_at": row.get("created_at", ""),
        }

    # -- Analyses --

    def create_analysis(self, analysis_id: str, user_id: str, client_name: str,
                        filename: str, file_size_bytes: int = 0) -> dict:
        # Only send columns that exist in the Supabase table
        payload = {
            "id": analysis_id,
            "user_id": user_id,
            "client_name": client_name,
            "file_name": filename,
            "status": "pending",
        }
        rows = self._rest("POST", "analyses", json=payload)
        if rows and isinstance(rows, list):
            return self._normalize_analysis(rows[0])
        return {"id": analysis_id}

    def update_analysis(self, analysis_id: str, **fields) -> None:
        if not fields:
            return
        mapped = self._map_fields_to_supabase(fields)
        if not mapped:
            return
        self._rest("PATCH", f"analyses?id=eq.{analysis_id}", json=mapped)

    def get_analysis(self, analysis_id: str) -> Optional[dict]:
        rows = self._rest("GET", "analyses", params={
            "select": "*",
            "id": f"eq.{analysis_id}",
            "limit": "1",
        })
        if rows and isinstance(rows, list) and len(rows) > 0:
            return self._normalize_analysis(rows[0])
        return None

    def list_user_analyses(self, user_id: str, limit: int = 50) -> list[dict]:
        rows = self._rest("GET", "analyses", params={
            "select": "*",
            "user_id": f"eq.{user_id}",
            "order": "created_at.desc",
            "limit": str(limit),
        })
        if not isinstance(rows, list):
            return []
        return [self._normalize_analysis(r) for r in rows]


# ---------------------------------------------------------------------------
# SQLite fallback backend
# ---------------------------------------------------------------------------

class SQLiteBackend(DatabaseBackend):
    """Local SQLite backend for development and offline use."""

    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or (Path(__file__).resolve().parent.parent / "data" / "users.db")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self):
        conn = self._conn()
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                display_name TEXT NOT NULL DEFAULT '',
                created_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS analyses (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                client_name TEXT NOT NULL DEFAULT '',
                filename TEXT NOT NULL DEFAULT '',
                file_size_bytes INTEGER NOT NULL DEFAULT 0,
                page_count INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'pending',
                overall_score REAL,
                overall_rating TEXT,
                binding_recommendation TEXT,
                red_flag_count INTEGER DEFAULT 0,
                critical_gap_count INTEGER DEFAULT 0,
                error TEXT,
                total_duration_seconds REAL DEFAULT 0,
                scoring_input_tokens INTEGER DEFAULT 0,
                scoring_output_tokens INTEGER DEFAULT 0,
                narrative_input_tokens INTEGER DEFAULT 0,
                narrative_output_tokens INTEGER DEFAULT 0,
                has_report INTEGER DEFAULT 0,
                report_r2_key TEXT,
                created_at REAL NOT NULL,
                completed_at REAL
            );
        """)
        conn.commit()
        conn.close()
        logger.info("SQLite database initialized at %s", self.db_path)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    # -- Users --

    def create_user(self, email: str, password_hash: str, display_name: str) -> dict:
        user_id = str(uuid.uuid4())
        now = time.time()
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO users (id, email, password_hash, display_name, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                (user_id, email, password_hash, display_name, now),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            raise RuntimeError("DUPLICATE_EMAIL")
        finally:
            conn.close()
        return {
            "id": user_id,
            "email": email,
            "password_hash": password_hash,
            "display_name": display_name,
            "created_at": str(now),
        }

    def get_user_by_email(self, email: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return dict(row)

    def get_user_by_id(self, user_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
        if not row:
            return None
        return dict(row)

    # -- Analyses --

    def create_analysis(self, analysis_id: str, user_id: str, client_name: str,
                        filename: str, file_size_bytes: int = 0) -> dict:
        now = time.time()
        conn = self._conn()
        try:
            conn.execute(
                "INSERT INTO analyses (id, user_id, client_name, filename, file_size_bytes, "
                "status, created_at) VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                (analysis_id, user_id, client_name, filename, file_size_bytes, now),
            )
            conn.commit()
        finally:
            conn.close()
        return {"id": analysis_id, "user_id": user_id, "status": "pending", "created_at": now}

    def update_analysis(self, analysis_id: str, **fields) -> None:
        if not fields:
            return
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        values = list(fields.values()) + [analysis_id]
        conn = self._conn()
        try:
            conn.execute(f"UPDATE analyses SET {set_clause} WHERE id = ?", values)
            conn.commit()
        finally:
            conn.close()

    def get_analysis(self, analysis_id: str) -> Optional[dict]:
        conn = self._conn()
        try:
            row = conn.execute("SELECT * FROM analyses WHERE id = ?", (analysis_id,)).fetchone()
        finally:
            conn.close()
        return dict(row) if row else None

    def list_user_analyses(self, user_id: str, limit: int = 50) -> list[dict]:
        conn = self._conn()
        try:
            rows = conn.execute(
                "SELECT * FROM analyses WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
                (user_id, limit),
            ).fetchall()
        finally:
            conn.close()
        return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Module-level singleton — auto-detect backend
# ---------------------------------------------------------------------------

def _init_backend() -> DatabaseBackend:
    """Initialize the database backend based on environment variables."""
    supabase_url = os.environ.get("SUPABASE_URL", "")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "") or os.environ.get("SUPABASE_KEY", "")

    if supabase_url and supabase_key:
        sb = SupabaseBackend(supabase_url, supabase_key)
        if sb.is_available():
            return sb
        logger.warning("Supabase configured but tables not found. "
                       "Run migrations/001_init.sql in the Supabase SQL Editor. "
                       "Falling back to SQLite.")

    logger.info("Using SQLite backend for user and analysis storage.")
    return SQLiteBackend()


db: DatabaseBackend = _init_backend()
