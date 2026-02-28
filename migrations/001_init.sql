-- ============================================================================
-- RhôneRisk Cyber Insurance Policy Analyzer — Supabase Migration 001
-- ============================================================================
-- Run this SQL in the Supabase SQL Editor (https://supabase.com/dashboard)
-- before deploying the application.
--
-- This creates two tables:
--   1. app_users  — local JWT auth user accounts (NOT Supabase Auth)
--   2. analyses   — per-user analysis metadata
--
-- RLS is DISABLED on both tables because all access is mediated by the
-- backend API using the service_role key. The backend enforces per-user
-- isolation in application code via JWT validation.
-- ============================================================================

-- ---------------------------------------------------------------------------
-- 1. app_users — stores user accounts for local JWT authentication
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS app_users (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email           TEXT UNIQUE NOT NULL,
    password_hash   TEXT NOT NULL,
    display_name    TEXT NOT NULL DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_app_users_email ON app_users (email);

-- Disable RLS — backend mediates all access
ALTER TABLE app_users DISABLE ROW LEVEL SECURITY;

-- Grant roles full access
GRANT ALL ON app_users TO anon;
GRANT ALL ON app_users TO authenticated;
GRANT ALL ON app_users TO service_role;

-- ---------------------------------------------------------------------------
-- 2. analyses — stores per-user analysis metadata
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS analyses (
    id                      TEXT PRIMARY KEY,
    user_id                 UUID NOT NULL REFERENCES app_users(id) ON DELETE CASCADE,
    client_name             TEXT NOT NULL DEFAULT '',
    file_name               TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL DEFAULT 'pending',
    overall_score           REAL,
    rating                  TEXT,
    binding_recommendation  TEXT,
    red_flag_count          INTEGER DEFAULT 0,
    critical_gap_count      INTEGER DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at            TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_analyses_user_id    ON analyses (user_id);
CREATE INDEX IF NOT EXISTS idx_analyses_created_at ON analyses (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_analyses_status     ON analyses (status);

-- Disable RLS — backend mediates all access
ALTER TABLE analyses DISABLE ROW LEVEL SECURITY;

-- Grant roles full access
GRANT ALL ON analyses TO anon;
GRANT ALL ON analyses TO authenticated;
GRANT ALL ON analyses TO service_role;

-- ---------------------------------------------------------------------------
-- Verify
-- ---------------------------------------------------------------------------
-- After running this migration, verify by running:
--   SELECT count(*) FROM app_users;
--   SELECT count(*) FROM analyses;
-- Both should return 0 with no errors.
