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


async def _request(method, url, **kwargs):
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.request(method, url, **kwargs)
        try:
            body = r.json()
        except Exception:
            body = None
        return r.status_code, body


async def _get(table, params=""):
    status, body = await _request("GET", f"{BASE}/{table}?{params}", headers=HEADERS)
    return body if isinstance(body, list) else []


async def _post(table, data):
    status, body = await _request("POST", f"{BASE}/{table}", headers=HEADERS, json=data)
    return status, body


async def _patch(table, data, match):
    status, body = await _request(
        "PATCH",
        f"{BASE}/{table}?{match}",
        headers={**HEADERS, "Prefer": "return=representation"},
        json=data,
    )
    return status, body


async def _delete(table, match):
    status, body = await _request("DELETE", f"{BASE}/{table}?{match}", headers=HEADERS)
    return status


async def upsert(table, data, conflict_col="uid"):
    # Supabase REST upsert needs Prefer resolution + on_conflict when uid is the unique key.
    status, body = await _request(
        "POST",
        f"{BASE}/{table}?on_conflict={conflict_col}",
        headers={**HEADERS, "Prefer": "resolution=merge-duplicates,return=representation"},
        json=data,
    )

    if 200 <= status < 300:
        return True

    # Fallback: if row exists, patch it; otherwise post it normally.
    uid = data.get(conflict_col)
    if uid is not None:
        rows = await _get(table, f"{conflict_col}=eq.{uid}&select={conflict_col}")
        if rows:
            patch_status, _ = await _patch(table, data, f"{conflict_col}=eq.{uid}")
            return 200 <= patch_status < 300

    post_status, _ = await _post(table, data)
    return 200 <= post_status < 300


# Settings
async def get_setting(key):
    rows = await _get("settings", f"key=eq.{key}&select=value")
    return rows[0]["value"] if rows else None


async def set_setting(key, value):
    await upsert("settings", {"key": key, "value": str(value)}, conflict_col="key")


# Verified
async def is_verified(uid):
    rows = await _get("verified", f"uid=eq.{uid}&select=uid")
    return len(rows) > 0


async def save_verified(uid, phone, full_name, username):
    return await upsert(
        "verified",
        {
            "uid": str(uid),
            "phone": phone,
            "full_name": full_name,
            "username": username,
            "verified_at": datetime.now().isoformat(),
        },
        conflict_col="uid",
    )


async def get_verified_phone(uid):
    rows = await _get("verified", f"uid=eq.{uid}&select=phone")
    return rows[0]["phone"] if rows else "—"


async def get_verified_user(uid):
    rows = await _get("verified", f"uid=eq.{uid}")
    return rows[0] if rows else None


async def get_all_verified():
    return await _get("verified", "select=*")


# Subscribers
async def get_subscriber(uid):
    rows = await _get("subscribers", f"uid=eq.{uid}")
    return rows[0] if rows else None


async def save_subscriber(uid, plan_key, expires_at):
    # لا نرسل أعمدة التذكير هنا حتى لا يفشل الحفظ إذا لم تكن الأعمدة مضافة في Supabase.
    return await upsert(
        "subscribers",
        {
            "uid": str(uid),
            "plan_key": plan_key,
            "expires_at": expires_at.isoformat(),
            "activated_at": datetime.now().isoformat(),
            "is_trial": False,
        },
        conflict_col="uid",
    )


async def delete_subscriber(uid):
    await _delete("subscribers", f"uid=eq.{uid}")


async def get_all_expired():
    now = datetime.now().isoformat()
    return await _get("subscribers", f"expires_at=lte.{now}")


async def get_all_active_subscribers():
    now = datetime.now().isoformat()
    return await _get("subscribers", f"expires_at=gt.{now}")


async def mark_reminder(uid, stage):
    # إذا كانت الأعمدة غير موجودة في Supabase، لن يوقف هذا البوت.
    if stage == "3d":
        await _patch("subscribers", {"reminder_3d_sent": True}, f"uid=eq.{uid}")
    elif stage == "1d":
        await _patch("subscribers", {"reminder_1d_sent": True}, f"uid=eq.{uid}")


# Pending
async def get_pending(uid):
    rows = await _get("pending", f"uid=eq.{uid}")
    return rows[0] if rows else None


async def save_pending(uid, plan_key, full_name, username, phone, status):
    return await upsert(
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
        conflict_col="uid",
    )


async def update_pending_status(uid, status):
    await _patch("pending", {"status": status}, f"uid=eq.{uid}")


async def delete_pending(uid):
    await _delete("pending", f"uid=eq.{uid}")


# Channel users
async def save_channel_user(uid, name, username):
    return await upsert(
        "channel_users",
        {
            "uid": str(uid),
            "name": name,
            "username": username,
            "joined": datetime.now().isoformat(),
        },
        conflict_col="uid",
    )


async def get_channel_users_count():
    rows = await _get("channel_users", "select=uid")
    return len(rows)


async def get_all_channel_users():
    return await _get("channel_users", "select=uid")


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
    return len(verified), len(active), len(expired), len(pending)
