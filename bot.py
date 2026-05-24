import asyncio
import logging
from telegram import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeChat
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, filters,
)

from config import BOT_TOKEN, ADMIN_IDS
from handlers.user import cmd_start, cmd_status, cmd_history, handle_menu_button
from handlers.admin import (
    cmd_report, cmd_users, cmd_pending,
    cmd_adduser, cmd_remindall,
    newbill_handler,
)
from handlers.callbacks import handle_callback
import scheduler

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger(__name__)

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
]


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

    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()

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

    # Inline button callbacks (u_*, b_*)
    app.add_handler(CallbackQueryHandler(handle_callback, pattern="^(u_|b_)"))

    # Reply keyboard text buttons
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_menu_button))

    scheduler.setup(app)

    log.info("Бот запущен. Администраторы: %s", ADMIN_IDS)
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    asyncio.set_event_loop(asyncio.new_event_loop())
    main()
