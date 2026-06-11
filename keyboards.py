from telegram import ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
import db
import reports

# ── Reply keyboards ────────────────────────────────────────────────────────────

ADMIN_MENU = ReplyKeyboardMarkup(
    [
        ["📊 Отчёт по бюджету", "⏳ Неоплаченные счета"],
        ["👥 Пользователи",     "➕ Новый счёт"],
        ["📨 Напомнить всем",   "🤖 Боты"],
        ["💳 Мой статус"],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие...",
)

USER_MENU = ReplyKeyboardMarkup(
    [["💳 Мой статус", "📜 История платежей"]],
    resize_keyboard=True,
    input_field_placeholder="Выбери действие...",
)

# ── Predefined services ────────────────────────────────────────────────────────

SERVICES = [
    ("🖥 VPS Сервер",      "VPS Сервер"),
    ("🌐 Хостинг",         "Хостинг"),
    ("🔗 Домен",           "Домен"),
    ("🤖 Telegram Bot",    "Telegram Bot"),
    ("💻 Доп. сервер",     "Доп. сервер"),
    ("☁️ Облако",          "Облако"),
    ("✏️ Своё название",   "__custom__"),
]

def service_keyboard() -> InlineKeyboardMarkup:
    rows = []
    pair = []
    for label, val in SERVICES:
        pair.append(InlineKeyboardButton(label, callback_data=f"nb_svc:{val}"))
        if len(pair) == 2:
            rows.append(pair)
            pair = []
    if pair:
        rows.append(pair)
    rows.append([InlineKeyboardButton("❌ Отмена", callback_data="nb_cancel")])
    return InlineKeyboardMarkup(rows)

# ── User list with action buttons ─────────────────────────────────────────────

def user_list_keyboard(uid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➕ Счёт",       callback_data=f"nb_pre:{uid}"),
            InlineKeyboardButton("📋 Счета",      callback_data=f"u_bills:{uid}"),
        ],
        [
            InlineKeyboardButton("📨 Напомнить",  callback_data=f"u_remind:{uid}"),
            InlineKeyboardButton("🗑 Удалить",    callback_data=f"u_del_ask:{uid}"),
        ],
        [
            InlineKeyboardButton("🤖 Привязать бота", callback_data=f"ubn_pick:{uid}"),
        ],
    ])

def user_delete_confirm(uid: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Да, удалить", callback_data=f"u_del_yes:{uid}"),
        InlineKeyboardButton("❌ Отмена",      callback_data=f"u_del_no:{uid}"),
    ]])

# ── Bill action buttons ────────────────────────────────────────────────────────

def bill_keyboard(uid: str, bill_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Оплачено",      callback_data=f"b_paid_ask:{uid}:{bill_id}"),
            InlineKeyboardButton("📨 Напомнить",     callback_data=f"b_remind:{uid}:{bill_id}"),
        ],
        [
            InlineKeyboardButton("🗑 Удалить счёт",  callback_data=f"b_del_ask:{uid}:{bill_id}"),
        ],
    ])

def bill_paid_keyboard(uid: str, bill_id: str, amount: float) -> InlineKeyboardMarkup:
    amt_label = reports._fmt(amount)
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"✅ Да, {amt_label}",  callback_data=f"b_paid_yes:{uid}:{bill_id}"),
            InlineKeyboardButton("✏️ Другая сумма",      callback_data=f"b_paid_custom:{uid}:{bill_id}"),
        ],
        [InlineKeyboardButton("❌ Отмена", callback_data=f"b_paid_no:{uid}:{bill_id}")],
    ])

def bill_delete_confirm(uid: str, bill_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ Удалить", callback_data=f"b_del_yes:{uid}:{bill_id}"),
        InlineKeyboardButton("❌ Отмена",  callback_data=f"b_del_no:{uid}:{bill_id}"),
    ]])

# ── Due date selection ─────────────────────────────────────────────────────────

def due_date_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("7 дней",  callback_data="nb_date:7"),
            InlineKeyboardButton("14 дней", callback_data="nb_date:14"),
            InlineKeyboardButton("30 дней", callback_data="nb_date:30"),
        ],
        [InlineKeyboardButton("📅 Ввести дату вручную", callback_data="nb_date:manual")],
        [InlineKeyboardButton("❌ Отмена", callback_data="nb_cancel")],
    ])

# ── Bots management ────────────────────────────────────────────────────────────

def bots_keyboard() -> InlineKeyboardMarkup:
    bots = db.get_all_bots()
    rows = []
    for username in bots:
        rows.append([InlineKeyboardButton(f"🗑 @{username}", callback_data=f"bm_del:{username}")])
    rows.append([InlineKeyboardButton("➕ Добавить бота", callback_data="bm_add")])
    return InlineKeyboardMarkup(rows)


def user_bot_select_keyboard(uid: str) -> InlineKeyboardMarkup:
    bots = db.get_all_bots()
    rows = []
    for username in bots:
        rows.append([InlineKeyboardButton(f"@{username}", callback_data=f"ubn_set:{uid}:{username}")])
    if not bots:
        rows.append([InlineKeyboardButton("Нет ботов — добавь в «🤖 Боты»", callback_data="bm_list")])
    rows.append([InlineKeyboardButton("❌ Отвязать", callback_data=f"ubn_set:{uid}:__none__")])
    return InlineKeyboardMarkup(rows)
