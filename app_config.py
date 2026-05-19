from pathlib import Path


APP_VERSION = "v25.5.3"
APP_ICON = "assets/app.ico"
DEFAULT_LANGUAGE = "en"
DEFAULT_ACCOUNT = "Cash"
CURRENT_BACKUP_KEEP = 7

CURRENCY_OPTIONS = {
    "USD": "$",
    "CNY": "\u00a5",
    "EUR": "\u20ac",
    "GBP": "\u00a3",
    "JPY": "\u00a5",
}

THEME_OPTIONS = ("Light", "Dark")


def app_root():
    return Path(__file__).resolve().parent
