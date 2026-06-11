import asyncio
import logging
import os
import sys
from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from telegram.error import Conflict, NetworkError
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from config import BOT_TOKEN, ADMIN_IDS
from handlers.user import cmd_start, cmd_status, cmd_history, handle_menu_button
from handlers.admin import (
    cmd_report, cmd_users, cmd_pending,
    cmd_adduser, cmd_remindall, cmd_bots,
    newbill_handler,
)
from handlers.callbacks import handle_callback, handle_bot_callback
import scheduler

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

PID_FILE = "bot.pid"

USER_COMMANDS = [
    BotCommand("start",   "🚀 Регистрация / главное меню"),
    BotCommand("status",  "💳 Мои счета к оплате"),
    BotCommand("history", "📜 История платежей"),
]

ADMIN_COMMANDS = USER_COMMANDS + [
    BotCommand("newbill",   "➕ Новый счёт пользователю"),
    BotCommand("report",    "📊 Бюджетный отчёт"),
    BotCommand("pending",   "⏳ Неоплаченные счета"),
    BotCommand("users",     "👥 Список пользователей"),
    BotCommand("remindall", "📨 Напомнить всем должникам"),
    BotCommand("adduser",   "👤 Добавить пользователя вручную"),
    BotCommand("bots",      "🤖 Управление ботами"),
]


def check_pid_file():
    """Prevent multiple instances."""
    if os.path.exists(PID_FILE):
        try:
            old_pid = int(open(PID_FILE).read().strip())
            os.kill(old_pid, 0)  # check if process alive
            log.error("Бот уже запущен (PID %d). Останови его перед запуском нового.", old_pid)
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass  # old PID dead, overwrite
    with open(PID_FILE, "w") as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    try:
        os.remove(PID_FILE)
    except FileNotFoundError:
        pass


async def error_handler(update, context):
    err = context.error
    if isinstance(err, Conflict):
        log.critical(
            "⚠️  КОНФЛИКТ ТОКЕНА: другое приложение использует тот же токен бота! "
            "Найди и останови его. Бот продолжает работу."
        )
        return
    if isinstance(err, NetworkError):
        log.warning("Сетевая ошибка (временно): %s", err)
        return
    log.error("Необработанная ошибка: %s", err, exc_info=context.error)


async def post_init(app: Application):
    await app.bot.set_my_commands(USER_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    for admin_id in ADMIN_IDS:
        try:
            await app.bot.set_my_commands(
                ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id)
            )
        except Exception as e:
            log.warning("set commands for admin %s: %s", admin_id, e)
    log.info("Commands set for %d admins", len(ADMIN_IDS))


def main():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN не задан в .env")
    if not ADMIN_IDS:
        log.warning("ADMIN_IDS не заданы!")

    check_pid_file()

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

    # Error handler
    app.add_error_handler(error_handler)

    # /newbill wizard (must be before generic handlers)
    app.add_handler(newbill_handler())

    # Commands
    app.add_handler(CommandHandler("start",     cmd_start))
    app.add_handler(CommandHandler("status",    cmd_status))
    app.add_handler(CommandHandler("history",   cmd_history))
    app.add_handler(CommandHandler("report",    cmd_report))
    app.add_handler(CommandHandler("users",     cmd_users))
    app.add_handler(CommandHandler("pending",   cmd_pending))
    app.add_handler(CommandHandler("adduser",   cmd_adduser))
    app.add_handler(CommandHandler("remindall", cmd_remindall))
    app.add_handler(CommandHandler("bots", cmd_bots))

    # Inline button callbacks (u_*, b_*)
    app.add_handler(CallbackQueryHandler(handle_callback, pattern="^(u_|b_)"))

    # Bots management callbacks (bm_*, ubn_*)
    app.add_handler(CallbackQueryHandler(handle_bot_callback, pattern="^(bm_|ubn_)"))

    # Reply keyboard text buttons & custom amount input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_button))

    scheduler.setup(app)

    log.info("Бот запущен. Администраторы: %s", ADMIN_IDS)
    try:
        app.run_polling(drop_pending_updates=True)
    finally:
        remove_pid_file()


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
