import os
import requests
from datetime import datetime, date
import pytz

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
NOTION_TOKEN = os.environ["NOTION_TOKEN"]
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

CALENDAR_DB_ID = "351a02e814ac80c9a25f000b77816a4c"
SCHEDULE_DB_ID = "351a02e814ac809c9b93000b20d18992"

CONTRACTORS = {
    "Технический директор": "156140953",
    "Пострановшики":        None,
    "А-про":                None,
    "Мидека":               None,
    "Все для шшоу":         None,
    "Яндекс":               None,
}

NOTION_HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
}

def get_calendar_entry(target_date):
    iso = target_date.isoformat()
    r = requests.post(
        f"https://api.notion.com/v1/databases/{CALENDAR_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={"filter": {"property": "Date", "date": {"equals": iso}}}
    )
    results = r.json().get("results", [])
    return results[0] if results else None

def get_schedule(calendar_page_id, contractor):
    r = requests.post(
        f"https://api.notion.com/v1/databases/{SCHEDULE_DB_ID}/query",
        headers=NOTION_HEADERS,
        json={"filter": {"and": [
            {"property": "подрядчики", "select": {"equals": contractor}},
            {"property": "Данные календаря", "relation": {"contains": calendar_page_id}}
        ]}}
    )
    return r.json().get("results", [])

def format_tasks(tasks):
    if not tasks:
        return "  — задач нет"
    lines = []
    for t in tasks:
        props = t["properties"]
        title = props.get("Наименование", {}).get("title", [{}])[0].get("plain_text", "—")
        start_d = props.get("время начало", {}).get("date") or {}
        end_d   = props.get("Время конец", {}).get("date") or {}
        start = start_d.get("start", "")[-8:-3] if start_d.get("start") else ""
        end   = end_d.get("start", "")[-8:-3]   if end_d.get("start")   else ""
        prio  = (props.get("Приоритет", {}).get("select") or {}).get("name", "")
        icon  = "⚠️" if prio.lower() in ["важно", "критично"] else "•"
        time_str = f"{start}–{end} " if start else ""
        lines.append(f"  {icon} {time_str}{title}")
    return "\n".join(lines)

def send_telegram(chat_id, text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    )

def main():
    now = datetime.now(MOSCOW_TZ)
    today = now.date()
    tomorrow = date.fromordinal(today.toordinal() + 1)

    today_entry = get_calendar_entry(today)
    tomorrow_entry = get_calendar_entry(tomorrow)

    for contractor, chat_id in CONTRACTORS.items():
        if not chat_id:
            continue

        # Сегодня
        if today_entry:
            pid = today_entry["id"]
            day_type = (today_entry["properties"].get("Select", {}).get("select") or {}).get("name", "")
            tasks = get_schedule(pid, contractor)
            today_block = f"📅 *Сегодня, {today.strftime('%d.%m')}* — {day_type}\n\n📋 *Задачи:*\n{format_tasks(tasks)}"
        else:
            today_block = f"📅 *Сегодня, {today.strftime('%d.%m')}* — данных нет"

        # Завтра
        if tomorrow_entry:
            pid2 = tomorrow_entry["id"]
            day_type2 = (tomorrow_entry["properties"].get("Select", {}).get("select") or {}).get("name", "")
            tasks2 = get_schedule(pid2, contractor)
            tomorrow_block = f"📅 *Завтра, {tomorrow.strftime('%d.%m')}* — {day_type2}\n\n📋 *План:*\n{format_tasks(tasks2)}"
        else:
            tomorrow_block = f"📅 *Завтра, {tomorrow.strftime('%d.%m')}* — данных нет"

        msg = f"🏗 *Титаны — утренняя сводка*\n{'─'*28}\n\n{today_block}\n\n{'─'*28}\n\n{tomorrow_block}"
        send_telegram(chat_id, msg)
        print(f"✅ Отправлено: {contractor}")

if __name__ == "__main__":
    main()
