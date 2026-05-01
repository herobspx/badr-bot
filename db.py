"""Supabase REST API helper"""
import os
import httpx
from datetime import datetime

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

HEADERS = {
    "apikey": SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type": "application/json",
    "Prefer": "return=representation"
}

BASE = f"{SUPABASE_URL}/rest/v1"

async def _get(table, params=""):
    async with httpx.AsyncClient() as c:
        r = await c.get(f"{BASE}/{table}?{params}", headers=HEADERS)
        return r.json()

async def _post(table, data):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/{table}", headers=HEADERS, json=data)
        return r.json()

async def _patch(table, data, match):
    async with httpx.AsyncClient() as c:
        r = await c.patch(f"{BASE}/{table}?{match}", headers={**HEADERS,"Prefer":"return=minimal"}, json=data)
        return r.status_code

async def _delete(table, match):
    async with httpx.AsyncClient() as c:
        r = await c.delete(f"{BASE}/{table}?{match}", headers=HEADERS)
        return r.status_code

async def upsert(table, data):
    async with httpx.AsyncClient() as c:
        r = await c.post(f"{BASE}/{table}", headers={**HEADERS,"Prefer":"resolution=merge-duplicates"}, json=data)
        return r.status_code

# ── Settings ──
async def get_setting(key):
    rows = await _get("settings", f"key=eq.{key}&select=value")
    return rows[0]["value"] if rows else None

async def set_setting(key, value):
    await upsert("settings", {"key": key, "value": str(value)})

# ── Verified ──
async def is_verified(uid):
    rows = await _get("verified", f"uid=eq.{uid}&select=uid")
    return len(rows) > 0

async def save_verified(uid, phone, full_name, username):
    await upsert("verified", {"uid": str(uid), "phone": phone, "full_name": full_name, "username": username, "verified_at": datetime.now().isoformat()})

async def get_verified_phone(uid):
    rows = await _get("verified", f"uid=eq.{uid}&select=phone")
    return rows[0]["phone"] if rows else "—"

# ── Subscribers ──
async def get_subscriber(uid):
    rows = await _get("subscribers", f"uid=eq.{uid}")
    return rows[0] if rows else None

async def save_subscriber(uid, plan_key, expires_at, is_trial=False):
    await upsert("subscribers", {"uid": str(uid), "plan_key": plan_key, "expires_at": expires_at.isoformat(), "activated_at": datetime.now().isoformat(), "is_trial": is_trial})

async def delete_subscriber(uid):
    await _delete("subscribers", f"uid=eq.{uid}")

async def get_all_expired():
    now = datetime.now().isoformat()
    return await _get("subscribers", f"expires_at=lte.{now}")

# ── Trials ──
async def used_trial(uid):
    rows = await _get("trials", f"uid=eq.{uid}&select=uid")
    return len(rows) > 0

async def save_trial(uid, expires_at):
    await upsert("trials", {"uid": str(uid), "started_at": datetime.now().isoformat(), "expires_at": expires_at.isoformat()})

# ── Pending ──
async def get_pending(uid):
    rows = await _get("pending", f"uid=eq.{uid}")
    return rows[0] if rows else None

async def save_pending(uid, plan_key, full_name, username, phone, status):
    await upsert("pending", {"uid": str(uid), "plan_key": plan_key, "full_name": full_name, "username": username, "phone": phone, "status": status, "requested_at": datetime.now().isoformat()})

async def update_pending_status(uid, status):
    await _patch("pending", {"status": status}, f"uid=eq.{uid}")

async def delete_pending(uid):
    await _delete("pending", f"uid=eq.{uid}")

# ── Channel Users ──
async def save_channel_user(uid, name, username):
    await upsert("channel_users", {"uid": str(uid), "name": name, "username": username, "joined": datetime.now().isoformat()})

async def get_channel_users_count():
    rows = await _get("channel_users", "select=uid")
    return len(rows)

async def get_all_channel_users():
    return await _get("channel_users", "select=uid")

# ── Stats ──
async def get_stats():
    now = datetime.now().isoformat()
    verified    = await _get("verified",    "select=uid")
    trials      = await _get("trials",      "select=uid")
    active      = await _get("subscribers", f"is_trial=eq.false&expires_at=gt.{now}&select=uid")
    expired     = await _get("subscribers", f"is_trial=eq.false&expires_at=lte.{now}&select=uid")
    return len(verified), len(trials), len(active), len(expired)
