import os
import asyncio
import logging
from datetime import datetime, date
import pytz

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)
from notion_client import Client

# ─── НАСТРОЙКИ ───────────────────────────────────────────────────────────────

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
NOTION_TOKEN   = os.environ.get("NOTION_TOKEN")

# Базы данных Notion
CALENDAR_DB_ID  = "351a02e814ac80c9a25f000b77816a4c"
SCHEDULE_DB_ID  = "351a02e814ac809c9b93000b20d18992"
MATERIALS_DB_ID = "351a02e814ac80c7bec4000b283546cb"
FEEDBACK_DB_ID  = "351a02e814ac80babe40000b81e81ce4"

MOSCOW_TZ = pytz.timezone("Europe/Moscow")

# Подрядчики: Notion-название → Telegram username
CONTRACTORS = {
    "Постановщики": "@Shapi444",
    "Мидека":       "@revzis",
    "А-Про":        "@GusevSVW",
    "Все для шоу":  "@Slavik07077",
    "Технический диретор": "@vbotiy",
    # Цех — добавить позже
}

# username → chat_id (заполняется автоматически когда пользователь пишет /start)
USER_CHAT_IDS: dict[str, int] = {}

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

notion = Client(auth=NOTION_TOKEN)

# ─── NOTION: получить данные на дату ─────────────────────────────────────────

def get_calendar_entry(target_date: date):
    """Возвращает запись календаря на указанную дату."""
    iso = target_date.isoformat()
    results = notion.databases.query(
        database_id=CALENDAR_DB_ID,
        filter={
            "property": "Дата",
            "date": {"equals": iso}
        }
    ).get("results", [])
    return results[0] if results else None


def get_schedule(calendar_page_id: str, contractor: str):
    """Возвращает задачи подрядчика, привязанные к странице календаря."""
    results = notion.databases.query(
        database_id=SCHEDULE_DB_ID,
        filter={
            "and": [
                {
                    "property": "Подрядчик",
                    "select": {"equals": contractor}
                },
                {
                    "property": "День",
                    "relation": {"contains": calendar_page_id}
                }
            ]
        }
    ).get("results", [])
    return results


def get_materials(calendar_page_id: str):
    """Возвращает материалы, привязанные к странице календаря."""
    results = notion.databases.query(
        database_id=MATERIALS_DB_ID,
        filter={
            "property": "День",
            "relation": {"contains": calendar_page_id}
        }
    ).get("results", [])
    return results


def format_schedule(tasks: list) -> str:
    if not tasks:
        return "  — задач нет"
    lines = []
    for t in tasks:
        props = t["properties"]
        title = props.get("Название", {}).get("title", [{}])[0].get("plain_text", "—")
        start = props.get("Начало", {}).get("rich_text", [{}])[0].get("plain_text", "")
        end   = props.get("Конец",  {}).get("rich_text", [{}])[0].get("plain_text", "")
        prio  = props.get("Приоритет", {}).get("select", {})
        prio_name = prio.get("name", "") if prio else ""
        prio_icon = "⚠️" if prio_name == "важно" else "•"
        time_str = f"{start}–{end} " if start else ""
        lines.append(f"  {prio_icon} {time_str}{title}")
    return "\n".join(lines)


def format_materials(materials: list) -> str:
    if not materials:
        return "  — материалов нет"
    lines = []
    for m in materials:
        props = m["properties"]
        name = props.get("Название", {}).get("title", [{}])[0].get("plain_text", "—")
        url  = m.get("url", "")
        lines.append(f"  📎 [{name}]({url})")
    return "\n".join(lines)


def build_morning_message(contractor: str, today: date, tomorrow: date) -> str:
    today_entry    = get_calendar_entry(today)
    tomorrow_entry = get_calendar_entry(tomorrow)

    # Сегодня
    if today_entry:
        pid_today   = today_entry["id"]
        day_type    = today_entry["properties"].get("Тип дня", {}).get("select", {})
        day_type_name = day_type.get("name", "") if day_type else ""
        tasks_today = get_schedule(pid_today, contractor)
        mats_today  = get_materials(pid_today)
        today_block = (
            f"📅 *Сегодня, {today.strftime('%d.%m')}* — {day_type_name}\n\n"
            f"📋 *Твои задачи:*\n{format_schedule(tasks_today)}\n\n"
            f"📎 *Материалы:*\n{format_materials(mats_today)}"
        )
    else:
        today_block = f"📅 *Сегодня, {today.strftime('%d.%m')}* — данных нет"

    # Завтра
    if tomorrow_entry:
        pid_tomorrow   = tomorrow_entry["id"]
        day_type2      = tomorrow_entry["properties"].get("Тип дня", {}).get("select", {})
        day_type_name2 = day_type2.get("name", "") if day_type2 else ""
        tasks_tomorrow = get_schedule(pid_tomorrow, contractor)
        tomorrow_block = (
            f"📅 *Завтра, {tomorrow.strftime('%d.%m')}* — {day_type_name2}\n\n"
            f"📋 *План работ:*\n{format_schedule(tasks_tomorrow)}"
        )
    else:
        tomorrow_block = f"📅 *Завтра, {tomorrow.strftime('%d.%m')}* — данных нет"

    msg = (
        f"🏗 *Титаны — утренняя сводка*\n"
        f"{'─' * 28}\n\n"
        f"{today_block}\n\n"
        f"{'─' * 28}\n\n"
        f"{tomorrow_block}\n\n"
        f"{'─' * 28}\n"
        f"Используй кнопки ниже для обратной связи 👇"
    )
    return msg


# ─── ОБРАТНАЯ СВЯЗЬ: сохранить в Notion ──────────────────────────────────────

def save_feedback(contractor: str, feedback_type: str, text: str, today: date):
    today_entry = get_calendar_entry(today)
    relations = []
    if today_entry:
        relations = [{"id": today_entry["id"]}]

    notion.pages.create(
        parent={"database_id": FEEDBACK_DB_ID},
        properties={
            "тема":           {"title": [{"text": {"content": text[:100]}}]},
            "подрядчик":      {"select": {"name": contractor}},
            "Тип":            {"select": {"name": feedback_type}},
            "Статус":         {"select": {"name": "принято"}},
            "Date получения": {"date":   {"start": today.isoformat()}},
            "Данные календаря": {"relation": relations},
            "Text":           {"rich_text": [{"text": {"content": text}}]},
        }
    )


# ─── HANDLERS ────────────────────────────────────────────────────────────────

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.effective_user.username
    chat_id  = update.effective_chat.id
    if username:
        USER_CHAT_IDS[f"@{username}"] = chat_id
        logger.info(f"Registered @{username} → {chat_id}")

    await update.message.reply_text(
        "👋 Привет! Я бот проекта *Титаны*.\n\n"
        "Каждое утро в 08:00 ты будешь получать сводку по своим задачам.\n\n"
        "Команды:\n"
        "/today — сводка на сегодня\n"
        "/report — отчёт о выполнении\n"
        "/question — задать вопрос",
        parse_mode="Markdown"
    )


async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = f"@{update.effective_user.username}"
    contractor = next((k for k, v in CONTRACTORS.items() if v == username), None)
    if not contractor:
        await update.message.reply_text("❌ Ты не зарегистрирован в проекте.")
        return

    now      = datetime.now(MOSCOW_TZ)
    today    = now.date()
    tomorrow = date.fromordinal(today.toordinal() + 1)

    msg = build_morning_message(contractor, today, tomorrow)
    keyboard = [
        [
            InlineKeyboardButton("✅ Отчёт о выполнении", callback_data="feedback_report"),
            InlineKeyboardButton("❓ Вопрос/Проблема",    callback_data="feedback_question"),
        ]
    ]
    await update.message.reply_text(
        msg,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


async def report_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback_type"] = "отчет о выполнении"
    await update.message.reply_text(
        "📝 Напиши отчёт о выполнении — я передам его в Notion:"
    )


async def question_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["feedback_type"] = "комментарий"
    await update.message.reply_text(
        "❓ Напиши свой вопрос или опиши проблему — я передам в Notion:"
    )


async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "feedback_report":
        context.user_data["feedback_type"] = "отчет о выполнении"
        await query.message.reply_text("📝 Напиши отчёт о выполнении:")
    elif query.data == "feedback_question":
        context.user_data["feedback_type"] = "комментарий"
        await query.message.reply_text("❓ Напиши вопрос или проблему:")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    feedback_type = context.user_data.get("feedback_type")
    if not feedback_type:
        await update.message.reply_text(
            "Используй команды:\n/today — сводка\n/report — отчёт\n/question — вопрос"
        )
        return

    username   = f"@{update.effective_user.username}"
    contractor = next((k for k, v in CONTRACTORS.items() if v == username), "Неизвестно")
    text       = update.message.text
    today      = datetime.now(MOSCOW_TZ).date()

    save_feedback(contractor, feedback_type, text, today)
    context.user_data.pop("feedback_type")

    await update.message.reply_text(
        "✅ Принято! Сообщение сохранено в Notion.",
    )


# ─── УТРЕННЯЯ РАССЫЛКА ───────────────────────────────────────────────────────

async def morning_broadcast(context: ContextTypes.DEFAULT_TYPE):
    now      = datetime.now(MOSCOW_TZ)
    today    = now.date()
    tomorrow = date.fromordinal(today.toordinal() + 1)

    for contractor, username in CONTRACTORS.items():
        chat_id = USER_CHAT_IDS.get(username)
        if not chat_id:
            logger.warning(f"Нет chat_id для {username}, пропускаю")
            continue
        try:
            msg = build_morning_message(contractor, today, tomorrow)
            keyboard = [[
                InlineKeyboardButton("✅ Отчёт", callback_data="feedback_report"),
                InlineKeyboardButton("❓ Вопрос", callback_data="feedback_question"),
            ]]
            await context.bot.send_message(
                chat_id=chat_id,
                text=msg,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
            logger.info(f"Отправлено {username}")
        except Exception as e:
            logger.error(f"Ошибка отправки {username}: {e}")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start",    start))
    app.add_handler(CommandHandler("today",    today_command))
    app.add_handler(CommandHandler("report",   report_command))
    app.add_handler(CommandHandler("question", question_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    # Утренняя рассылка в 08:00 МСК
    job_queue = app.job_queue
    job_queue.run_daily(
        morning_broadcast,
        time=datetime.strptime("08:00", "%H:%M").replace(tzinfo=MOSCOW_TZ).timetz(),
        name="morning_broadcast"
    )

    logger.info("Бот запущен")
    app.run_polling()


if __name__ == "__main__":
    main()
