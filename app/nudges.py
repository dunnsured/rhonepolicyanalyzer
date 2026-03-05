"""
RhôneRisk Nudge Scheduler
Background jobs that send follow-up emails and SMS to users who viewed teasers but haven't purchased.
Uses APScheduler for periodic checks.
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

logger = logging.getLogger("rhone.nudges")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY", ""))
BASE_URL = os.getenv("BASE_URL", "https://rhonepolicyanalyzer-production.up.railway.app")


def _supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


def _sb_get(table: str, params: dict) -> list:
    try:
        r = httpx.get(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_supabase_headers(),
            params=params,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Supabase GET {table} error: {e}")
        return []


def _sb_patch(table: str, params: dict, data: dict) -> list:
    try:
        r = httpx.patch(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_supabase_headers(),
            params=params,
            json=data,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Supabase PATCH {table} error: {e}")
        return []


# ---------------------------------------------------------------------------
# Nudge timing configuration
# ---------------------------------------------------------------------------
NUDGE_SCHEDULE = {
    "email_1": {"delay_hours": 1, "field": "nudge_email_1_sent"},
    "email_2": {"delay_hours": 24, "field": "nudge_email_2_sent"},
    "email_3": {"delay_hours": 72, "field": "nudge_email_3_sent"},
    "sms_1": {"delay_hours": 4, "field": "nudge_sms_1_sent"},
    "sms_2": {"delay_hours": 48, "field": "nudge_sms_2_sent"},
}


# ---------------------------------------------------------------------------
# Email content templates
# ---------------------------------------------------------------------------
def _get_email_content(nudge_type: str, analysis: dict, user: dict) -> dict:
    """Generate email subject and body for a nudge type."""
    client_name = analysis.get("client_name", "your client")
    score = analysis.get("overall_score", "N/A")
    red_flags = analysis.get("red_flag_count", 0)
    user_name = user.get("display_name", "there")
    analysis_url = f"{BASE_URL}/#teaser?id={analysis['id']}"

    if nudge_type == "email_1":
        return {
            "subject": f"Your policy analysis for {client_name} is ready — {red_flags} issues found",
            "body": (
                f"Hi {user_name},\n\n"
                f"Your AI-powered analysis of {client_name}'s cyber insurance policy is complete.\n\n"
                f"Here's what we found:\n"
                f"- Overall Score: {score}/10\n"
                f"- Red Flags Identified: {red_flags}\n\n"
                f"Your full report includes detailed coverage scoring, risk quantification, "
                f"and actionable binding recommendations.\n\n"
                f"View your full report: {analysis_url}\n\n"
                f"— The RhôneRisk Team"
            ),
        }
    elif nudge_type == "email_2":
        return {
            "subject": f"Don't leave {client_name} exposed — {red_flags} coverage gaps need attention",
            "body": (
                f"Hi {user_name},\n\n"
                f"We noticed you haven't unlocked the full analysis for {client_name} yet.\n\n"
                f"With {red_flags} red flags identified, there are critical coverage gaps "
                f"that could leave your client exposed in a cyber incident.\n\n"
                f"The full report includes:\n"
                f"- Detailed risk quantification with dollar-amount scenarios\n"
                f"- Coverage gap analysis with specific recommendations\n"
                f"- Benchmarking against industry standards\n"
                f"- A clear binding recommendation with rationale\n\n"
                f"Unlock the full report: {analysis_url}\n\n"
                f"— The RhôneRisk Team"
            ),
        }
    elif nudge_type == "email_3":
        return {
            "subject": f"Last chance: Your {client_name} policy analysis expires soon",
            "body": (
                f"Hi {user_name},\n\n"
                f"This is a final reminder about your pending policy analysis for {client_name}.\n\n"
                f"Our AI identified {red_flags} critical issues that deserve attention. "
                f"The full report provides the detailed analysis your client needs.\n\n"
                f"Don't miss out — unlock your report today: {analysis_url}\n\n"
                f"Need help? Reply to this email and our team will assist you.\n\n"
                f"— The RhôneRisk Team"
            ),
        }
    return {"subject": "", "body": ""}


def _get_sms_content(nudge_type: str, analysis: dict, user: dict) -> str:
    """Generate SMS content for a nudge type."""
    client_name = analysis.get("client_name", "your client")
    red_flags = analysis.get("red_flag_count", 0)
    analysis_url = f"{BASE_URL}/#teaser?id={analysis['id']}"

    if nudge_type == "sms_1":
        return (
            f"RhôneRisk: Your policy analysis for {client_name} found {red_flags} issues. "
            f"View your full report: {analysis_url}"
        )
    elif nudge_type == "sms_2":
        return (
            f"RhôneRisk: Don't miss the {red_flags} coverage gaps in {client_name}'s policy. "
            f"Unlock your report: {analysis_url}"
        )
    return ""


# ---------------------------------------------------------------------------
# Nudge processing
# ---------------------------------------------------------------------------
def process_nudges():
    """
    Main nudge processing function — called periodically by APScheduler.
    Finds analyses with teaser_viewed_at set but not unlocked, and sends
    appropriate nudges based on timing.
    """
    from app.integrations import send_klaviyo_email, send_sendblue_sms

    logger.info("Processing nudges...")

    # Find analyses that have been viewed but not unlocked
    analyses = _sb_get("analyses", {
        "select": "*",
        "is_unlocked": "eq.false",
        "status": "eq.completed",
        "teaser_viewed_at": "not.is.null",
        "order": "teaser_viewed_at.asc",
        "limit": "100",
    })

    if not analyses:
        logger.info("No pending nudges found")
        return

    now = datetime.now(timezone.utc)
    nudges_sent = 0

    for analysis in analyses:
        teaser_viewed = datetime.fromisoformat(
            analysis["teaser_viewed_at"].replace("Z", "+00:00")
        )
        hours_since_view = (now - teaser_viewed).total_seconds() / 3600

        # Get user info
        users = _sb_get("app_users", {
            "select": "id,email,display_name,phone,sms_opt_in",
            "id": f"eq.{analysis['user_id']}",
        })
        if not users:
            continue
        user = users[0]

        # Process each nudge type
        for nudge_type, config in NUDGE_SCHEDULE.items():
            field = config["field"]
            delay = config["delay_hours"]

            # Skip if already sent
            if analysis.get(field):
                continue

            # Skip if not enough time has passed
            if hours_since_view < delay:
                continue

            # Send the nudge
            if nudge_type.startswith("email"):
                content = _get_email_content(nudge_type, analysis, user)
                if content["subject"]:
                    success = send_klaviyo_email(
                        to_email=user["email"],
                        subject=content["subject"],
                        body=content["body"],
                        user_name=user.get("display_name", ""),
                    )
                    if success:
                        _sb_patch(
                            "analyses",
                            {"id": f"eq.{analysis['id']}"},
                            {field: True},
                        )
                        nudges_sent += 1
                        logger.info(f"Sent {nudge_type} for analysis {analysis['id']} to {user['email']}")

            elif nudge_type.startswith("sms"):
                # Only send SMS if user opted in and has a phone number
                if user.get("sms_opt_in") and user.get("phone"):
                    content = _get_sms_content(nudge_type, analysis, user)
                    if content:
                        success = send_sendblue_sms(
                            to_phone=user["phone"],
                            message=content,
                        )
                        if success:
                            _sb_patch(
                                "analyses",
                                {"id": f"eq.{analysis['id']}"},
                                {field: True},
                            )
                            nudges_sent += 1
                            logger.info(f"Sent {nudge_type} for analysis {analysis['id']} to {user['phone']}")

    logger.info(f"Nudge processing complete. Sent {nudges_sent} nudges.")


# ---------------------------------------------------------------------------
# Scheduler setup
# ---------------------------------------------------------------------------
_scheduler = None


def start_nudge_scheduler():
    """Start the APScheduler background job for nudge processing."""
    global _scheduler

    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
    except ImportError:
        logger.warning("APScheduler not installed — nudge scheduler disabled")
        return

    if _scheduler is not None:
        logger.warning("Nudge scheduler already running")
        return

    _scheduler = BackgroundScheduler()
    _scheduler.add_job(
        process_nudges,
        trigger=IntervalTrigger(minutes=15),
        id="nudge_processor",
        name="Process nudge emails and SMS",
        replace_existing=True,
    )
    _scheduler.start()
    logger.info("Nudge scheduler started (runs every 15 minutes)")


def stop_nudge_scheduler():
    """Stop the nudge scheduler."""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        _scheduler = None
        logger.info("Nudge scheduler stopped")
