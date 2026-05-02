import os
import requests
from datetime import datetime, date, timedelta
import pytz

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
SPREADSHEET_ID = "1X81SMkOIED0--ztW3dsHD4kD79I0dej-"
MOSCOW_TZ = pytz.timezone("Europe/Moscow")

# Подрядчики: имя в таблице → chat_id в Telegram
CONTRACTORS = {
    "Технический директор": "156140953",
    "Цех":                  None,
    "Постановщики":         None,
    "А-Про":                None,
    "Мидека":               None,
    "Все для шоу":          None,
    "Продюсер":             None,
    "Яндекс":               None,
}

# Серии материалов: диапазон дат → ссылки папок
SERIES = [
    {
        "name": "Серия 1",
        "start": date(2026, 5, 11),
        "end":   date(2026, 5, 13),
        "design":   "https://drive.google.com/drive/folders/1bsDKa0BloWcToj5GwcvwzGPt6IxQBSHB",
        "drawings": "https://drive.google.com/drive/folders/1GxKu9Du7VIbcuGcACgWMgUSLTJOw6RR9",
    },
    # Добавляй серии сюда:
    # {
    #     "name": "Серия 2",
    #     "start": date(2026, 5, 14),
    #     "end":   date(2026, 5, 16),
    #     "design":   "https://...",
    #     "drawings": "https://...",
    # },
]

def get_series(target_date):
    for s in SERIES:
        if s["start"] <= target_date <= s["end"]:
            return s
    return None

def fetch_sheet_csv():
    url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/export?format=csv"
    headers = {"Authorization": f"Bearer {os.environ.get('GDRIVE_TOKEN', '')}"}
    r = requests.get(url, headers=headers, timeout=30)
    return r.text

def parse_schedule(csv_text, target_date):
    """Возвращает dict: {подрядчик: [(час_начала, час_конца, задача), ...]}"""
    lines = csv_text.strip().split("\n")
    date_str = target_date.strftime("%d.%m")
    
    in_block = False
    header_row = []
    tasks = {}
    
    for line in lines:
        cells = [c.strip().strip('"') for c in line.split(",")]
        
        if cells[0].startswith(date_str):
            in_block = True
            continue
        
        if in_block:
            if not cells[0] and not any(cells[1:]):
                continue
            if cells[0] == "Подрядчик":
                header_row = cells
                continue
            if cells[0] and any(cells[1:]):
                contractor = cells[0]
                contractor_tasks = []
                for i, cell in enumerate(cells[1:], start=1):
                    if cell and i < len(header_row):
                        hour_label = header_row[i]
                        contractor_tasks.append((hour_label, cell))
                if contractor_tasks:
                    # Группируем подряд идущие одинаковые задачи
                    grouped = []
                    for hour, task in contractor_tasks:
                        if grouped and grouped[-1][2] == task:
                            grouped[-1] = (grouped[-1][0], hour, task)
                        else:
                            grouped.append((hour, hour, task))
                    tasks[contractor] = grouped
            # Если встретили следующую дату — выходим
            if cells[0] and "." in cells[0] and cells[0] != date_str and in_block and header_row:
                break
    
    return tasks

def format_tasks(tasks_dict, contractor):
    rows = tasks_dict.get(contractor, [])
    if not rows:
        return "  — задач нет"
    lines = []
    for start_h, end_h, task in rows:
        lines.append(f"  • {start_h}–{end_h} {task}")
    return "\n".join(lines)

def send_telegram(chat_id, text):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"},
        timeout=15
    )
    return r.ok

def main():
    now = datetime.now(MOSCOW_TZ)
    today = now.date()
    tomorrow = today + timedelta(days=1)

    print(f"Дата: {today}")
    csv_text = fetch_sheet_csv()

    tasks_today    = parse_schedule(csv_text, today)
    tasks_tomorrow = parse_schedule(csv_text, tomorrow)

    series_today    = get_series(today)
    series_tomorrow = get_series(tomorrow)

    for contractor, chat_id in CONTRACTORS.items():
        if not chat_id:
            print(f"Пропуск {contractor} — нет chat_id")
            continue

        # Блок сегодня
        today_tasks = format_tasks(tasks_today, contractor)
        today_block = (
            f"📅 *Сегодня, {today.strftime('%d.%m')}* — Монтаж\n\n"
            f"📋 *Задачи:*\n{today_tasks}"
        )
        if series_today:
            today_block += (
                f"\n\n📎 *Материалы ({series_today['name']}):*\n"
                f"  • [Дизайн]({series_today['design']})\n"
                f"  • [Чертежи]({series_today['drawings']})"
            )

        # Блок завтра
        tomorrow_tasks = format_tasks(tasks_tomorrow, contractor)
        tomorrow_block = (
            f"📅 *Завтра, {tomorrow.strftime('%d.%m')}* — Монтаж\n\n"
            f"📋 *План:*\n{tomorrow_tasks}"
        )
        if series_tomorrow:
            tomorrow_block += (
                f"\n\n📎 *Материалы ({series_tomorrow['name']}):*\n"
                f"  • [Дизайн]({series_tomorrow['design']})\n"
                f"  • [Чертежи]({series_tomorrow['drawings']})"
            )

        msg = (
            f"🏗 *Титаны — утренняя сводка*\n"
            f"{'━'*26}\n\n"
            f"{today_block}\n\n"
            f"{'━'*26}\n\n"
            f"{tomorrow_block}"
        )

        ok = send_telegram(chat_id, msg)
        print(f"{'✅' if ok else '❌'} {contractor} ({chat_id})")

if __name__ == "__main__":
    main()
