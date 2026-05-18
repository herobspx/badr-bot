"""Supabase REST API helper for BAMSPX bot."""
import os
import httpx
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation",
}

BASE = f"{SUPABASE_URL}/rest/v1"


async def _get(table, params=""):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.get(f"{BASE}/{table}?{params}", headers=HEADERS)
        try:
            return r.json()
        except Exception:
            return []


async def _post(table, data):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(f"{BASE}/{table}", headers=HEADERS, json=data)
        try:
            return r.json()
        except Exception:
            return []


async def _patch(table, data, match):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.patch(
            f"{BASE}/{table}?{match}",
            headers={**HEADERS, "Prefer": "return=minimal"},
            json=data,
        )
        return r.status_code


async def _delete(table, match):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.delete(f"{BASE}/{table}?{match}", headers=HEADERS)
        return r.status_code


async def upsert(table, data):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(
            f"{BASE}/{table}",
            headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"},
            json=data,
        )
        return r.status_code


# Settings
async def get_setting(key):
    rows = await _get("settings", f"key=eq.{key}&select=value")
    return rows[0]["value"] if isinstance(rows, list) and rows else None


async def set_setting(key, value):
    await upsert("settings", {"key": key, "value": str(value)})


# Verified
async def is_verified(uid):
    rows = await _get("verified", f"uid=eq.{uid}&select=uid")
    return isinstance(rows, list) and len(rows) > 0


async def save_verified(uid, phone, full_name, username):
    await upsert(
        "verified",
        {
            "uid": str(uid),
            "phone": phone,
            "full_name": full_name,
            "username": username,
            "verified_at": datetime.now().isoformat(),
        },
    )


async def get_verified_phone(uid):
    rows = await _get("verified", f"uid=eq.{uid}&select=phone")
    return rows[0]["phone"] if isinstance(rows, list) and rows else "—"


async def get_verified_user(uid):
    rows = await _get("verified", f"uid=eq.{uid}")
    return rows[0] if isinstance(rows, list) and rows else None


async def get_all_verified():
    rows = await _get("verified", "select=*")
    return rows if isinstance(rows, list) else []


# Subscribers
async def get_subscriber(uid):
    rows = await _get("subscribers", f"uid=eq.{uid}")
    return rows[0] if isinstance(rows, list) and rows else None


async def save_subscriber(uid, plan_key, expires_at):
    await upsert(
        "subscribers",
        {
            "uid": str(uid),
            "plan_key": plan_key,
            "expires_at": expires_at.isoformat(),
            "activated_at": datetime.now().isoformat(),
            "is_trial": False,
            "reminder_3d_sent": False,
            "reminder_1d_sent": False,
        },
    )


async def delete_subscriber(uid):
    await _delete("subscribers", f"uid=eq.{uid}")


async def get_all_expired():
    now = datetime.now().isoformat()
    rows = await _get("subscribers", f"expires_at=lte.{now}")
    return rows if isinstance(rows, list) else []


async def get_all_active_subscribers():
    now = datetime.now().isoformat()
    rows = await _get("subscribers", f"expires_at=gt.{now}")
    return rows if isinstance(rows, list) else []


async def mark_reminder(uid, stage):
    if stage == "3d":
        await _patch("subscribers", {"reminder_3d_sent": True}, f"uid=eq.{uid}")
    elif stage == "1d":
        await _patch("subscribers", {"reminder_1d_sent": True}, f"uid=eq.{uid}")


# Pending
async def get_pending(uid):
    rows = await _get("pending", f"uid=eq.{uid}")
    return rows[0] if isinstance(rows, list) and rows else None


async def save_pending(uid, plan_key, full_name, username, phone, status):
    await upsert(
        "pending",
        {
            "uid": str(uid),
            "plan_key": plan_key,
            "full_name": full_name,
            "username": username,
            "phone": phone,
            "status": status,
            "requested_at": datetime.now().isoformat(),
        },
    )


async def update_pending_status(uid, status):
    await _patch("pending", {"status": status}, f"uid=eq.{uid}")


async def delete_pending(uid):
    await _delete("pending", f"uid=eq.{uid}")


# Channel users
async def save_channel_user(uid, name, username):
    await upsert(
        "channel_users",
        {
            "uid": str(uid),
            "name": name,
            "username": username,
            "joined": datetime.now().isoformat(),
        },
    )


async def get_channel_users_count():
    rows = await _get("channel_users", "select=uid")
    return len(rows) if isinstance(rows, list) else 0


async def get_all_channel_users():
    rows = await _get("channel_users", "select=uid")
    return rows if isinstance(rows, list) else []


# Search
async def search_users(keyword):
    keyword = str(keyword).replace("@", "").strip().lower()
    users = await get_all_verified()
    results = []

    for u in users:
        uid = str(u.get("uid", ""))
        phone = str(u.get("phone", ""))
        username = str(u.get("username", "")).lower()
        name = str(u.get("full_name", "")).lower()

        if keyword in uid or keyword in phone or keyword in username or keyword in name:
            results.append(u)

    return results[:10]


# Stats
async def get_stats():
    now = datetime.now().isoformat()
    verified = await _get("verified", "select=uid")
    active = await _get("subscribers", f"expires_at=gt.{now}&select=uid")
    expired = await _get("subscribers", f"expires_at=lte.{now}&select=uid")
    pending = await _get("pending", "select=uid")

    return (
        len(verified) if isinstance(verified, list) else 0,
        len(active) if isinstance(active, list) else 0,
        len(expired) if isinstance(expired, list) else 0,
        len(pending) if isinstance(pending, list) else 0,
    )
