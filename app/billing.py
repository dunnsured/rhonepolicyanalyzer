"""
RhôneRisk Billing Module
Stripe integration, credit system, teaser/paywall logic, and subscription management.
"""

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import httpx

logger = logging.getLogger("rhone.billing")

# ---------------------------------------------------------------------------
# Pricing configuration
# ---------------------------------------------------------------------------
PRICING = {
    "single_report": 4900,        # $49.00 per report
    "starter_monthly": 9900,      # $99/mo — 5 credits
    "pro_monthly": 24900,         # $249/mo — 15 credits
    "enterprise_monthly": 49900,  # $499/mo — 50 credits
}

PLAN_CREDITS = {
    "starter": 5,
    "pro": 15,
    "enterprise": 50,
}

# Supabase config (read from env)
SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", os.getenv("SUPABASE_KEY", ""))

# Stripe config
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = os.getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Base URL for redirects
BASE_URL = os.getenv("BASE_URL", "https://rhonepolicyanalyzer-production.up.railway.app")


def _supabase_headers():
    return {
        "apikey": SUPABASE_SERVICE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------
def _sb_get(table: str, params: dict) -> list:
    """GET from Supabase REST API."""
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
    """PATCH (update) in Supabase REST API."""
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


def _sb_post(table: str, data: dict) -> list:
    """POST (insert) to Supabase REST API."""
    try:
        r = httpx.post(
            f"{SUPABASE_URL}/rest/v1/{table}",
            headers=_supabase_headers(),
            json=data,
            timeout=10,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"Supabase POST {table} error: {e}")
        return []


# ---------------------------------------------------------------------------
# Credit system
# ---------------------------------------------------------------------------
def get_user_credits(user_id: str) -> int:
    """Get the current credit balance for a user."""
    rows = _sb_get("app_users", {"select": "credits", "id": f"eq.{user_id}"})
    if rows:
        return rows[0].get("credits", 0)
    return 0


def deduct_credit(user_id: str) -> bool:
    """Deduct one credit from user. Returns True if successful."""
    credits = get_user_credits(user_id)
    if credits <= 0:
        return False
    _sb_patch(
        "app_users",
        {"id": f"eq.{user_id}"},
        {"credits": credits - 1},
    )
    logger.info(f"Deducted 1 credit from user {user_id}. Remaining: {credits - 1}")
    return True


def add_credits(user_id: str, amount: int) -> int:
    """Add credits to user. Returns new balance."""
    current = get_user_credits(user_id)
    new_balance = current + amount
    _sb_patch(
        "app_users",
        {"id": f"eq.{user_id}"},
        {"credits": new_balance},
    )
    logger.info(f"Added {amount} credits to user {user_id}. New balance: {new_balance}")
    return new_balance


def get_user_analysis_count(user_id: str) -> int:
    """Get total number of completed analyses for a user."""
    rows = _sb_get("analyses", {
        "select": "id",
        "user_id": f"eq.{user_id}",
        "status": "eq.completed",
    })
    return len(rows)


def is_first_analysis(user_id: str) -> bool:
    """Check if this would be the user's first analysis (free)."""
    count = get_user_analysis_count(user_id)
    return count == 0


# ---------------------------------------------------------------------------
# Teaser / Paywall logic
# ---------------------------------------------------------------------------
def get_teaser_data(analysis_id: str, user_id: str) -> Optional[dict]:
    """
    Build teaser data for a completed but locked analysis.
    Returns limited info: overall score, rating, red flag count, and first 2 red flags.
    """
    rows = _sb_get("analyses", {
        "select": "*",
        "id": f"eq.{analysis_id}",
        "user_id": f"eq.{user_id}",
    })
    if not rows:
        return None

    analysis = rows[0]
    if analysis.get("is_unlocked"):
        return {"unlocked": True, "analysis_id": analysis_id}

    # Mark teaser as viewed
    if not analysis.get("teaser_viewed_at"):
        _sb_patch(
            "analyses",
            {"id": f"eq.{analysis_id}"},
            {"teaser_viewed_at": datetime.now(timezone.utc).isoformat()},
        )

    return {
        "unlocked": False,
        "analysis_id": analysis_id,
        "overall_score": analysis.get("overall_score"),
        "rating": analysis.get("rating"),
        "red_flag_count": analysis.get("red_flag_count", 0),
        "critical_gap_count": analysis.get("critical_gap_count", 0),
        "binding_recommendation": analysis.get("binding_recommendation"),
        "client_name": analysis.get("client_name"),
        "status": analysis.get("status"),
        "created_at": analysis.get("created_at"),
    }


def unlock_analysis(analysis_id: str, user_id: str, method: str = "credit") -> bool:
    """Mark an analysis as unlocked."""
    result = _sb_patch(
        "analyses",
        {"id": f"eq.{analysis_id}", "user_id": f"eq.{user_id}"},
        {"is_unlocked": True, "unlock_method": method},
    )
    if result:
        logger.info(f"Analysis {analysis_id} unlocked via {method} for user {user_id}")
        return True
    return False


def unlock_with_credit(analysis_id: str, user_id: str) -> dict:
    """Try to unlock an analysis using a credit."""
    # Check if already unlocked
    rows = _sb_get("analyses", {
        "select": "is_unlocked,unlock_method",
        "id": f"eq.{analysis_id}",
        "user_id": f"eq.{user_id}",
    })
    if not rows:
        return {"success": False, "error": "Analysis not found"}
    if rows[0].get("is_unlocked"):
        return {"success": True, "already_unlocked": True}

    # Check if first analysis (free)
    if is_first_analysis(user_id):
        unlock_analysis(analysis_id, user_id, method="free_first")
        return {"success": True, "method": "free_first", "credits_remaining": get_user_credits(user_id)}

    # Try to deduct credit
    if deduct_credit(user_id):
        unlock_analysis(analysis_id, user_id, method="credit")
        return {"success": True, "method": "credit", "credits_remaining": get_user_credits(user_id)}

    return {"success": False, "error": "Insufficient credits", "credits_remaining": 0}


# ---------------------------------------------------------------------------
# Stripe integration
# ---------------------------------------------------------------------------
def _stripe_request(method: str, endpoint: str, data: dict = None) -> dict:
    """Make a request to the Stripe API."""
    if not STRIPE_SECRET_KEY:
        logger.warning("STRIPE_SECRET_KEY not configured")
        return {"error": "Stripe not configured"}

    url = f"https://api.stripe.com/v1/{endpoint}"
    headers = {"Authorization": f"Bearer {STRIPE_SECRET_KEY}"}

    try:
        if method == "GET":
            r = httpx.get(url, headers=headers, params=data, timeout=15)
        elif method == "POST":
            r = httpx.post(url, headers=headers, data=data, timeout=15)
        else:
            return {"error": f"Unsupported method: {method}"}

        r.raise_for_status()
        return r.json()
    except httpx.HTTPStatusError as e:
        logger.error(f"Stripe API error: {e.response.status_code} - {e.response.text}")
        return {"error": str(e)}
    except Exception as e:
        logger.error(f"Stripe request error: {e}")
        return {"error": str(e)}


def get_or_create_stripe_customer(user_id: str, email: str, name: str = "") -> Optional[str]:
    """Get or create a Stripe customer for the user."""
    # Check if user already has a Stripe customer ID
    rows = _sb_get("app_users", {"select": "stripe_customer_id", "id": f"eq.{user_id}"})
    if rows and rows[0].get("stripe_customer_id"):
        return rows[0]["stripe_customer_id"]

    # Create new Stripe customer
    result = _stripe_request("POST", "customers", {
        "email": email,
        "name": name,
        "metadata[user_id]": user_id,
    })

    if "error" in result:
        return None

    customer_id = result.get("id")
    if customer_id:
        _sb_patch("app_users", {"id": f"eq.{user_id}"}, {"stripe_customer_id": customer_id})
        logger.info(f"Created Stripe customer {customer_id} for user {user_id}")

    return customer_id


def create_checkout_session(
    user_id: str,
    email: str,
    name: str,
    mode: str = "single",  # "single" or "starter" / "pro" / "enterprise"
    analysis_id: str = "",
) -> dict:
    """Create a Stripe Checkout Session."""
    customer_id = get_or_create_stripe_customer(user_id, email, name)
    if not customer_id:
        return {"error": "Failed to create Stripe customer"}

    if mode == "single":
        # One-time payment for a single report
        data = {
            "customer": customer_id,
            "mode": "payment",
            "payment_method_types[0]": "card",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": str(PRICING["single_report"]),
            "line_items[0][price_data][product_data][name]": "RhôneRisk Full Policy Analysis Report",
            "line_items[0][price_data][product_data][description]": "Complete AI-powered cyber insurance policy analysis with risk quantification, coverage scoring, and actionable recommendations.",
            "line_items[0][quantity]": "1",
            "success_url": f"{BASE_URL}/#results?session_id={{CHECKOUT_SESSION_ID}}&analysis_id={analysis_id}",
            "cancel_url": f"{BASE_URL}/#teaser?analysis_id={analysis_id}",
            "metadata[user_id]": user_id,
            "metadata[analysis_id]": analysis_id,
            "metadata[purchase_type]": "single_report",
        }
    else:
        # Subscription
        plan_key = f"{mode}_monthly"
        if plan_key not in PRICING:
            return {"error": f"Invalid plan: {mode}"}

        data = {
            "customer": customer_id,
            "mode": "subscription",
            "payment_method_types[0]": "card",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": str(PRICING[plan_key]),
            "line_items[0][price_data][recurring][interval]": "month",
            "line_items[0][price_data][product_data][name]": f"RhôneRisk {mode.title()} Plan",
            "line_items[0][price_data][product_data][description]": f"{PLAN_CREDITS[mode]} policy analyses per month",
            "line_items[0][quantity]": "1",
            "success_url": f"{BASE_URL}/#dashboard?session_id={{CHECKOUT_SESSION_ID}}",
            "cancel_url": f"{BASE_URL}/#pricing",
            "metadata[user_id]": user_id,
            "metadata[purchase_type]": "subscription",
            "metadata[plan]": mode,
        }

    result = _stripe_request("POST", "checkout/sessions", data)
    if "error" in result:
        return result

    return {
        "checkout_url": result.get("url"),
        "session_id": result.get("id"),
    }


def handle_stripe_webhook(payload: bytes, sig_header: str) -> dict:
    """
    Process a Stripe webhook event.
    Returns a dict with the event type and processing result.
    """
    import hashlib
    import hmac

    if not STRIPE_WEBHOOK_SECRET:
        logger.warning("STRIPE_WEBHOOK_SECRET not configured — skipping signature verification")
        import json
        try:
            event = json.loads(payload)
        except Exception:
            return {"error": "Invalid payload"}
    else:
        # Verify webhook signature
        try:
            import json
            # Parse the signature header
            parts = dict(item.split("=", 1) for item in sig_header.split(","))
            timestamp = parts.get("t", "")
            signature = parts.get("v1", "")

            # Compute expected signature
            signed_payload = f"{timestamp}.{payload.decode('utf-8')}"
            expected = hmac.new(
                STRIPE_WEBHOOK_SECRET.encode("utf-8"),
                signed_payload.encode("utf-8"),
                hashlib.sha256,
            ).hexdigest()

            if not hmac.compare_digest(expected, signature):
                return {"error": "Invalid signature"}

            # Check timestamp (allow 5 min tolerance)
            if abs(time.time() - int(timestamp)) > 300:
                return {"error": "Timestamp too old"}

            event = json.loads(payload)
        except Exception as e:
            logger.error(f"Webhook signature verification failed: {e}")
            return {"error": str(e)}

    event_type = event.get("type", "")
    data = event.get("data", {}).get("object", {})
    metadata = data.get("metadata", {})

    logger.info(f"Processing Stripe webhook: {event_type}")

    if event_type == "checkout.session.completed":
        user_id = metadata.get("user_id")
        purchase_type = metadata.get("purchase_type")

        if purchase_type == "single_report":
            analysis_id = metadata.get("analysis_id")
            payment_intent = data.get("payment_intent")

            # Record purchase
            _sb_post("purchases", {
                "user_id": user_id,
                "analysis_id": analysis_id,
                "stripe_payment_intent_id": payment_intent,
                "amount_cents": PRICING["single_report"],
                "status": "completed",
            })

            # Unlock the analysis
            unlock_analysis(analysis_id, user_id, method="single_purchase")

            # Update analysis with payment ID
            _sb_patch(
                "analyses",
                {"id": f"eq.{analysis_id}"},
                {"stripe_payment_id": payment_intent},
            )

            logger.info(f"Single report purchase completed: user={user_id}, analysis={analysis_id}")
            return {"processed": True, "type": "single_report", "analysis_id": analysis_id}

        elif purchase_type == "subscription":
            plan = metadata.get("plan", "starter")
            subscription_id = data.get("subscription")

            # Create subscription record
            _sb_post("subscriptions", {
                "user_id": user_id,
                "stripe_subscription_id": subscription_id,
                "plan": plan,
                "status": "active",
                "credits_per_month": PLAN_CREDITS.get(plan, 5),
            })

            # Add credits
            add_credits(user_id, PLAN_CREDITS.get(plan, 5))

            logger.info(f"Subscription started: user={user_id}, plan={plan}")
            return {"processed": True, "type": "subscription", "plan": plan}

    elif event_type == "invoice.paid":
        subscription_id = data.get("subscription")
        if subscription_id:
            # Find the subscription
            subs = _sb_get("subscriptions", {
                "select": "*",
                "stripe_subscription_id": f"eq.{subscription_id}",
            })
            if subs:
                sub = subs[0]
                # Add monthly credits
                add_credits(sub["user_id"], sub.get("credits_per_month", 5))
                logger.info(f"Monthly credits added for subscription {subscription_id}")
                return {"processed": True, "type": "invoice_paid"}

    elif event_type == "customer.subscription.deleted":
        subscription_id = data.get("id")
        if subscription_id:
            _sb_patch(
                "subscriptions",
                {"stripe_subscription_id": f"eq.{subscription_id}"},
                {"status": "canceled", "updated_at": datetime.now(timezone.utc).isoformat()},
            )
            logger.info(f"Subscription canceled: {subscription_id}")
            return {"processed": True, "type": "subscription_canceled"}

    elif event_type == "customer.subscription.updated":
        subscription_id = data.get("id")
        status = data.get("status")
        current_period_end = data.get("current_period_end")
        if subscription_id:
            update_data = {
                "status": status,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            if current_period_end:
                update_data["current_period_end"] = datetime.fromtimestamp(
                    current_period_end, tz=timezone.utc
                ).isoformat()
            _sb_patch(
                "subscriptions",
                {"stripe_subscription_id": f"eq.{subscription_id}"},
                update_data,
            )
            return {"processed": True, "type": "subscription_updated"}

    return {"processed": False, "type": event_type}


# ---------------------------------------------------------------------------
# User billing info
# ---------------------------------------------------------------------------
def get_user_billing_info(user_id: str) -> dict:
    """Get comprehensive billing info for a user."""
    # Get user data
    users = _sb_get("app_users", {
        "select": "credits,stripe_customer_id",
        "id": f"eq.{user_id}",
    })
    credits = users[0].get("credits", 0) if users else 0

    # Get active subscription
    subs = _sb_get("subscriptions", {
        "select": "*",
        "user_id": f"eq.{user_id}",
        "status": "eq.active",
        "order": "created_at.desc",
        "limit": "1",
    })
    subscription = subs[0] if subs else None

    # Get purchase history
    purchases = _sb_get("purchases", {
        "select": "*",
        "user_id": f"eq.{user_id}",
        "status": "eq.completed",
        "order": "created_at.desc",
        "limit": "10",
    })

    # Count total analyses
    total_analyses = get_user_analysis_count(user_id)

    return {
        "credits": credits,
        "subscription": {
            "plan": subscription["plan"] if subscription else None,
            "status": subscription["status"] if subscription else None,
            "credits_per_month": subscription["credits_per_month"] if subscription else 0,
            "current_period_end": subscription["current_period_end"] if subscription else None,
        } if subscription else None,
        "total_analyses": total_analyses,
        "recent_purchases": [
            {
                "analysis_id": p["analysis_id"],
                "amount": p["amount_cents"] / 100,
                "date": p["created_at"],
            }
            for p in purchases
        ],
        "stripe_publishable_key": STRIPE_PUBLISHABLE_KEY,
        "pricing": {
            "single_report": PRICING["single_report"] / 100,
            "starter": {"price": PRICING["starter_monthly"] / 100, "credits": PLAN_CREDITS["starter"]},
            "pro": {"price": PRICING["pro_monthly"] / 100, "credits": PLAN_CREDITS["pro"]},
            "enterprise": {"price": PRICING["enterprise_monthly"] / 100, "credits": PLAN_CREDITS["enterprise"]},
        },
    }
