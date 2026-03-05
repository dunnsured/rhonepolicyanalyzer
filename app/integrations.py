"""
RhôneRisk Integration Services
Klaviyo (email), SendBlue (SMS), and Slack (internal notifications).
"""

import logging
import os
from typing import Optional

import httpx

logger = logging.getLogger("rhone.integrations")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
KLAVIYO_API_KEY = os.getenv("KLAVIYO_API_KEY", "")
SENDBLUE_API_KEY = os.getenv("SENDBLUE_API_KEY", "")
SLACK_WEBHOOK_URL = os.getenv("SLACK_WEBHOOK_URL", "")
BASE_URL = os.getenv("BASE_URL", "https://rhonepolicyanalyzer-production.up.railway.app")


# ---------------------------------------------------------------------------
# Klaviyo Email
# ---------------------------------------------------------------------------
def send_klaviyo_email(
    to_email: str,
    subject: str,
    body: str,
    user_name: str = "",
    template_id: str = "",
) -> bool:
    """
    Send a transactional email via Klaviyo.
    Uses the Klaviyo API v2024-10-15 for sending transactional emails.
    Falls back to logging if Klaviyo is not configured.
    """
    if not KLAVIYO_API_KEY:
        logger.info(f"[Klaviyo disabled] Would send email to {to_email}: {subject}")
        return True  # Return True so nudge logic marks it as sent

    try:
        # Klaviyo transactional email via Events API
        # Create an event that triggers a Klaviyo flow
        headers = {
            "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
            "Content-Type": "application/json",
            "revision": "2024-10-15",
        }

        # First, ensure the profile exists
        profile_payload = {
            "data": {
                "type": "profile",
                "attributes": {
                    "email": to_email,
                    "first_name": user_name.split()[0] if user_name else "",
                    "last_name": " ".join(user_name.split()[1:]) if user_name and " " in user_name else "",
                    "properties": {
                        "source": "rhone_policy_analyzer",
                    },
                },
            }
        }

        r = httpx.post(
            "https://a.klaviyo.com/api/profiles/",
            headers=headers,
            json=profile_payload,
            timeout=15,
        )
        # 201 = created, 409 = already exists — both are fine
        if r.status_code not in (200, 201, 202, 409):
            logger.warning(f"Klaviyo profile create returned {r.status_code}: {r.text[:200]}")

        # Create an event to trigger the email flow
        event_payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "metric": {
                        "data": {
                            "type": "metric",
                            "attributes": {
                                "name": "Policy Analysis Nudge",
                            },
                        },
                    },
                    "profile": {
                        "data": {
                            "type": "profile",
                            "attributes": {
                                "email": to_email,
                            },
                        },
                    },
                    "properties": {
                        "subject": subject,
                        "body": body,
                        "email_type": "nudge",
                    },
                },
            }
        }

        r = httpx.post(
            "https://a.klaviyo.com/api/events/",
            headers=headers,
            json=event_payload,
            timeout=15,
        )

        if r.status_code in (200, 201, 202):
            logger.info(f"Klaviyo event sent for {to_email}: {subject}")
            return True
        else:
            logger.error(f"Klaviyo event failed ({r.status_code}): {r.text[:200]}")
            return False

    except Exception as e:
        logger.error(f"Klaviyo email error: {e}")
        return False


def track_klaviyo_event(
    email: str,
    event_name: str,
    properties: dict = None,
) -> bool:
    """Track a custom event in Klaviyo for flow triggers and analytics."""
    if not KLAVIYO_API_KEY:
        logger.info(f"[Klaviyo disabled] Would track event '{event_name}' for {email}")
        return True

    try:
        headers = {
            "Authorization": f"Klaviyo-API-Key {KLAVIYO_API_KEY}",
            "Content-Type": "application/json",
            "revision": "2024-10-15",
        }

        payload = {
            "data": {
                "type": "event",
                "attributes": {
                    "metric": {
                        "data": {
                            "type": "metric",
                            "attributes": {
                                "name": event_name,
                            },
                        },
                    },
                    "profile": {
                        "data": {
                            "type": "profile",
                            "attributes": {
                                "email": email,
                            },
                        },
                    },
                    "properties": properties or {},
                },
            }
        }

        r = httpx.post(
            "https://a.klaviyo.com/api/events/",
            headers=headers,
            json=payload,
            timeout=15,
        )

        if r.status_code in (200, 201, 202):
            logger.info(f"Klaviyo event tracked: {event_name} for {email}")
            return True
        else:
            logger.warning(f"Klaviyo event tracking failed ({r.status_code}): {r.text[:200]}")
            return False

    except Exception as e:
        logger.error(f"Klaviyo event tracking error: {e}")
        return False


# ---------------------------------------------------------------------------
# SendBlue SMS
# ---------------------------------------------------------------------------
def send_sendblue_sms(to_phone: str, message: str) -> bool:
    """
    Send an SMS via SendBlue API.
    Falls back to logging if SendBlue is not configured.
    """
    if not SENDBLUE_API_KEY:
        logger.info(f"[SendBlue disabled] Would send SMS to {to_phone}: {message[:80]}...")
        return True

    try:
        headers = {
            "sb-api-key-id": SENDBLUE_API_KEY,
            "Content-Type": "application/json",
        }

        payload = {
            "number": to_phone,
            "content": message,
        }

        r = httpx.post(
            "https://api.sendblue.co/api/send-message",
            headers=headers,
            json=payload,
            timeout=15,
        )

        if r.status_code in (200, 201, 202):
            logger.info(f"SendBlue SMS sent to {to_phone}")
            return True
        else:
            logger.error(f"SendBlue SMS failed ({r.status_code}): {r.text[:200]}")
            return False

    except Exception as e:
        logger.error(f"SendBlue SMS error: {e}")
        return False


# ---------------------------------------------------------------------------
# Slack Notifications
# ---------------------------------------------------------------------------
def send_slack_notification(message: str, channel: str = "#crm-alerts") -> bool:
    """
    Send a notification to Slack via webhook.
    Falls back to logging if Slack webhook is not configured.
    """
    if not SLACK_WEBHOOK_URL:
        logger.info(f"[Slack disabled] Would send to {channel}: {message}")
        return True

    try:
        payload = {
            "text": message,
            "channel": channel,
            "username": "RhôneRisk Bot",
            "icon_emoji": ":shield:",
        }

        r = httpx.post(
            SLACK_WEBHOOK_URL,
            json=payload,
            timeout=10,
        )

        if r.status_code == 200:
            logger.info(f"Slack notification sent: {message[:80]}...")
            return True
        else:
            logger.error(f"Slack notification failed ({r.status_code}): {r.text[:200]}")
            return False

    except Exception as e:
        logger.error(f"Slack notification error: {e}")
        return False


# ---------------------------------------------------------------------------
# High-level notification functions (called from main.py)
# ---------------------------------------------------------------------------
def notify_new_user(email: str, display_name: str = ""):
    """Send notifications when a new user registers."""
    # Slack
    send_slack_notification(
        f"\U0001f195 New user registered: {email}"
        + (f" ({display_name})" if display_name else "")
    )

    # Klaviyo — track registration event
    track_klaviyo_event(email, "User Registered", {
        "display_name": display_name,
        "source": "rhone_policy_analyzer",
    })


def notify_analysis_started(email: str, filename: str, analysis_id: str):
    """Send notifications when a new analysis starts."""
    send_slack_notification(
        f"\U0001f4c4 New policy analysis started by {email} — {filename}"
    )

    track_klaviyo_event(email, "Analysis Started", {
        "filename": filename,
        "analysis_id": analysis_id,
    })


def notify_analysis_completed(
    email: str,
    analysis_id: str,
    client_name: str,
    score: float,
    red_flags: int,
):
    """Send notifications when an analysis completes."""
    send_slack_notification(
        f"\u2705 Analysis completed for {email} — {client_name}: "
        f"Score {score}/10, {red_flags} red flags"
    )

    track_klaviyo_event(email, "Analysis Completed", {
        "analysis_id": analysis_id,
        "client_name": client_name,
        "score": score,
        "red_flags": red_flags,
    })


def notify_teaser_viewed(email: str, analysis_id: str, red_flags: int):
    """Send notifications when a user views a teaser report."""
    send_slack_notification(
        f"\U0001f440 {email} viewed their teaser report ({red_flags} gaps found)"
    )

    track_klaviyo_event(email, "Teaser Viewed", {
        "analysis_id": analysis_id,
        "red_flags": red_flags,
    })


def notify_purchase_completed(email: str, amount: float, analysis_id: str = ""):
    """Send notifications when a purchase is completed."""
    send_slack_notification(
        f"\U0001f4b0 {email} purchased full report — ${amount:.2f}"
    )

    track_klaviyo_event(email, "Purchase Completed", {
        "amount": amount,
        "analysis_id": analysis_id,
    })


def notify_subscription_started(email: str, plan: str, amount: float):
    """Send notifications when a subscription starts."""
    send_slack_notification(
        f"\U0001f389 {email} started {plan} subscription — ${amount:.2f}/mo"
    )

    track_klaviyo_event(email, "Subscription Started", {
        "plan": plan,
        "amount": amount,
    })
