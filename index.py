import time
import logging
from datetime import datetime, timedelta
from contextlib import contextmanager
import sqlite3

from telegram import (
    InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton,
    ReactionTypeEmoji,
    Update
)
from telegram.error import Forbidden, TelegramError
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# ⚠️ اطلاعات اصلی ربات خود را اینجا وارد کنید:
TOKEN = "8942433541:AAG_lvWnQkj_9S5WWM4fKU8TXmcDZjbZq4E"
OWNER_ID = 8782675695
CHANNEL_ID = "@MobinaVpn"

DEFAULT_CARD_NUMBER = "5029081013823121"
DEFAULT_CARD_NAME = "پروانه ابراهیمی"
REFERRAL_BONUS = 5000
DEFAULT_DICE_REWARD = 20000
DEFAULT_DICE_COOLDOWN_HOURS = 24

DB_NAME = 'snibase_final_v10.db'
user_states = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger("vpn_bot")

START_TEXT = (
    "اشتراک‌های پر سرعت اینجاست! 💎⚡️\n\n"
    "🔥 پایدار و پرسرعت حتی در نت ملی\n"
    "🌐 سازگار با همه نوع اینترنت\n"
    "🌼 بدون محدودیت کاربر\n\n"
    "با تضمین بازگشت وجه در صورت 24 ساعت قطعی ✅\n\n"
    "از منوی زیر بخش مورد نظر خود را انتخاب کنید ⬇️"
)

RULES_TEXT = (
    "📜 <b>ضوابط استفاده از خدمات شبکه</b>\n\n"
    "1️⃣ هر اشتراک تنها متعلق به یک کاربر است\n\n"
    "2️⃣ امکان عودت وجه یا تعویض سرویس وجود ندارد\n\n"
    "3️⃣ ارسال رسید جعلی موجب مسدودیت دائم می‌شود\n\n"
    "4️⃣ ورود به ربات به منزله پذیرش ضوابط است"
)

AGENCY_SUCCESS_TEXT = (
    "👑 <b>تاییدیه ارتقای حساب به سطح نمایندگی</b>\n\n"
    "همکار گرامی، حساب شما با موفقیت به سطح <b>نماینده فروش</b> ارتقا یافت. 🎉\n\n"
    "🛠️ <b>قابلیت‌های فعال شده برای شما:</b>\n\n"
    "1️⃣ 💸 <b>تخفیف دائم 10 درصدی:</b> از این پس تمامی سرویس‌های ربات برای شما با 10% قیمت کمتر محاسبه و کسر می‌شود.\n\n"
    "2️⃣ 🎁 <b>سهمیه تست روزانه:</b> شما می‌توانید روزانه 1 عدد اکانت تست رایگان جهت ارائه به مشتریان خود از ربات دریافت کنید."
)

HELP_TEXT = (
    "📖 <b>راهنمای ربات</b>\n\n"
    "▫️ /start - شروع / بازگشت به منوی اصلی\n"
    "▫️ /cancel - لغو عملیات جاری\n"
    "▫️ /help - نمایش همین راهنما\n\n"
    "برای خرید، شارژ کیف پول، دریافت اکانت تست یا شرکت در گردونه شانس از دکمه‌های پایین صفحه استفاده کنید 👇"
)

# --- برچسب دکمه‌های کیبورد اصلی (منویی) ---
BTN_BUY = "🛒 خرید اشتراک"
BTN_TEST = "🔑 اکانت تست"
BTN_SERVICES = "🛍️ سرویس‌های من"
BTN_WALLET = "🏦 کیف پول"
BTN_DICE = "🎲 گردونه شانس"
BTN_TUTORIALS = "📚 آموزش‌ها"
BTN_REF = "👥 زیرمجموعه‌گیری"
BTN_AGENCY = "🙋 درخواست نمایندگی"
BTN_SUPPORT = "☎️ پشتیبانی"
BTN_ADMIN = "👨‍💼 پنل مدیریت"
BTN_SHARE_PHONE = "📱 ارسال شماره تلفن"

PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"
_DIGIT_MAP = {}
for _i, _c in enumerate(PERSIAN_DIGITS):
    _DIGIT_MAP[_c] = str(_i)
for _i, _c in enumerate(ARABIC_DIGITS):
    _DIGIT_MAP[_c] = str(_i)

_last_action_at = {}


def to_en_digits(s: str) -> str:
    return "".join(_DIGIT_MAP.get(ch, ch) for ch in s.strip())


def parse_positive_int(s: str):
    s = to_en_digits(s)
    if not s.isdigit():
        return None
    v = int(s)
    return v if v > 0 else None


def parse_user_id(s: str):
    s = to_en_digits(s).strip()
    if not s.isdigit():
        return None
    return int(s)


def debounce(user_id, seconds=1.2) -> bool:
    now = time.time()
    if now - _last_action_at.get(user_id, 0) < seconds:
        return False
    _last_action_at[user_id] = now
    return True


def normalize_ir_phone(raw: str):
    """
    شماره را نرمال‌سازی می‌کند و فقط در صورتی که واقعاً یک شماره موبایل ایران (+98) باشد
    رشته‌ی نرمال‌شده (مثل 989123456789) را برمی‌گرداند، در غیر این صورت None.
    """
    if not raw:
        return None
    digits = to_en_digits(raw).strip().replace(" ", "").replace("-", "")
    digits = digits.lstrip("+")
    if digits.startswith("0098"):
        digits = "98" + digits[4:]
    elif digits.startswith("098"):
        digits = "98" + digits[3:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = "98" + digits[1:]
    if not digits.startswith("98"):
        return None
    if not digits.isdigit():
        return None
    if len(digits) != 12:  # 98 + 10 رقم
        return None
    return digits


# ----------------- دیتابیس -----------------
@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_NAME, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    try:
        yield conn
    finally:
        conn.close()


def ensure_column(conn, table, col, coltype):
    cols = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if col not in cols:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {coltype}")


def init_db():
    with get_conn() as conn:
        conn.execute('''CREATE TABLE IF NOT EXISTS users
                          (user_id INTEGER PRIMARY KEY, balance INTEGER DEFAULT 0, is_agent INTEGER DEFAULT 0,
                           is_banned INTEGER DEFAULT 0, has_accepted_rules INTEGER DEFAULT 0,
                           referred_by INTEGER DEFAULT 0, last_test_date TEXT, blocked_by_bot INTEGER DEFAULT 0)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS admins (user_id INTEGER PRIMARY KEY)''')
        conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (OWNER_ID,))
        conn.execute('''CREATE TABLE IF NOT EXISTS products (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, price INTEGER)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS configs (id INTEGER PRIMARY KEY AUTOINCREMENT, product_id INTEGER, type TEXT, content TEXT, is_used INTEGER DEFAULT 0)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS user_services (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, type TEXT, content TEXT, price INTEGER)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS transactions
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, amount INTEGER,
                           balance_after INTEGER, reason TEXT, created_at TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS pending_requests
                          (id INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT, user_id INTEGER,
                           product_id INTEGER, amount INTEGER, status TEXT DEFAULT 'pending', created_at TEXT)''')
        conn.execute('''CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)''')

        # مهاجرت ستون‌های جدید بدون از دست رفتن داده‌های قبلی
        ensure_column(conn, "configs", "used_by", "INTEGER")
        ensure_column(conn, "configs", "used_at", "TEXT")
        ensure_column(conn, "user_services", "created_at", "TEXT")
        ensure_column(conn, "products", "qr_file_id", "TEXT")
        ensure_column(conn, "products", "description", "TEXT")
        ensure_column(conn, "users", "phone_number", "TEXT")
        ensure_column(conn, "users", "phone_verified", "INTEGER DEFAULT 0")
        ensure_column(conn, "users", "last_dice_at", "TEXT")

        defaults = {
            "card_number": DEFAULT_CARD_NUMBER,
            "card_name": DEFAULT_CARD_NAME,
            "locked": "0",
            "phone_verify_required": "0",
            "dice_reward": str(DEFAULT_DICE_REWARD),
            "dice_cooldown_hours": str(DEFAULT_DICE_COOLDOWN_HOURS),
            "tutorial_app_text": "📲 لینک برنامه مورد نیاز هنوز توسط مدیریت تنظیم نشده است.",
            "tutorial_import_text": "🧭 آموزش وارد کردن هنوز توسط مدیریت تنظیم نشده است.",
        }
        for k, v in defaults.items():
            conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        conn.commit()


init_db()


def get_setting(key, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row[0] if row else default


def set_setting(key, value):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, str(value))
        )
        conn.commit()


def is_admin(user_id):
    with get_conn() as conn:
        res = conn.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,)).fetchone()
        return res is not None


def get_user(user_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT balance, is_agent, is_banned, has_accepted_rules, referred_by, last_test_date, "
            "phone_verified, last_dice_at FROM users WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        if not row:
            conn.execute(
                "INSERT OR IGNORE INTO users (user_id, balance, is_agent, is_banned, has_accepted_rules, referred_by, last_test_date) "
                "VALUES (?, 0, 0, 0, 0, 0, NULL)", (user_id,)
            )
            conn.commit()
            row = (0, 0, 0, 0, 0, None, 0, None)
        return {
            "balance": row[0], "is_agent": row[1], "is_banned": row[2], "has_accepted_rules": row[3],
            "referred_by": row[4], "last_test_date": row[5], "phone_verified": row[6], "last_dice_at": row[7]
        }


def adjust_balance(user_id, delta, reason="تنظیم موجودی"):
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("INSERT OR IGNORE INTO users (user_id, balance) VALUES (?, 0)", (user_id,))
        conn.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (delta, user_id))
        bal = conn.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO transactions (user_id, amount, balance_after, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, delta, bal, reason, datetime.now().isoformat())
        )
        conn.commit()
        return bal


def get_products():
    with get_conn() as conn:
        return conn.execute("SELECT id, name, price FROM products").fetchall()


def get_product_info(product_id):
    with get_conn() as conn:
        return conn.execute("SELECT id, name, price, qr_file_id, description FROM products WHERE id=?", (product_id,)).fetchone()


def get_stock_count(product_id):
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM configs WHERE product_id=? AND is_used=0", (product_id,)).fetchone()[0]


# ----- عملیات اتمیک ضدِ رِیس‌کاندیشن -----
def claim_config_locked(conn, product_id, user_id):
    """
    باید داخل یک تراکنش BEGIN IMMEDIATE از قبل باز شده صدا زده شود.
    BEGIN IMMEDIATE قفل نوشتن را فوراً می‌گیرد، پس هیچ اتصال دیگری نمی‌تواند
    همزمان همان کانفیگ را بردارد؛ دقیقاً همان تضمینی که برای رفع باگ دو-کاربر-یک-کانفیگ لازم است.
    """
    row = conn.execute(
        "SELECT id, content FROM configs WHERE product_id=? AND is_used=0 ORDER BY id LIMIT 1", (product_id,)
    ).fetchone()
    if not row:
        return None
    conn.execute(
        "UPDATE configs SET is_used=1, used_by=?, used_at=? WHERE id=?",
        (user_id, datetime.now().isoformat(), row[0])
    )
    return row  # (id, content)


def claim_free_test(user_id, is_agent, today_str):
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT last_test_date FROM users WHERE user_id=?", (user_id,)).fetchone()
        last_test_date = row[0] if row else None
        if not is_agent and last_test_date is not None:
            conn.rollback()
            return {"ok": False, "reason": "already_used"}
        if is_agent and last_test_date == today_str:
            conn.rollback()
            return {"ok": False, "reason": "daily_limit"}

        claimed = claim_config_locked(conn, 0, user_id)
        if not claimed:
            conn.rollback()
            return {"ok": False, "reason": "out_of_stock"}

        conn.execute(
            "INSERT INTO user_services (user_id, type, content, price, created_at) VALUES (?, 'تست رایگان', ?, 0, ?)",
            (user_id, claimed[1], datetime.now().isoformat())
        )
        conn.execute("UPDATE users SET last_test_date = ? WHERE user_id = ?", (today_str, user_id))
        conn.commit()
        return {"ok": True, "content": claimed[1]}


def purchase_with_wallet(user_id, product_id):
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        prod = conn.execute("SELECT name, price FROM products WHERE id=?", (product_id,)).fetchone()
        if not prod:
            conn.rollback()
            return {"ok": False, "reason": "no_product"}

        agent_row = conn.execute("SELECT is_agent FROM users WHERE user_id=?", (user_id,)).fetchone()
        is_agent = agent_row[0] if agent_row else 0
        final_price = int(prod[1] * 0.9) if is_agent else prod[1]

        cur = conn.execute(
            "UPDATE users SET balance = balance - ? WHERE user_id=? AND balance >= ?",
            (final_price, user_id, final_price)
        )
        if cur.rowcount == 0:
            conn.rollback()
            return {"ok": False, "reason": "insufficient_balance"}

        claimed = claim_config_locked(conn, product_id, user_id)
        if not claimed:
            conn.rollback()
            return {"ok": False, "reason": "out_of_stock"}

        conn.execute(
            "INSERT INTO user_services (user_id, type, content, price, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, prod[0], claimed[1], final_price, datetime.now().isoformat())
        )
        bal_after = conn.execute("SELECT balance FROM users WHERE user_id=?", (user_id,)).fetchone()[0]
        conn.execute(
            "INSERT INTO transactions (user_id, amount, balance_after, reason, created_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, -final_price, bal_after, f"خرید {prod[0]}", datetime.now().isoformat())
        )
        conn.commit()
        return {"ok": True, "content": claimed[1], "price": final_price, "name": prod[0]}


def create_pending_request(req_type, user_id, product_id=None, amount=None):
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO pending_requests (type, user_id, product_id, amount, status, created_at) VALUES (?, ?, ?, ?, 'pending', ?)",
            (req_type, user_id, product_id, amount, datetime.now().isoformat())
        )
        conn.commit()
        return cur.lastrowid


def resolve_pending_request(req_id, new_status):
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, type, user_id, product_id, amount FROM pending_requests WHERE id=? AND status='pending'",
            (req_id,)
        ).fetchone()
        if not row:
            conn.rollback()
            return None
        conn.execute("UPDATE pending_requests SET status=? WHERE id=?", (new_status, req_id))
        conn.commit()
        return {"id": row[0], "type": row[1], "user_id": row[2], "product_id": row[3], "amount": row[4]}


def claim_dice_turn(user_id, cooldown_hours):
    """
    اتمیک: فقط اگر کول‌داون تمام شده باشد نوبت را رزرو می‌کند (زمان را فوراً آپدیت می‌کند)
    تا حتی با تپ همزمان دو درخواست، کاربر دو جایزه نگیرد.
    """
    with get_conn() as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute("SELECT last_dice_at FROM users WHERE user_id=?", (user_id,)).fetchone()
        last_at = row[0] if row else None
        now = datetime.now()
        if last_at:
            try:
                last_dt = datetime.fromisoformat(last_at)
                if now - last_dt < timedelta(hours=cooldown_hours):
                    remaining = timedelta(hours=cooldown_hours) - (now - last_dt)
                    conn.rollback()
                    return {"ok": False, "remaining": remaining}
            except ValueError:
                pass
        conn.execute("UPDATE users SET last_dice_at = ? WHERE user_id = ?", (now.isoformat(), user_id))
        conn.commit()
        return {"ok": True}


async def safe_send(bot, chat_id, *args, **kwargs):
    try:
        return await bot.send_message(chat_id, *args, **kwargs)
    except Forbidden:
        with get_conn() as conn:
            conn.execute("UPDATE users SET blocked_by_bot = 1 WHERE user_id = ?", (chat_id,))
            conn.commit()
        return None
    except TelegramError as e:
        logger.warning(f"خطا در ارسال پیام به {chat_id}: {e}")
        return None


async def react_heart(update: Update):
    """تلاش برای زدن ری‌اکشن ❤️ روی پیام کاربر؛ اگر نسخه کتابخانه پشتیبانی نکند، بی‌سروصدا رد می‌شود"""
    try:
        # نکته مهم: پارامتر reaction باید یک لیست باشد، نه رشته‌ی تکی؛
        # چون رشته در پایتون قابل پیمایش است و ممکن است به‌اشتباه کاراکتر به کاراکتر تفسیر شود.
        await update.message.set_reaction(reaction=[ReactionTypeEmoji(emoji="❤️")])
    except Exception as e:
        logger.warning(f"امکان ارسال ری‌اکشن وجود نداشت: {e}")


async def check_join(bot, user_id):
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except TelegramError as e:
        logger.warning(f"خطا در بررسی عضویت کاربر {user_id} در کانال: {e}")
        return False


# ----------------- کیبورد اصلی (منویی/Reply) -----------------
def get_main_reply_keyboard(user_id):
    rows = [
        [KeyboardButton(BTN_BUY), KeyboardButton(BTN_TEST)],
        [KeyboardButton(BTN_SERVICES), KeyboardButton(BTN_WALLET)],
        [KeyboardButton(BTN_DICE), KeyboardButton(BTN_TUTORIALS)],
        [KeyboardButton(BTN_REF), KeyboardButton(BTN_AGENCY)],
        [KeyboardButton(BTN_SUPPORT)],
    ]
    if is_admin(user_id):
        rows.append([KeyboardButton(BTN_ADMIN)])
    return ReplyKeyboardMarkup(rows, resize_keyboard=True, is_persistent=True)


def get_phone_request_keyboard():
    return ReplyKeyboardMarkup(
        [[KeyboardButton(BTN_SHARE_PHONE, request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )


# ----------------- کیبوردهای شیشه‌ای (Inline) -----------------
def get_admin_inline_keyboard():
    keyboard = [
        [InlineKeyboardButton("📦 مخزن", callback_data="adm_makhzan"), InlineKeyboardButton("📊 آمار ربات", callback_data="adm_stats")],
        [InlineKeyboardButton("🛠️ مدیریت پیشرفته کاربران", callback_data="adm_advanced")],
        [InlineKeyboardButton("📚 مدیریت آموزش‌ها", callback_data="adm_tutorials")],
        [InlineKeyboardButton("⚙️ تنظیمات عمومی", callback_data="adm_settings"), InlineKeyboardButton("📢 ارسال پیام همگانی", callback_data="adm_broadcast")],
        [InlineKeyboardButton("✖️ بستن", callback_data="close_inline")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_advanced_users_inline():
    keyboard = [
        [InlineKeyboardButton("🔍 اطلاعات کاربر", callback_data="cap_1"), InlineKeyboardButton("➕ افزایش موجودی", callback_data="cap_2")],
        [InlineKeyboardButton("➖ کسر موجودی", callback_data="cap_3"), InlineKeyboardButton("🚫 مسدود کردن", callback_data="cap_4")],
        [InlineKeyboardButton("🟢 رفع مسدودیت", callback_data="cap_5"), InlineKeyboardButton("👑 اعطای نمایندگی", callback_data="cap_6")],
        [InlineKeyboardButton("👤 لغو نمایندگی", callback_data="cap_7"), InlineKeyboardButton("🎁 شارژ همگانی", callback_data="cap_8")],
        [InlineKeyboardButton("❌ حذف سرویس‌ها", callback_data="cap_9"), InlineKeyboardButton("🧹 حذف غیرفعالین", callback_data="cap_10")],
        [InlineKeyboardButton("➕ افزودن ادمین", callback_data="cap_11"), InlineKeyboardButton("❌ عزل ادمین", callback_data="cap_12")],
        [InlineKeyboardButton("📊 لیست ادمین‌ها", callback_data="cap_13"), InlineKeyboardButton("📉 کسر شارژ همگانی", callback_data="cap_14")],
        [InlineKeyboardButton("🔓 فعالسازی کل کاربران", callback_data="cap_15"), InlineKeyboardButton("🔒 قفل موقت ربات", callback_data="cap_16")],
        [InlineKeyboardButton("🔗 تنظیم دستی معرف", callback_data="cap_17"), InlineKeyboardButton("📱 وضعیت احراز شماره", callback_data="cap_18")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin_inline")]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_receipt_management_keyboard(req_id, action_type):
    if action_type == "charge":
        cb_approve, cb_reject = f"ok_dp_{req_id}", f"no_dp_{req_id}"
    elif action_type == "buy":
        cb_approve, cb_reject = f"ok_by_{req_id}", f"no_by_{req_id}"
    elif action_type == "agency_req":
        cb_approve, cb_reject = f"ok_ag_{req_id}", f"no_ag_{req_id}"
        return InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ تایید درخواست", callback_data=cb_approve), InlineKeyboardButton("❌ رد درخواست", callback_data=cb_reject)]
        ])
    else:
        raise ValueError("نوع نامعتبر")

    keyboard = [
        [InlineKeyboardButton("✅ تایید رسید", callback_data=cb_approve), InlineKeyboardButton("❌ رد رسید", callback_data=cb_reject)],
    ]
    return InlineKeyboardMarkup(keyboard)


# ----------------- توابع نمایش منوها (مشترک) -----------------
async def show_buy_menu(message):
    prods = get_products()
    if not prods:
        await message.reply_text("🙁 در حال حاضر هیچ پلنی برای فروش تعریف نشده است.")
        return
    keyboard = []
    for p in prods:
        stock = get_stock_count(p[0])
        label = f"📦 {p[1]} - {p[2]:,} تومان" + ("" if stock > 0 else " (ناموجود ❌)")
        keyboard.append([InlineKeyboardButton(label, callback_data=f"buy_prod_{p[0]}")])
    await message.reply_html("🛒 <b>لیست پلن‌های ارتباطی موجود</b>\n\nیک پلن را انتخاب کنید 👇", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_services_menu(message, user_id):
    with get_conn() as conn:
        rows = conn.execute("SELECT id, type FROM user_services WHERE user_id = ?", (user_id,)).fetchall()
    if rows:
        keyboard = [[InlineKeyboardButton(f"📦 {r[1]}", callback_data=f"view_service_{r[0]}")] for r in rows]
        await message.reply_text("🛍️ لیست سرویس‌های خریداری‌شده شما:", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await message.reply_text("😕 همراه گرامی، هیچ سرویس فعالی برای شما یافت نشد.")


async def show_wallet_menu(message, u):
    keyboard = [
        [InlineKeyboardButton("➕ افزایش موجودی (کارت به کارت)", callback_data="wallet_charge")],
        [InlineKeyboardButton("📜 تاریخچه تراکنش‌ها", callback_data="wallet_history")],
    ]
    wallet_text = (
        f"🏦 <b>میز کار و مدیریت تراز مالی حساب کاربر</b>\n\n"
        f"💰 موجودى فعلى حساب شما: <b>{u['balance']:,} تومان</b>\n\n"
        f"✅ وضعیت دسترسی: معتبر و فعال\n\n"
        f"جهت افزایش اعتبار از دکمه زیر استفاده فرمایید 👇"
    )
    await message.reply_html(wallet_text, reply_markup=InlineKeyboardMarkup(keyboard))


async def show_tutorials_menu(message):
    keyboard = [
        [InlineKeyboardButton("📲 برنامه مورد نیاز", callback_data="tut_app")],
        [InlineKeyboardButton("🧭 آموزش وارد کردن", callback_data="tut_import")],
    ]
    await message.reply_html("📚 <b>بخش آموزش‌ها</b>\n\nموضوع مورد نظر خود را انتخاب کنید 👇", reply_markup=InlineKeyboardMarkup(keyboard))


async def show_referral_menu(message, context, user_id):
    bot_info = await context.bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    ref_text = (
        f"👥 <b>بخش کسب درآمد و دعوت از دوستان</b>\n\n"
        f"با اشتراک‌گذاری لینک خود دوستانتان را دعوت کنید 🤝\n\n"
        f"🎁 پاداش مالی هر دعوت موفق: <b>{REFERRAL_BONUS:,} تومان</b> اعتبار آنی\n\n"
        f"🔗 لینک دعوت اختصاصی شما:\n{ref_link}"
    )
    await message.reply_html(ref_text)


async def show_agency_menu(message, user_id, u):
    """اگر درخواست جدیدی ثبت شود، شناسه‌ی آن را برمی‌گرداند تا برای ادمین ارسال شود؛ در غیر این صورت None"""
    if u["is_agent"] == 1:
        await message.reply_text("👑 حساب شما هم‌اکنون روی وضعیت همکاری تنظیم است.")
        return None
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT id FROM pending_requests WHERE type='agency' AND user_id=? AND status='pending'", (user_id,)
        ).fetchone()
    if existing:
        await message.reply_text("⏳ درخواست نمایندگی قبلی شما در حال بررسی است.")
        return None

    req_id = create_pending_request("agency", user_id)
    await message.reply_html(
        "🙋 <b>تقاضای شما جهت ارتقای حساب ثبت شد</b>\n\n"
        "این درخواست جهت بررسی سوابق ارسال گردید 📨\n\n"
        "نتیجه بررسی از طریق همین پیام‌رسان به شما اعلام می‌شود\n\n"
        "از تمایل شما جهت همکاری سپاسگزاریم 🌹"
    )
    return req_id


# ----------------- هندلرهای دستورات و پیام‌ها -----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    try:
        user_states[user_id] = None
        u = get_user(user_id)
        if u["is_banned"] == 1:
            return

        await react_heart(update)

        with get_conn() as conn:
            conn.execute("UPDATE users SET blocked_by_bot = 0 WHERE user_id = ?", (user_id,))
            conn.commit()

        if get_setting("locked", "0") == "1" and not is_admin(user_id):
            await update.message.reply_html("🚧 <b>ربات موقتاً در دست تعمیرات است</b>")
            return

        if u["referred_by"] == 0 and context.args:
            ref_id = to_en_digits(context.args[0])
            if ref_id.isdigit() and int(ref_id) != user_id:
                with get_conn() as conn:
                    conn.execute("UPDATE users SET referred_by = ? WHERE user_id = ? AND referred_by = 0", (int(ref_id), user_id))
                    conn.commit()

        if not await check_join(context.bot, user_id):
            keyboard = [
                [InlineKeyboardButton("📢 عضویت در کانال", url=f"https://t.me/{CHANNEL_ID.replace('@', '')}")],
                [InlineKeyboardButton("✅ تایید عضویت مکرر", callback_data="check_membership")]
            ]
            await update.message.reply_html(
                f"👋 <b>درود بر شما مشترک گرامی</b>\n\nجهت استفاده از خدمات شبکه ابتدا در کانال زیر عضو شوید 🙏\n\n{CHANNEL_ID}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            return

        if u["has_accepted_rules"] == 0:
            keyboard = [[InlineKeyboardButton("✅ ضوابط را می‌پذیرم", callback_data="accept_rules")]]
            await update.message.reply_html(RULES_TEXT, reply_markup=InlineKeyboardMarkup(keyboard))
            return

        await update.message.reply_html(START_TEXT, reply_markup=get_main_reply_keyboard(user_id))
    except Exception:
        logger.exception(f"خطا در پردازش /start برای کاربر {user_id}")
        try:
            await update.message.reply_text("⚠️ خطایی در پردازش درخواست رخ داد. لطفاً به ادمین اطلاع دهید.")
        except Exception:
            pass


async def cancel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_states[user_id] = None
    await update.message.reply_text("✅ عملیات جاری لغو شد.", reply_markup=get_main_reply_keyboard(user_id))


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html(HELP_TEXT)


async def diag_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور تشخیصی موقت (فقط ادمین): نسخه کتابخونه و نتیجه دقیق تلاش برای ری‌اکشن را مستقیم در تلگرام گزارش می‌دهد"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return

    import telegram
    lines = [f"📦 نسخه python-telegram-bot: <code>{telegram.__version__}</code>"]

    has_method = hasattr(update.message, "set_reaction")
    lines.append(f"🔍 متد set_reaction وجود دارد: {'بله' if has_method else 'خیر'}")

    if has_method:
        try:
            await update.message.set_reaction(reaction=[ReactionTypeEmoji(emoji="❤️")])
            lines.append("✅ فراخوانی set_reaction بدون خطا انجام شد (اگر باز هم قلب ندیدید، مشکل نمایشی/کش تلگرام است).")
        except Exception as e:
            lines.append(f"❌ خطای دقیق:\n<code>{type(e).__name__}: {e}</code>")

    await update.message.reply_html("\n\n".join(lines))


# ----------------- کال‌بک‌های اینلاین -----------------
async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    u = get_user(user_id)
    if u["is_banned"] == 1:
        return

    data = query.data
    if not debounce(user_id):
        return

    if data == "close_inline":
        try:
            await query.message.delete()
        except Exception:
            await query.edit_message_reply_markup(reply_markup=None)

    elif data in ("main_menu", "menu_admin_inline"):
        try:
            await query.edit_message_reply_markup(reply_markup=None)
        except Exception:
            pass
        if data == "menu_admin_inline" and is_admin(user_id):
            await context.bot.send_message(query.message.chat_id, "🛠️ به میز کار مدیریت خوش آمدید:", reply_markup=get_admin_inline_keyboard())

    elif data == "menu_test":
        today_str = datetime.now().strftime("%Y-%m-%d")
        result = claim_free_test(user_id, u["is_agent"], today_str)
        if result["ok"]:
            test_text = f"🔑 <b>پروفایل اتصال آزمایشی صادر شد</b>\n\n<code>{result['content']}</code>"
            await query.edit_message_text(test_text, parse_mode='HTML')
        else:
            reason = result["reason"]
            if reason == "already_used":
                msg = "⚠️ شما قبلاً سهمیه تست رایگان خود را دریافت کرده‌اید"
            elif reason == "daily_limit":
                msg = "👑 نماینده گرامی، شما سهمیه امروز خود (1 اکانت تست در روز) را دریافت کرده‌اید. فردا مجدداً تلاش کنید."
            else:
                msg = "📭 در حال حاضر اکانت تستی در مخزن موجود نیست"
            await query.edit_message_text(msg)

    elif data == "wallet_history":
        with get_conn() as conn:
            rows = conn.execute(
                "SELECT amount, balance_after, reason, created_at FROM transactions WHERE user_id=? ORDER BY id DESC LIMIT 10",
                (user_id,)
            ).fetchall()
        if rows:
            lines = ["📜 <b>۱۰ تراکنش اخیر شما:</b>\n"]
            for amt, bal, reason, ts in rows:
                sign = "+" if amt >= 0 else ""
                when = ts.split("T")[0] if ts else ""
                lines.append(f"{sign}{amt:,} تومان — {reason} ({when})")
            text = "\n".join(lines)
        else:
            text = "📭 هیچ تراکنشی برای شما ثبت نشده است."
        await query.edit_message_text(text, parse_mode='HTML')

    elif data == "wallet_charge":
        phone_required = get_setting("phone_verify_required", "0") == "1"
        if phone_required and not u["phone_verified"]:
            user_states[user_id] = "waiting_for_phone_verification"
            await context.bot.send_message(
                query.message.chat_id,
                "🔒 <b>احراز هویت شماره تلفن</b>\n\nپیش از شارژ کیف پول لازم است شماره تلفن ایرانی (+98) خود را از طریق دکمه زیر ارسال کنید.\n\nاین کار خودکار و آنی انجام می‌شود ✅",
                parse_mode='HTML',
                reply_markup=get_phone_request_keyboard()
            )
            return
        user_states[user_id] = "waiting_for_charge_amount"
        await context.bot.send_message(query.message.chat_id, "💳 <b>بخش افزایش موجودی حساب</b>\n\nلطفاً مبلغ مورد نظر خود را به تومان و به عدد وارد نمایید:", parse_mode='HTML')

    elif data == "tut_app":
        text = get_setting("tutorial_app_text", "تنظیم نشده")
        await query.edit_message_text(f"📲 <b>برنامه مورد نیاز</b>\n\n{text}", parse_mode='HTML')

    elif data == "tut_import":
        text = get_setting("tutorial_import_text", "تنظیم نشده")
        await query.edit_message_text(f"🧭 <b>آموزش وارد کردن</b>\n\n{text}", parse_mode='HTML')

    elif data == "menu_agency":
        req_id = await show_agency_menu(query.message, user_id, u)
        if req_id:
            username = f"@{query.from_user.username}" if query.from_user.username else "فاقد شناسه"
            markup = get_receipt_management_keyboard(req_id, "agency_req")
            await safe_send(context.bot, OWNER_ID, f"🙋 درخواست نمایندگی\n\nآیدی: {user_id}\n\nیوزرنیم: {username}", reply_markup=markup)

    # --- پنل مدیریت: مخزن ---
    elif data == "adm_makhzan":
        if not is_admin(user_id):
            return
        test_count = get_stock_count(0)
        keyboard = [[InlineKeyboardButton(f"🔑 مخزن تست (موجود: {test_count})", callback_data="m_manage_0")]]
        for p in get_products():
            keyboard.append([InlineKeyboardButton(f"📦 مخزن اشتراک: {p[1]} (موجود: {get_stock_count(p[0])})", callback_data=f"m_manage_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin_inline")])
        await query.edit_message_text("📦 انبار مرکزی؛ دسته مورد نظر را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("m_manage_"):
        if not is_admin(user_id):
            return
        p_id = int(data.split("_")[2])
        available_count = get_stock_count(p_id)
        keyboard = [
            [InlineKeyboardButton("➕ افزودن کانفیگ", callback_data=f"m_add_{p_id}"), InlineKeyboardButton("🗑️ پاکسازی", callback_data=f"m_rst_{p_id}")],
        ]
        if p_id != 0:
            keyboard.append([InlineKeyboardButton("🖼 تنظیم QR / راهنما", callback_data=f"m_qr_{p_id}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت به مخزن", callback_data="adm_makhzan")])
        await query.edit_message_text(f"📦 <b>تنظیمات مخزن کد {p_id}</b>\n\nتعداد موجود: {available_count}\n\nیک عملیات را انتخاب کنید:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif data.startswith("m_qr_"):
        if not is_admin(user_id):
            return
        p_id = int(data.split("_")[2])
        user_states[user_id] = {"action": "waiting_for_product_qr", "product_id": p_id}
        await context.bot.send_message(query.message.chat_id, "🖼 یک تصویر QR / راهنما برای این محصول ارسال کنید، یا برای رد شدن عبارت «رد» را بفرستید:")

    elif data == "adm_tutorials":
        if not is_admin(user_id):
            return
        keyboard = [
            [InlineKeyboardButton("📲 ویرایش متن برنامه مورد نیاز", callback_data="adm_edit_tut_app")],
            [InlineKeyboardButton("🧭 ویرایش متن آموزش وارد کردن", callback_data="adm_edit_tut_import")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin_inline")],
        ]
        await query.edit_message_text("📚 مدیریت متن‌های آموزشی:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "adm_edit_tut_app":
        if not is_admin(user_id):
            return
        user_states[user_id] = "waiting_for_tutorial_app"
        await context.bot.send_message(query.message.chat_id, "✍️ متن/لینک جدید «برنامه مورد نیاز» را ارسال کنید:")

    elif data == "adm_edit_tut_import":
        if not is_admin(user_id):
            return
        user_states[user_id] = "waiting_for_tutorial_import"
        await context.bot.send_message(query.message.chat_id, "✍️ متن جدید «آموزش وارد کردن» را ارسال کنید:")

    elif data == "adm_stats":
        if not is_admin(user_id):
            return
        with get_conn() as conn:
            total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            total_configs = conn.execute("SELECT COUNT(*) FROM configs WHERE is_used = 0").fetchone()[0]
            total_sales = conn.execute("SELECT COUNT(*) FROM user_services").fetchone()[0]
            pending_count = conn.execute("SELECT COUNT(*) FROM pending_requests WHERE status='pending'").fetchone()[0]
            blocked_count = conn.execute("SELECT COUNT(*) FROM users WHERE blocked_by_bot=1").fetchone()[0]
            verified_count = conn.execute("SELECT COUNT(*) FROM users WHERE phone_verified=1").fetchone()[0]
        phone_status = "🔓 غیرفعال" if get_setting("phone_verify_required", "0") == "0" else "🔒 فعال"
        msg_text = (
            f"📊 آمار اتوماسیون:\n\n👥 کاربران: {total_users}\n\n📦 مخزن: {total_configs}\n\n"
            f"🛒 سرویس‌ها: {total_sales}\n\n⏳ درخواست‌های در انتظار: {pending_count}\n\n"
            f"🚷 کاربران بلاک‌کرده ربات: {blocked_count}\n\n📱 کاربران احرازشده: {verified_count}\n\n"
            f"احراز شماره: {phone_status}"
        )
        await query.edit_message_text(msg_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin_inline")]]))

    elif data == "adm_advanced":
        if not is_admin(user_id):
            return
        await query.edit_message_text("⚙️ <b>کنسول مدیریت پیشرفته اعضا:</b>", reply_markup=get_advanced_users_inline(), parse_mode='HTML')

    elif data == "adm_settings":
        if not is_admin(user_id):
            return
        keyboard = [
            [InlineKeyboardButton("✏️ تغییر کارت بانکی", callback_data="adm_change_card")],
            [InlineKeyboardButton("➕ ساخت پلن جدید", callback_data="adm_add_btn")],
        ]
        for p in get_products():
            keyboard.append([InlineKeyboardButton(f"❌ حذف پلن: {p[1]}", callback_data=f"delprod_{p[0]}")])
        keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="menu_admin_inline")])
        await query.edit_message_text("⚙️ کنترلر تنظیمات عمومی:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "adm_change_card":
        if not is_admin(user_id):
            return
        user_states[user_id] = "waiting_for_new_card"
        await context.bot.send_message(query.message.chat_id, "💳 شماره کارت 16 رقمی مقصد جدید را بفرستید:")

    elif data == "adm_add_btn":
        if not is_admin(user_id):
            return
        user_states[user_id] = "waiting_new_btn_name"
        await context.bot.send_message(query.message.chat_id, "✍️ نام پلن جدید را وارد کنید:")

    elif data == "adm_broadcast":
        if not is_admin(user_id):
            return
        user_states[user_id] = "waiting_for_broadcast"
        await context.bot.send_message(query.message.chat_id, "✍️ پیام همگانی خود را بنویسید:")

    elif data.startswith("ok_dp_"):
        if not is_admin(user_id):
            return
        req_id = int(data.split("_")[2])
        row = resolve_pending_request(req_id, "approved")
        if not row:
            await query.answer("⏱️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            return
        target, amt = row["user_id"], row["amount"]
        adjust_balance(target, amt, "شارژ کیف پول (کارت به کارت)")
        await query.edit_message_caption(caption=f"✅ تراکنش مالی تایید شد\n\nموجودی کاربر {target} به مبلغ {amt:,} ارتقا یافت.")
        await safe_send(context.bot, target, f"💰 <b>اطلاعیه واریز وجه</b>\n\nکیف پول شما با موفقیت شارژ شد ✅\n\nمبلغ {amt:,} تومان به حساب شما اضافه گردید", parse_mode='HTML')

    elif data.startswith("no_dp_"):
        if not is_admin(user_id):
            return
        req_id = int(data.split("_")[2])
        row = resolve_pending_request(req_id, "rejected")
        if not row:
            await query.answer("⏱️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            return
        target = row["user_id"]
        await query.edit_message_caption(caption=f"❌ رسید تراکنش مالی کاربر {target} رد شد.")
        await safe_send(context.bot, target, "❌ <b>اطلاعیه عدم تایید رسید</b>\n\nتراکنش ارسالی شما مورد تایید قرار نگرفت", parse_mode='HTML')

    elif data.startswith("adm_ban_"):
        if not is_admin(user_id):
            return
        target = int(data.split("_")[2])
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target,))
            conn.commit()
        await query.edit_message_caption(caption=f"🚫 کاربر {target} مسدود شد.")
        await safe_send(context.bot, target, "🚫 <b>حساب کاربری شما مسدود گردید</b>", parse_mode='HTML')

    elif data.startswith("ok_ag_"):
        if not is_admin(user_id):
            return
        req_id = int(data.split("_")[2])
        row = resolve_pending_request(req_id, "approved")
        if not row:
            await query.answer("⏱️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            return
        target = row["user_id"]
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_agent = 1 WHERE user_id = ?", (target,))
            conn.commit()
        await query.edit_message_text(f"👑 سطح کاربری {target} به وضعیت همکاری تغییر یافت.")
        await safe_send(context.bot, target, AGENCY_SUCCESS_TEXT, parse_mode='HTML')

    elif data.startswith("no_ag_"):
        if not is_admin(user_id):
            return
        req_id = int(data.split("_")[2])
        row = resolve_pending_request(req_id, "rejected")
        if not row:
            await query.answer("⏱️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            return
        target = row["user_id"]
        await query.edit_message_text(f"❌ درخواست نمایندگی کاربر {target} رد شد.")
        await safe_send(context.bot, target, "❌ <b>درخواست نمایندگی شما مورد تایید قرار نگرفت</b>", parse_mode='HTML')

    elif data.startswith("ok_by_"):
        if not is_admin(user_id):
            return
        req_id = int(data.split("_")[2])
        row = resolve_pending_request(req_id, "approved")
        if not row:
            await query.answer("⏱️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            return
        target, prod_id = row["user_id"], row["product_id"]

        with get_conn() as conn:
            conn.execute("BEGIN IMMEDIATE")
            claimed = claim_config_locked(conn, prod_id, target)
            if not claimed:
                conn.rollback()
                await query.answer("⚠️ خطا: مخزن محصول خالی است. ابتدا کانفیگ اضافه کنید سپس با «افزایش موجودی» کاربر را جبران کنید.", show_alert=True)
                return
            p_info = conn.execute("SELECT name, price, qr_file_id FROM products WHERE id=?", (prod_id,)).fetchone()
            agent_row = conn.execute("SELECT is_agent FROM users WHERE user_id=?", (target,)).fetchone()
            is_agent = agent_row[0] if agent_row else 0
            final_price = int(p_info[1] * 0.9) if is_agent else p_info[1]
            conn.execute(
                "INSERT INTO user_services (user_id, type, content, price, created_at) VALUES (?, ?, ?, ?, ?)",
                (target, p_info[0], claimed[1], final_price, datetime.now().isoformat())
            )
            conn.commit()

        await query.edit_message_caption(caption="✅ فیش خرید تایید و اشتراک صادر شد.")
        success_text = (
            f"🎉 <b>سرویس شما با موفقیت فعال شد</b>\n\n"
            f"📦 نوع اشتراک: {p_info[0]}\n\n"
            f"🔑 کلید اتصال:\n<code>{claimed[1]}</code>"
        )
        await safe_send(context.bot, target, success_text, parse_mode='HTML')
        if p_info[2]:
            try:
                await context.bot.send_photo(target, p_info[2], caption="🖼 راهنمای اتصال / QR")
            except TelegramError:
                pass

    elif data.startswith("no_by_"):
        if not is_admin(user_id):
            return
        req_id = int(data.split("_")[2])
        row = resolve_pending_request(req_id, "rejected")
        if not row:
            await query.answer("⏱️ این درخواست قبلاً پردازش شده است.", show_alert=True)
            return
        target = row["user_id"]
        await query.edit_message_caption(caption=f"❌ فیش خرید کاربر {target} رد شد.")
        await safe_send(context.bot, target, "❌ <b>درخواست خرید شما به دلیل اشکال در رسید رد شد</b>", parse_mode='HTML')

    elif data.startswith("delprod_"):
        if not is_admin(user_id):
            return
        p_id = int(data.split("_")[1])
        with get_conn() as conn:
            conn.execute("DELETE FROM products WHERE id = ?", (p_id,))
            conn.execute("DELETE FROM configs WHERE product_id = ? AND is_used = 0", (p_id,))
            conn.commit()
        await query.edit_message_text("🗑️ پلن و کانفیگ‌های استفاده‌نشده مربوطه حذف شدند.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 بازگشت", callback_data="adm_settings")]]))

    elif data.startswith("m_add_"):
        if not is_admin(user_id):
            return
        p_id = int(data.split("_")[2])
        user_states[user_id] = {"action": "waiting_for_configs_reply", "product_id": p_id}
        await context.bot.send_message(query.message.chat_id, "📥 لطفاً کلیدهای اتصال را ارسال فرمایید (هر خط یک کانفیگ):")

    elif data.startswith("m_rst_"):
        if not is_admin(user_id):
            return
        p_id = int(data.split("_")[2])
        user_states[user_id] = {"action": "waiting_for_reset_count", "product_id": p_id}
        await context.bot.send_message(query.message.chat_id, "🗑️ تعداد کانفیگ‌های استفاده‌نشده جهت حذف از مخزن را وارد کنید:")

    elif data.startswith("cap_"):
        if not is_admin(user_id):
            return
        cap_num = data.split("_")[1]
        user_states[user_id] = f"p_cap_{cap_num}"

        prompts = {
            "1": "🔍 آیدی عددی کاربر مورد نظر را وارد نمایید:",
            "2": "➕ فرمت افزایش موجودی: آیدی مقدار",
            "3": "➖ فرمت کسر موجودی: آیدی مقدار",
            "4": "🚫 آیدی کاربر جهت مسدودسازی کامل:",
            "5": "🟢 آیدی کاربر جهت رفع مسدودیت دائم:",
            "6": "👑 آیدی کاربر جهت اعطای دسترسی نمایندگی:",
            "7": "👤 آیدی کاربر جهت لغو دسترسی نمایندگی:",
            "8": "🎁 مبلغ اعتبار هدیه عمومی به همه کاربران (تومان):",
            "9": "❌ آیدی کاربر جهت سلب کلیه سرویس‌ها:",
            "11": "➕ آیدی عددی جهت افزودن ادمین جدید:",
            "12": "❌ آیدی ادمین جهت عزل:",
            "14": "📉 مبلغ کسر همگانی از همه کاربران (تومان):",
            "17": "فرمت تخصیص معرف: آیدی‌کاربر آیدی‌معرف",
        }
        if cap_num in prompts:
            await context.bot.send_message(query.message.chat_id, prompts[cap_num])
        elif cap_num == "10":
            user_states[user_id] = None
            with get_conn() as conn:
                cur = conn.execute("DELETE FROM users WHERE balance = 0 AND user_id NOT IN (SELECT DISTINCT user_id FROM user_services)")
                c = cur.rowcount
                conn.commit()
            await context.bot.send_message(query.message.chat_id, f"🧹 پاکسازی پایان یافت؛ تعداد {c} حساب کاربری غیرفعال حذف شدند.")
        elif cap_num == "13":
            user_states[user_id] = None
            with get_conn() as conn:
                rows = conn.execute("SELECT user_id FROM admins").fetchall()
            await context.bot.send_message(query.message.chat_id, "📊 <b>لیست مدیران سیستم</b>\n\n" + "\n".join([f"<code>{r[0]}</code>" for r in rows]), parse_mode='HTML')
        elif cap_num == "15":
            user_states[user_id] = None
            with get_conn() as conn:
                conn.execute("UPDATE users SET is_banned = 0")
                conn.commit()
            await context.bot.send_message(query.message.chat_id, "🔓 کلیه کاربران محدود شده رفع مسدودیت شدند.")
        elif cap_num == "16":
            user_states[user_id] = None
            new_state = "0" if get_setting("locked", "0") == "1" else "1"
            set_setting("locked", new_state)
            status = "🔒 قفل" if new_state == "1" else "🔓 باز"
            await context.bot.send_message(query.message.chat_id, f"وضعیت قفل موقت ربات به: {status} تغییر یافت.")
        elif cap_num == "18":
            user_states[user_id] = None
            new_state = "0" if get_setting("phone_verify_required", "0") == "1" else "1"
            set_setting("phone_verify_required", new_state)
            status = "🔒 فعال" if new_state == "1" else "🔓 غیرفعال"
            await context.bot.send_message(query.message.chat_id, f"وضعیت احراز شماره تلفن به: {status} تغییر یافت.")

    elif data == "check_membership":
        if await check_join(context.bot, user_id):
            try:
                await query.message.delete()
            except Exception:
                pass
            u2 = get_user(user_id)
            if u2["has_accepted_rules"] == 0:
                keyboard = [[InlineKeyboardButton("✅ ضوابط را می‌پذیرم", callback_data="accept_rules")]]
                await safe_send(context.bot, query.message.chat_id, RULES_TEXT, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')
            else:
                await safe_send(context.bot, query.message.chat_id, "✅ سیستم آماده بهره‌برداری است", reply_markup=get_main_reply_keyboard(user_id))
        else:
            await query.answer("❌ عضویت شما در کانال تایید نشد", show_alert=True)

    elif data == "accept_rules":
        with get_conn() as conn:
            conn.execute("UPDATE users SET has_accepted_rules = 1 WHERE user_id = ?", (user_id,))
            conn.commit()
        try:
            await query.message.delete()
        except Exception:
            pass
        if u["referred_by"] != 0:
            adjust_balance(u["referred_by"], REFERRAL_BONUS, f"پاداش دعوت کاربر {user_id}")
            await safe_send(context.bot, u["referred_by"], f"🎁 <b>پاداش دعوت کاربر جدید</b>\n\nیک کاربر از طریق لینک شما وارد شد\n\nمبلغ {REFERRAL_BONUS:,} تومان به کیف پول شما افزوده شد", parse_mode='HTML')
        await safe_send(context.bot, query.message.chat_id, f"✅ ضوابط با موفقیت تایید شد\n\n{START_TEXT}", reply_markup=get_main_reply_keyboard(user_id))

    elif data.startswith("buy_prod_"):
        p_id = int(data.split("_")[2])
        with get_conn() as conn:
            p_info = conn.execute("SELECT name, price FROM products WHERE id = ?", (p_id,)).fetchone()
        if not p_info:
            await query.answer("این محصول دیگر موجود نیست.", show_alert=True)
            return

        final_price = int(p_info[1] * 0.9) if u["is_agent"] == 1 else p_info[1]
        user_role = "👑 نماینده (10% تخفیف ویژه)" if u["is_agent"] == 1 else "👤 کاربر عادی"

        keyboard = [
            [InlineKeyboardButton("💳 کارت به کارت (ارسال فیش)", callback_data=f"direct_pay_{p_id}")],
            [InlineKeyboardButton("🏦 پرداخت آنلاین از کیف پول", callback_data=f"wallet_pay_{p_id}")],
            [InlineKeyboardButton("🔙 انصراف و بازگشت", callback_data="buy_back")]
        ]

        buy_text = (
            f"📦 <b>پلن انتخابی:</b> {p_info[0]}\n\n"
            f"💵 <b>قیمت اصلی:</b> {p_info[1]:,} تومان\n\n"
            f"💰 <b>قیمت برای شما:</b> {final_price:,} تومان ({user_role})\n\n"
            f"🏦 <b>تراز مالی شما:</b> {u['balance']:,} تومان"
        )
        await query.edit_message_text(buy_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='HTML')

    elif data == "buy_back":
        try:
            await query.message.delete()
        except Exception:
            pass
        await show_buy_menu(query.message)

    elif data.startswith("direct_pay_"):
        p_id = int(data.split("_")[2])
        user_states[user_id] = {"action": "direct_buy_receipt", "product_id": p_id}
        card_number = get_setting("card_number", DEFAULT_CARD_NUMBER)
        card_name = get_setting("card_name", DEFAULT_CARD_NAME)
        await context.bot.send_message(
            query.message.chat_id,
            f"💳 <b>صورت‌حساب واریز مستقیم</b>\n\nلطفاً مبلغ را به حساب زیر واریز نموده و فقط تصویر رسید را بفرستید 🧾\n\nشماره کارت:\n<code>{card_number}</code>\n\nدارنده حساب: {card_name}",
            parse_mode='HTML'
        )

    elif data.startswith("wallet_pay_"):
        p_id = int(data.split("_")[2])
        result = purchase_with_wallet(user_id, p_id)
        if result["ok"]:
            success_text = (
                f"🎉 <b>سرویس شما با موفقیت فعال شد</b>\n\n"
                f"📦 نوع اشتراک: {result['name']}\n\n"
                f"💰 مبلغ کسر شده: {result['price']:,} تومان\n\n"
                f"🔑 کلید اتصال:\n<code>{result['content']}</code>"
            )
            await query.edit_message_text(success_text, parse_mode='HTML')
            prod_full = get_product_info(p_id)
            if prod_full and prod_full[3]:
                try:
                    await context.bot.send_photo(user_id, prod_full[3], caption="🖼 راهنمای اتصال / QR")
                except TelegramError:
                    pass
        else:
            reason = result["reason"]
            if reason == "insufficient_balance":
                await query.answer("💸 تراز مالی شما برای خرید کافی نیست", show_alert=True)
            elif reason == "out_of_stock":
                await query.answer("📭 مخزن این سرویس موقتاً خالی است", show_alert=True)
            else:
                await query.answer("این محصول دیگر موجود نیست.", show_alert=True)

    elif data.startswith("view_service_"):
        srv_id = int(data.split("_")[2])
        with get_conn() as conn:
            row = conn.execute("SELECT type, content FROM user_services WHERE id = ? AND user_id = ?", (srv_id, user_id)).fetchone()
        if row:
            await context.bot.send_message(query.message.chat_id, f"🔍 <b>اطلاعات فنی سرویس</b>\n\n📦 نوع: {row[0]}\n\n🔑 کلید دسترسی:\n<code>{row[1]}</code>", parse_mode='HTML')

    else:
        await query.answer()


# ----------------- دیسپچر برچسب‌های کیبورد منویی -----------------
async def dispatch_menu_label(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, user_id: int, u: dict) -> bool:
    """اگر متن دریافتی یکی از دکمه‌های کیبورد منویی باشد آن را پردازش و True برمی‌گرداند"""
    if text == BTN_BUY:
        user_states[user_id] = None
        await show_buy_menu(update.message)
        return True
    if text == BTN_TEST:
        user_states[user_id] = None
        today_str = datetime.now().strftime("%Y-%m-%d")
        result = claim_free_test(user_id, u["is_agent"], today_str)
        if result["ok"]:
            await update.message.reply_html(f"🔑 <b>پروفایل اتصال آزمایشی صادر شد</b>\n\n<code>{result['content']}</code>")
        else:
            reason = result["reason"]
            if reason == "already_used":
                msg = "⚠️ شما قبلاً سهمیه تست رایگان خود را دریافت کرده‌اید"
            elif reason == "daily_limit":
                msg = "👑 نماینده گرامی، شما سهمیه امروز خود (1 اکانت تست در روز) را دریافت کرده‌اید. فردا مجدداً تلاش کنید."
            else:
                msg = "📭 در حال حاضر اکانت تستی در مخزن موجود نیست"
            await update.message.reply_text(msg)
        return True
    if text == BTN_SERVICES:
        user_states[user_id] = None
        await show_services_menu(update.message, user_id)
        return True
    if text == BTN_WALLET:
        user_states[user_id] = None
        await show_wallet_menu(update.message, u)
        return True
    if text == BTN_TUTORIALS:
        user_states[user_id] = None
        await show_tutorials_menu(update.message)
        return True
    if text == BTN_REF:
        user_states[user_id] = None
        await show_referral_menu(update.message, context, user_id)
        return True
    if text == BTN_AGENCY:
        user_states[user_id] = None
        req_id = await show_agency_menu(update.message, user_id, u)
        if req_id:
            username = f"@{update.effective_user.username}" if update.effective_user.username else "فاقد شناسه"
            markup = get_receipt_management_keyboard(req_id, "agency_req")
            await safe_send(context.bot, OWNER_ID, f"🙋 درخواست نمایندگی\n\nآیدی: {user_id}\n\nیوزرنیم: {username}", reply_markup=markup)
        return True
    if text == BTN_SUPPORT:
        user_states[user_id] = "waiting_for_support_msg"
        await update.message.reply_html("☎️ <b>بخش ارتباط با پشتیبانی</b>\n\nلطفاً پیام خود را بنویسید تا در اسرع وقت پاسخگوی شما باشیم 🙏\n\n(برای انصراف /cancel را بزنید)")
        return True
    if text == BTN_ADMIN:
        if is_admin(user_id):
            user_states[user_id] = None
            await update.message.reply_text("🛠️ به میز کار مدیریت خوش آمدید:", reply_markup=get_admin_inline_keyboard())
        return True
    if text == BTN_DICE:
        user_states[user_id] = None
        await handle_dice_play(update, context, user_id)
        return True
    return False


async def handle_dice_play(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int):
    cooldown_hours = int(get_setting("dice_cooldown_hours", str(DEFAULT_DICE_COOLDOWN_HOURS)))
    reward = int(get_setting("dice_reward", str(DEFAULT_DICE_REWARD)))

    claim = claim_dice_turn(user_id, cooldown_hours)
    if not claim["ok"]:
        remaining = claim["remaining"]
        hours = int(remaining.total_seconds() // 3600)
        minutes = int((remaining.total_seconds() % 3600) // 60)
        await update.message.reply_text(f"⏳ نوبت بعدی شما تا {hours} ساعت و {minutes} دقیقه دیگر است.")
        return

    await update.message.reply_text("🎲 در حال پرتاب تاس توسط ربات...")
    # تاس توسط خود ربات ارسال می‌شود؛ عدد نتیجه را سرور تلگرام تعیین می‌کند، نه کاربر و نه کد ما — غیرقابل دستکاری
    dice_message = await context.bot.send_dice(update.effective_chat.id, emoji='🎲')
    value = dice_message.dice.value

    if value == 6:
        adjust_balance(user_id, reward, "جایزه گردونه شانس (تاس ۶)")
        await update.message.reply_html(f"🎉 <b>تبریک! عدد ۶ آوردید</b>\n\n💰 مبلغ {reward:,} تومان به کیف پول شما اضافه شد.")
    else:
        await update.message.reply_text(f"🙁 عدد {value} آمد. جایزه فقط برای عدد ۶ است — فردا دوباره امتحان کنید!")


async def handle_text_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if u["is_banned"] == 1:
        return

    text = update.message.text
    current_state = user_states.get(user_id)

    # اولویت با دکمه‌های کیبورد منویی؛ حتی اگر کاربر وسط یک فلو باشد، با زدن منو از آن خارج می‌شود
    if await dispatch_menu_label(update, context, text, user_id, u):
        return

    if current_state == "waiting_for_phone_verification":
        await update.message.reply_text(
            "لطفاً از دکمه‌ای که ارسال شد برای اشتراک‌گذاری شماره تلفن خود استفاده کنید 📱\n(یا /cancel برای انصراف)"
        )
        return

    if current_state == "p_cap_1" and is_admin(user_id):
        user_states[user_id] = None
        target = parse_user_id(text)
        if target is None:
            await update.message.reply_text("آیدی نامعتبر است.")
            return
        inf = get_user(target)
        with get_conn() as conn:
            srv_count = conn.execute("SELECT COUNT(*) FROM user_services WHERE user_id=?", (target,)).fetchone()[0]
        await update.message.reply_html(
            f"🔍 <b>وضعیت حساب کاربری</b>\n\nشناسه عددی: {target}\n\n💰 تراز مالی: {inf['balance']:,} تومان\n\n"
            f"👑 همکار/نماینده: {'بله' if inf['is_agent'] else 'خیر'}\n\n🚫 وضعیت مسدودیت: {'بله' if inf['is_banned'] else 'خیر'}\n\n"
            f"📱 احراز شماره: {'بله' if inf['phone_verified'] else 'خیر'}\n\n🛍️ تعداد سرویس‌ها: {srv_count}"
        )
        return

    elif current_state == "p_cap_2" and is_admin(user_id):
        user_states[user_id] = None
        parts = text.split()
        if len(parts) < 2:
            await update.message.reply_text("ساختار ورودی نادرست است. فرمت صحیح: آیدی مقدار")
            return
        target = parse_user_id(parts[0])
        amount = parse_positive_int(parts[1])
        if target is None or amount is None:
            await update.message.reply_text("ساختار ورودی نادرست است.")
            return
        adjust_balance(target, amount, "افزایش موجودی توسط ادمین")
        await update.message.reply_text("✅ تراز مالی با موفقیت ارتقا یافت")
        await safe_send(context.bot, target, f"💰 <b>اطلاعیه واریز وجه</b>\n\nمبلغ {amount:,} تومان به موجودی جاری حساب شما اضافه گردید", parse_mode='HTML')
        return

    elif current_state == "p_cap_3" and is_admin(user_id):
        user_states[user_id] = None
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("فرمت ورودی نامعتبر است. فرمت صحیح: آیدی مقدار")
            return
        target = parse_user_id(parts[0])
        amount = parse_positive_int(parts[1])
        if target is None or amount is None:
            await update.message.reply_text("فرمت ورودی نامعتبر است.")
            return
        adjust_balance(target, -amount, "کسر موجودی توسط ادمین")
        await update.message.reply_text("✅ کسر تراز با موفقیت اعمال شد")
        await safe_send(context.bot, target, f"⚠️ <b>اطلاعیه مالی</b>\n\nمبلغ {amount:,} تومان از حساب کاربری شما کسر گردید", parse_mode='HTML')
        return

    elif current_state == "p_cap_4" and is_admin(user_id):
        user_states[user_id] = None
        target = parse_user_id(text)
        if target is None:
            await update.message.reply_text("خطا: آیدی نامعتبر است")
            return
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_banned = 1 WHERE user_id = ?", (target,))
            conn.commit()
        await update.message.reply_text("🚫 کاربر مسدود شد.")
        return

    elif current_state == "p_cap_5" and is_admin(user_id):
        user_states[user_id] = None
        target = parse_user_id(text)
        if target is None:
            await update.message.reply_text("خطا: آیدی نامعتبر است")
            return
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_banned = 0 WHERE user_id = ?", (target,))
            conn.commit()
        await update.message.reply_text("🟢 رفع مسدودیت انجام شد.")
        return

    elif current_state == "p_cap_6" and is_admin(user_id):
        user_states[user_id] = None
        target = parse_user_id(text)
        if target is None:
            await update.message.reply_text("خطا: آیدی نامعتبر است")
            return
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_agent = 1 WHERE user_id = ?", (target,))
            conn.commit()
        await update.message.reply_text("👑 حق دسترسی همکاری اعطا شد.")
        await safe_send(context.bot, target, AGENCY_SUCCESS_TEXT, parse_mode='HTML')
        return

    elif current_state == "p_cap_7" and is_admin(user_id):
        user_states[user_id] = None
        target = parse_user_id(text)
        if target is None:
            await update.message.reply_text("خطا: آیدی نامعتبر است")
            return
        with get_conn() as conn:
            conn.execute("UPDATE users SET is_agent = 0 WHERE user_id = ?", (target,))
            conn.commit()
        await update.message.reply_text("👤 حق دسترسی لغو شد.")
        return

    elif current_state == "p_cap_8" and is_admin(user_id):
        user_states[user_id] = None
        amt = parse_positive_int(text)
        if amt is None:
            await update.message.reply_text("ساختار نادرست؛ فقط یک عدد صحیح مثبت وارد کنید.")
            return
        with get_conn() as conn:
            users = conn.execute("SELECT user_id FROM users WHERE is_banned = 0").fetchall()
        s = 0
        for u_row in users:
            adjust_balance(u_row[0], amt, "اعتبار هدیه همگانی")
            res = await safe_send(context.bot, u_row[0], f"🎁 <b>اعتبار هدیه عمومی</b>\n\nاعتبار هدیه‌ای به مبلغ {amt:,} تومان به حساب شما واریز شد", parse_mode='HTML')
            if res is not None:
                s += 1
        await update.message.reply_text(f"✅ واریز عمومی پایان یافت. ({s} پیام تحویل داده شد)")
        return

    elif current_state == "p_cap_9" and is_admin(user_id):
        user_states[user_id] = None
        target = parse_user_id(text)
        if target is None:
            await update.message.reply_text("خطا: آیدی نامعتبر است")
            return
        with get_conn() as conn:
            conn.execute("DELETE FROM user_services WHERE user_id = ?", (target,))
            conn.commit()
        await update.message.reply_text("❌ کلیه سرویس‌های فعال کاربر ابطال شدند.")
        return

    elif current_state == "p_cap_11" and is_admin(user_id):
        user_states[user_id] = None
        target = parse_user_id(text)
        if target is None:
            await update.message.reply_text("خطا: آیدی نامعتبر است")
            return
        with get_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (target,))
            conn.commit()
        await update.message.reply_text(f"✅ کاربر {target} به کادر ادمین‌ها ملحق شد.")
        return

    elif current_state == "p_cap_12" and is_admin(user_id):
        user_states[user_id] = None
        t_id = parse_user_id(text)
        if t_id is None:
            await update.message.reply_text("خطا: آیدی نامعتبر است")
            return
        if t_id == OWNER_ID:
            await update.message.reply_text("⛔️ لغو دسترسی مالک اصلی امکان‌پذیر نیست")
            return
        with get_conn() as conn:
            conn.execute("DELETE FROM admins WHERE user_id = ?", (t_id,))
            conn.commit()
        await update.message.reply_text("✅ عزل مدیر با موفقیت انجام شد.")
        return

    elif current_state == "p_cap_14" and is_admin(user_id):
        user_states[user_id] = None
        amt = parse_positive_int(text)
        if amt is None:
            await update.message.reply_text("خطا؛ فقط یک عدد صحیح مثبت وارد کنید.")
            return
        with get_conn() as conn:
            users = conn.execute("SELECT user_id FROM users").fetchall()
        for u_row in users:
            adjust_balance(u_row[0], -amt, "کسر همگانی توسط ادمین")
        await update.message.reply_text("✅ عملیات کسر همگانی پایان یافت.")
        return

    elif current_state == "p_cap_17" and is_admin(user_id):
        user_states[user_id] = None
        parts = text.split()
        if len(parts) != 2:
            await update.message.reply_text("خطا در فرمت. فرمت صحیح: آیدی‌کاربر آیدی‌معرف")
            return
        u_id, r_id = parse_user_id(parts[0]), parse_user_id(parts[1])
        if u_id is None or r_id is None:
            await update.message.reply_text("خطا در فرمت.")
            return
        with get_conn() as conn:
            conn.execute("UPDATE users SET referred_by = ? WHERE user_id = ?", (r_id, u_id))
            conn.commit()
        await update.message.reply_text("✅ وابستگی ارجاع ثبت شد.")
        return

    elif current_state == "waiting_for_tutorial_app" and is_admin(user_id):
        set_setting("tutorial_app_text", text.strip())
        user_states[user_id] = None
        await update.message.reply_text("✅ متن «برنامه مورد نیاز» به‌روزرسانی شد.")
        return

    elif current_state == "waiting_for_tutorial_import" and is_admin(user_id):
        set_setting("tutorial_import_text", text.strip())
        user_states[user_id] = None
        await update.message.reply_text("✅ متن «آموزش وارد کردن» به‌روزرسانی شد.")
        return

    elif isinstance(current_state, dict) and current_state.get("action") == "waiting_for_product_qr" and is_admin(user_id):
        if text.strip() in ("رد", "/skip", "skip"):
            user_states[user_id] = None
            await update.message.reply_text("رد شد؛ QR/راهنما تنظیم نشد.")
            return
        await update.message.reply_text("لطفاً یک تصویر ارسال کنید یا عبارت «رد» را بفرستید.")
        return

    elif current_state == "waiting_for_new_card" and is_admin(user_id):
        digits = to_en_digits(text).replace(" ", "").replace("-", "")
        if not (digits.isdigit() and len(digits) == 16):
            await update.message.reply_text("شماره کارت باید دقیقاً ۱۶ رقم باشد. مجدداً تلاش کنید:")
            return
        user_states[user_id] = {"action": "waiting_for_new_card_name", "card_num": digits}
        await update.message.reply_text("👤 اکنون نام صاحب حساب جدید را وارد نمایید:")
        return
    elif isinstance(current_state, dict) and current_state.get("action") == "waiting_for_new_card_name" and is_admin(user_id):
        set_setting("card_number", current_state["card_num"])
        set_setting("card_name", text.strip())
        user_states[user_id] = None
        await update.message.reply_text("✅ اطلاعات حساب بانکی با موفقیت به‌روزرسانی شد.")
        return

    elif current_state == "waiting_new_btn_name" and is_admin(user_id):
        name = text.strip()
        if not name:
            await update.message.reply_text("نام نمی‌تواند خالی باشد.")
            return
        user_states[user_id] = {"action": "waiting_new_btn_price", "name": name}
        await update.message.reply_text("💰 بهای محصول جدید را به تومان وارد نمایید:")
        return
    elif isinstance(current_state, dict) and current_state.get("action") == "waiting_new_btn_price" and is_admin(user_id):
        price = parse_positive_int(text)
        if price is None:
            await update.message.reply_text("❌ مقدار ورودی نامعتبر است.")
            return
        with get_conn() as conn:
            conn.execute("INSERT INTO products (name, price) VALUES (?, ?)", (current_state["name"], price))
            conn.commit()
        user_states[user_id] = None
        await update.message.reply_text("✅ محصول جدید با موفقیت اضافه شد.")
        return

    elif isinstance(current_state, dict) and current_state.get("action") == "waiting_for_configs_reply" and is_admin(user_id):
        p_id = current_state.get("product_id")
        user_states[user_id] = None
        lines = [ln.strip() for ln in text.split('\n') if ln.strip()]
        added = 0
        with get_conn() as conn:
            cfg_type = 'test' if p_id == 0 else 'unlimited'
            for line in lines:
                conn.execute("INSERT INTO configs (product_id, type, content) VALUES (?, ?, ?)", (p_id, cfg_type, line))
                added += 1
            conn.commit()
        await update.message.reply_text(f"✅ تعداد {added} اکانت با موفقیت به انبار افزوده شد.")
        return

    elif isinstance(current_state, dict) and current_state.get("action") == "waiting_for_reset_count" and is_admin(user_id):
        p_id = current_state.get("product_id")
        user_states[user_id] = None
        count = parse_positive_int(text)
        if count is None:
            await update.message.reply_text("عدد ورودی معتبر نیست")
            return
        with get_conn() as conn:
            rows = conn.execute("SELECT id FROM configs WHERE product_id = ? AND is_used = 0 LIMIT ?", (p_id, count)).fetchall()
            for r in rows:
                conn.execute("DELETE FROM configs WHERE id = ?", (r[0],))
            conn.commit()
            deleted = len(rows)
        await update.message.reply_text(f"🗑️ تعداد {deleted} کانفیگ از مخزن حذف شد.")
        return

    elif current_state == "waiting_for_charge_amount":
        amount = parse_positive_int(text)
        if amount is None:
            await update.message.reply_text("لطفاً فقط مبلغ را به عدد وارد کنید")
            return
        user_states[user_id] = {"action": "send_charge_receipt", "amount": amount}
        card_number = get_setting("card_number", DEFAULT_CARD_NUMBER)
        card_name = get_setting("card_name", DEFAULT_CARD_NAME)
        invoice_text = (
            f"💳 <b>بخش افزایش موجودی حساب</b>\n\n"
            f"لطفاً مبلغ واریزی را به مقدار دقیق {amount:,} تومان کارت به کارت نموده\n\n"
            f"و تصویر رسید فیش خود را در پاسخ به این پیام ارسال فرمایید 🧾\n\n"
            f"شماره کارت: <code>{card_number}</code>\n\n"
            f"بنام: {card_name}"
        )
        await update.message.reply_html(invoice_text)
        return

    elif current_state == "waiting_for_broadcast" and is_admin(user_id):
        user_states[user_id] = None
        with get_conn() as conn:
            users = conn.execute("SELECT user_id FROM users WHERE blocked_by_bot = 0").fetchall()
        s = 0
        for u_row in users:
            res = await safe_send(context.bot, u_row[0], f"📢 <b>اطلاعیه جدید مدیریت</b>\n\n{text}", parse_mode='HTML')
            if res is not None:
                s += 1
        await update.message.reply_text(f"✅ پیام همگانی با موفقیت به {s} کاربر ارسال شد.")
        return

    elif current_state == "waiting_for_support_msg":
        user_states[user_id] = None
        await context.bot.forward_message(OWNER_ID, update.message.chat_id, update.message.message_id)
        await update.message.reply_text("✅ پیام شما دریافت شد و به زودی پاسخگوی شما خواهیم بود.")
        return

    await update.message.reply_text("لطفاً از دکمه‌های پایین صفحه استفاده نمایید 👇", reply_markup=get_main_reply_keyboard(user_id))


async def handle_contact(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if u["is_banned"] == 1:
        return

    contact = update.message.contact
    if contact.user_id != user_id:
        await update.message.reply_text("⚠️ لطفاً فقط شماره تلفن متعلق به خودتان را ارسال کنید.")
        return

    normalized = normalize_ir_phone(contact.phone_number)
    if not normalized:
        await update.message.reply_text(
            "❌ فقط شماره‌های ایران (+98) پذیرفته می‌شود. لطفاً با یک شماره ایرانی مجدداً تلاش کنید یا /cancel بزنید.",
        )
        return

    with get_conn() as conn:
        conn.execute("UPDATE users SET phone_number = ?, phone_verified = 1 WHERE user_id = ?", (normalized, user_id))
        conn.commit()

    await update.message.reply_text("✅ شماره شما با موفقیت و به‌صورت خودکار تایید شد.", reply_markup=get_main_reply_keyboard(user_id))

    if user_states.get(user_id) == "waiting_for_phone_verification":
        user_states[user_id] = "waiting_for_charge_amount"
        await update.message.reply_html("💳 <b>بخش افزایش موجودی حساب</b>\n\nلطفاً مبلغ مورد نظر خود را به تومان و به عدد وارد نمایید:")


async def handle_photos(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    u = get_user(user_id)
    if u["is_banned"] == 1:
        return
    state = user_states.get(user_id)
    if not state:
        await update.message.reply_text("در حال حاضر منتظر دریافت تصویر از شما نبودیم.")
        return

    if isinstance(state, dict) and state.get("action") == "send_charge_receipt":
        amount = state.get("amount", 0)
        req_id = create_pending_request("charge", user_id, amount=amount)
        await update.message.reply_text("🧾 تصویر فیش دریافت شد و در صف بررسی قرار گرفت.")
        markup = get_receipt_management_keyboard(req_id, "charge")
        await context.bot.send_photo(OWNER_ID, update.message.photo[-1].file_id, caption=f"💳 درخواست تایید واریزی\n\nکاربر: {user_id}\n\nمبلغ: {amount:,} تومان", reply_markup=markup)
        user_states[user_id] = None

    elif isinstance(state, dict) and state.get("action") == "direct_buy_receipt":
        prod_id = state.get("product_id")
        req_id = create_pending_request("buy", user_id, product_id=prod_id)
        await update.message.reply_text("🧾 تصویر فیش خرید دریافت شد و پس از تایید سرویس صادر می‌شود.")
        markup = get_receipt_management_keyboard(req_id, "buy")
        await context.bot.send_photo(OWNER_ID, update.message.photo[-1].file_id, caption=f"🛒 فیش خرید مستقیم\n\nکاربر: {user_id}\n\nکد محصول: {prod_id}", reply_markup=markup)
        user_states[user_id] = None

    elif isinstance(state, dict) and state.get("action") == "waiting_for_product_qr" and is_admin(user_id):
        p_id = state.get("product_id")
        file_id = update.message.photo[-1].file_id
        with get_conn() as conn:
            conn.execute("UPDATE products SET qr_file_id = ? WHERE id = ?", (file_id, p_id))
            conn.commit()
        user_states[user_id] = None
        await update.message.reply_text("✅ تصویر QR/راهنما برای این محصول ثبت شد.")

    else:
        await update.message.reply_text("در این مرحله نیازی به ارسال تصویر نیست.")


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("خطای پیش‌بینی‌نشده در پردازش آپدیت", exc_info=context.error)


# ----------------- اجرای اصلی برنامه -----------------
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cancel", cancel_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("diag", diag_cmd))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_messages))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photos))
    app.add_error_handler(error_handler)

    logger.info("✅ ربات آماده به کار است.")
    app.run_polling()


if __name__ == "__main__":
    main()
