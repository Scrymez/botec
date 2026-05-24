import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
CURRENCY = os.getenv("CURRENCY", "RUB")
DB_PATH = os.getenv("DB_PATH", "data/db.json")

CURRENCY_SYMBOL = {
    "RUB": "₽",
    "USD": "$",
    "EUR": "€",
    "KZT": "₸",
    "UZS": "сум",
}.get(CURRENCY, CURRENCY)
