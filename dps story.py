import asyncio
import logging
import time
import os
import threading
import requests
import aiosqlite
from flask import Flask

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ChatMemberHandler,
    ContextTypes,
    filters,
)
from telegram.error import RetryAfter, BadRequest, Forbidden

# ==============================================================================
# CONFIGURATION VARIABLES
# ==============================================================================
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8749988449:AAGROgxIJbDMTJJE5AOBki8TvLC74QjPhLo') 

# Parses comma-separated IDs from Render Env variables, or uses your default list
admin_env = os.environ.get('ADMIN_IDS', '8323137024, 8205396055, 5855151459')
ADMIN_IDS = [int(x.strip()) for x in admin_env.split(',')]

DB_NAME = 'channel_admin_bot.db'
RENDER_EXTERNAL_URL = "https://des-story-tg.onrender.com"

# ==============================================================================
# LOGGING SETUP
# ==============================================================================
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("werkzeug").setLevel(logging.WARNING) # Silence Flask logs

# ==============================================================================
# KEEP-ALIVE WEB SERVER & PINGER (Flask + Threading)
# ==============================================================================
flask_app = Flask('')

@flask_app.route('/')
def home(): 
    return "Bot is running 24/7!"

def ping_self():
    """Pings the Render URL every 14 minutes to prevent sleep."""
    while True:
        try: 
            requests.get(RENDER_EXTERNAL_URL)
            logger.info("Self-ping successful.")
        except Exception as e: 
            logger.error(f"Self-ping failed: {e}")
        time.sleep(840) # 840 seconds = 14 minutes

# ==============================================================================
# DATABASE SETUP & HELPERS
# ==============================================================================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_users (
                channel_id INTEGER,
                user_id INTEGER,
                join_time REAL,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                key TEXT PRIMARY KEY,
                value INTEGER
            )
        """)
        await db.execute("INSERT OR IGNORE INTO bot_stats (key, value) VALUES ('total_kicked', 0)")
        await db.execute("INSERT OR IGNORE INTO bot_stats (key, value) VALUES ('time_threshold', 604800)")
        await db.commit()

# ==============================================================================
# EVENT HANDLERS
# ==============================================================================
async def track_bot_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.my_chat_member
    if not result or result.chat.type != "channel":
        return

    chat_id = result.chat.id
    chat_name = result.chat.title
    new_status = result.new_chat_member.status

    async with aiosqlite.connect(DB_NAME) as db:
        if new_status == "administrator":
            await db.execute("INSERT OR REPLACE INTO active_channels (channel_id, channel_name) VALUES (?, ?)", (chat_id, chat_name))
            logger.info(f"Bot added as admin to: {chat_name}")
        elif new_status in ["left", "kicked"]:
            await db.execute("DELETE FROM active_channels WHERE channel_id = ?", (chat_id,))
            await db.execute("DELETE FROM tracked_users WHERE channel_id = ?", (chat_id,))
            logger.info(f"Bot removed from: {chat_name}")
        await db.commit()

async def track_user_joins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = update.chat_member
    if not result or result.chat.type != "channel":
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    if old_status in ["left", "kicked"] and new_status == "member":
        chat_id = result.chat.id
        user_id = result.new_chat_member.user.id
        current_time = time.time()

        async with aiosqlite.connect(DB_NAME) as db:
            await db.execute(
                "INSERT OR REPLACE INTO tracked_users (channel_id, user_id, join_time) VALUES (?, ?, ?)",
                (chat_id, user_id, current_time)
            )
            await db.commit()

# ==============================================================================
# CORE KICK LOGIC & SCHEDULER
# ==============================================================================
async def kick_user_with_retry(bot, channel_id, user_id, max_retries=3) -> bool:
    for attempt in range(max_retries):
        try:
            await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
            await bot.unban_chat_member(chat_id=channel_id, user_id=user_id)
            return True
        except RetryAfter as e:
            logger.warning(f"Rate limited! Sleeping for {e.retry_after}s.")
            await asyncio.sleep(e.retry_after)
        except (BadRequest, Forbidden):
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            return False
    return False

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE, manual=False):
    bot = context.bot
    current_time = time.time()
    kicked_count_this_run = 0

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM bot_stats WHERE key = 'time_threshold'") as cur:
            threshold_seconds_duration = (await cur.fetchone())[0]
            
        threshold_timestamp = current_time - threshold_seconds_duration

        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT channel_id, user_id FROM tracked_users WHERE join_time < ?", 
            (threshold_timestamp,)
        ) as cursor:
            users_to_kick = await cursor.fetchall()

        for row in users_to_kick:
            channel_id = row['channel_id']
            user_id = row['user_id']
            
            success = await kick_user_with_retry(bot, channel_id, user_id)
            
            await db.execute(
                "DELETE FROM tracked_users WHERE channel_id = ? AND user_id = ?", 
                (channel_id, user_id)
            )
            
            if success:
                kicked_count_this_run += 1
                await db.execute("UPDATE bot_stats SET value = value + 1 WHERE key = 'total_kicked'")
            
            await asyncio.sleep(0.05) 
            
        await db.commit()
    
    if manual:
        logger.info(f"Manual cleanup finished. Kicked {kicked_count_this_run} users.")

# ==============================================================================
# ADMIN UI INTERFACE & COMMANDS
# ==============================================================================
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 View Stats", callback_data='menu_stats')],
        [InlineKeyboardButton("⚙️ Current Timer", callback_data='menu_timer')],
        [InlineKeyboardButton("🧹 Manual Cleanup", callback_data='menu_cleanup')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return
    await update.message.reply_text(
        "👋 Welcome to the Channel Admin Manager Bot.\n\n"
        "Use `/dps <unit> <value>` to set the timer.\n"
        "*(Example: `/dps days 30`, `/dps minutes 5`)*\n\n"
        "Or use the menu below:",
        reply_markup=get_main_menu_keyboard(),
        parse_mode="Markdown"
    )

async def dps_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id not in ADMIN_IDS: return

    args = context.args
    if len(args) != 2:
        await update.message.reply_text(
            "⚠️ **Invalid Format**\nUsage: `/dps <unit> <value>`\nExamples: `/dps days 30`, `/dps minutes 5`, `/dps hours 12`", 
            parse_mode="Markdown"
        )
        return

    unit = args[0].lower()
    try:
        value = int(args[1])
    except ValueError:
        await update.message.reply_text("⚠️ The value must be a number.")
        return

    if unit in ['day', 'days']: seconds = value * 24 * 3600
    elif unit in ['hour', 'hours']: seconds = value * 3600
    elif unit in ['minute', 'minutes', 'min', 'mins']: seconds = value * 60
    elif unit in ['second', 'seconds', 'sec']: seconds = value
    else:
        await update.message.reply_text("⚠️ Unknown unit. Use `days`, `hours`, `minutes`, or `seconds`.", parse_mode="Markdown")
        return

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("UPDATE bot_stats SET value = ? WHERE key = 'time_threshold'", (seconds,))
        await db.commit()

    await update.message.reply_text(f"✅ Auto-kick timer successfully updated to **{value} {unit}**.", parse_mode="Markdown")

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query.from_user.id not in ADMIN_IDS:
        await query.answer("Not authorized.", show_alert=True)
        return

    await query.answer()
    data = query.data

    if data == 'menu_stats':
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT COUNT(*) FROM active_channels") as cur:
                channels_count = (await cur.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM tracked_users") as cur:
                users_count = (await cur.fetchone())[0]
            async with db.execute("SELECT value FROM bot_stats WHERE key = 'total_kicked'") as cur:
                kicked_count = (await cur.fetchone())[0]
                
        text = (
            "📊 **Bot Statistics**\n\n"
            f"📡 Active Channels: {channels_count}\n"
            f"👥 Active Tracked Users: {users_count}\n"
            f"🚫 Total Users Kicked: {kicked_count}"
        )
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

    elif data == 'menu_timer':
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT value FROM bot_stats WHERE key = 'time_threshold'") as cur:
                total_seconds = (await cur.fetchone())[0]

        days = total_seconds // (24 * 3600)
        remaining = total_seconds % (24 * 3600)
        hours = remaining // 3600
        minutes = (remaining % 3600) // 60
        secs = remaining % 60
        
        time_str = []
        if days > 0: time_str.append(f"{days} days")
        if hours > 0: time_str.append(f"{hours} hours")
        if minutes > 0: time_str.append(f"{minutes} minutes")
        if secs > 0 or not time_str: time_str.append(f"{secs} seconds")
        
        text = (
            "⚙️ **Current Timer Configuration**\n\n"
            f"Users are kicked after: **{', '.join(time_str)}**\n\n"
            "*To change this, send a command like:*\n`/dps days 30`"
        )
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

    elif data == 'menu_cleanup':
        await query.edit_message_text(
            "🧹 Manual cleanup triggered. Scanning database...",
            reply_markup=get_main_menu_keyboard()
        )
        asyncio.create_task(cleanup_job(context, manual=True))

# ==============================================================================
# MAIN 
# ==============================================================================
def main():
    # Initialize the SQLite DB
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

    # Start Flask Web Server in a background thread
    port = int(os.environ.get("PORT", 8080))
    threading.Thread(target=lambda: flask_app.run(host='0.0.0.0', port=port), daemon=True).start()
    
    # Start the Self-Pinger in a background thread
    threading.Thread(target=ping_self, daemon=True).start()

    # Build the application with 30-second timeouts
    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .connect_timeout(30.0)
        .read_timeout(30.0)
        .write_timeout(30.0)
        .pool_timeout(30.0)
        .build()
    )

    application.add_handler(ChatMemberHandler(track_bot_channels, ChatMemberHandler.MY_CHAT_MEMBER))
    application.add_handler(ChatMemberHandler(track_user_joins, ChatMemberHandler.CHAT_MEMBER))
    
    application.add_handler(CommandHandler("start", start_cmd, filters=filters.ChatType.PRIVATE))
    application.add_handler(CommandHandler("dps", dps_cmd, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(menu_callback_handler))

    job_queue = application.job_queue
    job_queue.run_repeating(cleanup_job, interval=60, first=10)

    logger.info("Bot is polling and pinging itself 24/7...")
    application.run_polling(allowed_updates=[Update.MESSAGE, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER, Update.CALLBACK_QUERY])

if __name__ == "__main__":
    main()

