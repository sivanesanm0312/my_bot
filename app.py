import os
import re
from datetime import datetime, timedelta
from flask import Flask, request
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)
from telegram.constants import ParseMode
from models import db, Expense
from dotenv import load_dotenv
from sqlalchemy import func, extract
import calendar

load_dotenv()

TOKEN = os.getenv("BOT_TOKEN")
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///expenses.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()

# --- States ---
WAIT_CATEGORY = 1
WAIT_ANALYSIS_TYPE = 2

# --- Keyboards ---
MAIN_MENU = [
    ["➕ Quick Add", "📊 Analysis"],
    ["🧾 List Recent", "💰 Total Spent"],
    ["❓ Help"]
]
MARKUP_MAIN = ReplyKeyboardMarkup(MAIN_MENU, resize_keyboard=True)

CATEGORIES = [
    ["🍔 Food", "🚗 Transport", "🏠 Rent"],
    ["🛍️ Shopping", "💊 Health", "🎉 Fun"],
    ["💡 Utilities", "📚 Education", "🔙 Cancel"]
]
MARKUP_CATEGORY = ReplyKeyboardMarkup(CATEGORIES, one_time_keyboard=True, resize_keyboard=True, input_field_placeholder="Type custom category...")

# --- Analysis Helper ---
# --- Analysis Helper ---
def get_date_range(filter_type):
    now = datetime.utcnow()
    if filter_type == 'day':
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, "Today"
    elif filter_type == 'week':
        start = now - timedelta(days=now.weekday()) # Start of week (Monday)
        start = start.replace(hour=0, minute=0, second=0, microsecond=0)
        return start, now, "This Week"
    elif filter_type == 'month':
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return start, now, "This Month"
    return None, None, "All Time"

async def generate_report(user_id, filter_type):
    try:
        title = "Report"
        with app.app_context():
            query = db.session.query(Expense).filter_by(user_id=user_id)
            
            # 1. Apply Date Filter
            start_date, end_date, title = get_date_range(filter_type)
            if start_date:
                query = query.filter(Expense.date >= start_date)

            expenses = query.all()

            if not expenses:
                return f"📭 No data found for <b>{title}</b>."

            total = sum(e.amount for e in expenses)

            # 2. Group by Category
            cat_map = {}
            for e in expenses:
                cat_map[e.category] = cat_map.get(e.category, 0) + e.amount

            # Sort by highest spend
            sorted_cats = sorted(cat_map.items(), key=lambda x: x[1], reverse=True)

            # 3. Build CSV/Text Report
            report = f"📊 <b>Analysis: {title}</b>\n"
            report += f"💰 <b>Total Spent: {total:,.2f}</b>\n"
            report += "─" * 20 + "\n"
            
            for cat, amt in sorted_cats:
                percent = (amt / total * 100) if total > 0 else 0
                # Progress bar: [■■■□□□□□□□]
                blocks = int(percent / 10)
                bar = "■" * blocks + "□" * (10 - blocks)
                
                report += f"<b>{cat}</b>: {amt:,.2f} ({int(percent)}%)\n"
                report += f"<code>{bar}</code>\n"

            return report
    except Exception as e:
        return f"Error generating report: {e}"

async def analysis_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows analysis options."""
    keyboard = [
        [InlineKeyboardButton("📅 Today", callback_data='report_day'),
         InlineKeyboardButton("🗓️ This Week", callback_data='report_week')],
        [InlineKeyboardButton("📆 This Month", callback_data='report_month'),
         InlineKeyboardButton("📂 All Time", callback_data='report_all')],
        # Add a specific category drill-down button if needed later
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "📊 <b>Select Analysis Period:</b>\n"
        "Tap a button to see spend by category.",
        reply_markup=reply_markup,
        parse_mode=ParseMode.HTML
    )

async def report_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles report button clicks."""
    query = update.callback_query
    await query.answer()
    
    filter_type = query.data.replace('report_', '')
    report = await generate_report(update.effective_user.id, filter_type)
    
    # Edit the message with the report
    try:
        await query.edit_message_text(text=report, parse_mode=ParseMode.HTML, reply_markup=query.message.reply_markup)
    except Exception:
        pass # Ignore message not modified errors

# --- Smart Add Logic ---
async def smart_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    
    if text == "➕ Quick Add":
        await update.message.reply_text("Type amount (e.g. 50) or full expense (e.g. 50 Food).", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END

    if text == "📊 Analysis":
        await analysis_menu(update, context)
        return ConversationHandler.END

    if text == "🧾 List Recent":
        await handle_list(update, context)
        return ConversationHandler.END
        
    if text == "💰 Total Spent":
        await handle_total(update, context)
        return ConversationHandler.END

    # Regex for Number start
    match = re.match(r'^(\d+(\.\d+)?)(\s+(.+))?$', text)
    if match:
        amount = float(match.group(1))
        rest = match.group(4)
        
        if rest:
            # Full add
            parts = rest.split(' ', 1)
            cat = parts[0]
            desc = parts[1] if len(parts) > 1 else ""
            with app.app_context():
                exp = Expense(user_id=update.effective_user.id, amount=amount, category=cat, description=desc)
                db.session.add(exp)
                db.session.commit()
            await update.message.reply_text(f"✅ Saved: {amount} for {cat}", reply_markup=MARKUP_MAIN)
            return ConversationHandler.END
        else:
            context.user_data['amount'] = amount
            await update.message.reply_text(f"💰 Amount: {amount}\nSelect Category:", reply_markup=MARKUP_CATEGORY)
            return WAIT_CATEGORY
            
    return ConversationHandler.END


async def finish_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    if text == "🔙 Cancel":
        await update.message.reply_text("❌ Cancelled", reply_markup=MARKUP_MAIN)
        return ConversationHandler.END

    amount = context.user_data['amount']
    with app.app_context():
        exp = Expense(user_id=update.effective_user.id, amount=amount, category=text)
        db.session.add(exp)
        db.session.commit()
    
    await update.message.reply_text(f"✅ Saved: {amount} for {text}", reply_markup=MARKUP_MAIN)
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Cancelled", reply_markup=MARKUP_MAIN)
    return ConversationHandler.END

# --- Standard Handlers ---
async def handle_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with app.app_context():
        expenses = Expense.query.filter_by(user_id=user_id).order_by(Expense.date.desc()).limit(10).all()
        if not expenses:
            await update.message.reply_text("No recent expenses.")
            return
        
        msg = "<b>Recent Expenses:</b>\n"
        for e in expenses:
             msg += f"/del_{e.id} | {e.amount} | {e.category}\n"
        await update.message.reply_text(msg, parse_mode=ParseMode.HTML)

async def handle_total(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with app.app_context(): # Total All Time
        total = db.session.query(func.sum(Expense.amount)).filter_by(user_id=user_id).scalar() or 0
    await update.message.reply_text(f"💰 <b>Total All Time:</b> {total:,.2f}", parse_mode=ParseMode.HTML)

async def delete_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        eid = int(update.message.text.split('_')[1])
        with app.app_context():
            Expense.query.filter_by(id=eid, user_id=update.effective_user.id).delete()
            db.session.commit()
        await update.message.reply_text(f"Deleted #{eid}")
    except:
        await update.message.reply_text("Error deleting")

# --- Setup ---
if TOKEN:
    ptb_app = Application.builder().token(TOKEN).build()
    
    # Analyze Callback
    ptb_app.add_handler(CallbackQueryHandler(report_callback, pattern='^report_'))

    # Converstation / Smart Handler
    conv = ConversationHandler(
        entry_points=[
            MessageHandler(filters.Regex(r'^\d+'), smart_add_handler),
            MessageHandler(filters.TEXT & ~filters.COMMAND, smart_add_handler)
        ],
        states={
            WAIT_CATEGORY: [MessageHandler(filters.TEXT, finish_category)]
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )
    
    ptb_app.add_handler(CommandHandler('start', start))
    ptb_app.add_handler(MessageHandler(filters.Regex(r'^/del_'), delete_handler))
    ptb_app.add_handler(conv)
else:
    ptb_app = None

# --- Flask ---
@app.route('/')
def index(): return "Bot Running"

@app.route('/webhook', methods=['POST'])
async def webhook():
    if not ptb_app: return "Not Init", 500
    if not ptb_app._initialized: await ptb_app.initialize()
    try:
        await ptb_app.process_update(Update.de_json(request.get_json(force=True), ptb_app.bot))
    except Exception as e: print(e)
    return "OK"

if __name__ == '__main__':
    app.run(port=5000, debug=True)
