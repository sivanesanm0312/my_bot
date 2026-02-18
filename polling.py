from app import ptb_app, app
from telegram import Update
from telegram.ext import Application
import asyncio

if __name__ == '__main__':
    print("Starting bot in polling mode...")
    
    # Initialize DB (safety check)
    try:
        with app.app_context():
            from models import db
            db.create_all()
    except Exception as e:
        print(f"DB Init Warning: {e}")

    # Start Polling
    if ptb_app:
        ptb_app.run_polling()
    else:
        print("Bot failed to initialize (check TOKEN).")
