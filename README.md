# Expense Bot Backend (Flask + Telegram)

This project is a Telegram bot backend written in Python using Flask and `python-telegram-bot` (v20+).
It allows users to manage their expenses via Telegram commands.

## Features

- `/start`: Welcome message.
- `/add <amount> <category> <description>`: Add a new expense.
- `/list`: List the last 10 expenses.
- `/total`: Show the total expenses.
- `/delete <id>`: Delete an expense by ID.

## Setup

1.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

2.  **Environment Variables**:
    - Rename `.env.example` to `.env`.
    - Open `.env` and paste your Telegram Bot Token.
    - If testing locally with webhooks, use `ngrok` to get a public URL and set `WEBHOOK_URL`.

## Running the Bot

### Option 1: Polling (Easiest for Local Development)
This runs the bot directly without a webhook server. Ideal for testing logic.

```bash
python polling.py
```

### Option 2: Webhook (Production / Flask Server)
This runs the Flask server which listens for updates from Telegram.
Note: You need a public HTTPS URL (using something like `ngrok` locally).

```bash
python app.py
```

- To set the webhook URL for the bot, you can visit: `http://localhost:5000/set_webhook` (after configuring `WEBHOOK_URL`).

## Database
The app uses SQLite (`expenses.db`) by default.
The database is automatically created on first run.

## API Endpoints
- `POST /webhook`: Webhook endpoint for Telegram updates.
- `GET /`: Health check.
