# Титаны — Telegram Bot

## Деплой на Railway

### 1. GitHub
1. Создай аккаунт на github.com
2. Нажми + → New repository → название: `titany-bot` → Create
3. Загрузи три файла: `bot.py`, `requirements.txt`, `Procfile`

### 2. Railway
1. Зайди на railway.app → Login with GitHub
2. New Project → Deploy from GitHub repo → выбери `titany-bot`
3. После деплоя зайди в Variables и добавь:

| Переменная | Значение |
|------------|----------|
| TELEGRAM_TOKEN | твой токен от BotFather |
| NOTION_TOKEN | твой Notion integration token |

4. Нажми Deploy — бот запустится

### 3. Регистрация подрядчиков
Каждый подрядчик должен написать боту /start — это нужно сделать один раз чтобы бот запомнил их chat_id.

Отправь им ссылку: t.me/titany_montazh_bot

### Команды бота
- /start — регистрация
- /today — сводка на сегодня
- /report — отчёт о выполнении
- /question — вопрос или проблема

### Добавить Цех позже
В файле bot.py найди строку CONTRACTORS и добавь:
`"Цех": "@username_цеха",`
