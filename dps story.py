import asyncio
import logging
import time
from datetime import timedelta
import aiosqlite

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
# CRUCIAL CONFIGURATION VARIABLES - Edit these as needed
# ==============================================================================
BOT_TOKEN = '8749988449:AAHYIa8axAcH6zToYLg7y3ElexBAN8aQp90'  # Replace with your actual bot token from @BotFather
ADMIN_ID = [8323137024, 8205396055, 5855151459]         # Replace with your numeric Telegram User ID
TIME_THRESHOLD = timedelta(minutes=10) # e.g., timedelta(minutes=5) (days=7)for testing
DB_NAME = 'channel_admin_bot.db'
# ==============================================================================

# Enable logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# ==============================================================================
# DATABASE SETUP & HELPERS
# ==============================================================================
async def init_db():
    """Initializes the SQLite database asynchronously."""
    async with aiosqlite.connect(DB_NAME) as db:
        # Track active users in channels
        await db.execute("""
            CREATE TABLE IF NOT EXISTS tracked_users (
                channel_id INTEGER,
                user_id INTEGER,
                join_time REAL,
                PRIMARY KEY (channel_id, user_id)
            )
        """)
        # Track which channels the bot is an admin in
        await db.execute("""
            CREATE TABLE IF NOT EXISTS active_channels (
                channel_id INTEGER PRIMARY KEY,
                channel_name TEXT
            )
        """)
        # Track global statistics (like total kicked)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_stats (
                key TEXT PRIMARY KEY,
                value INTEGER
            )
        """)
        await db.execute("INSERT OR IGNORE INTO bot_stats (key, value) VALUES ('total_kicked', 0)")
        await db.commit()

# ==============================================================================
# EVENT HANDLERS
# ==============================================================================
async def track_bot_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tracks when the bot is added or removed as an admin from a channel."""
    result = update.my_chat_member
    if not result or result.chat.type != "channel":
        return

    chat_id = result.chat.id
    chat_name = result.chat.title
    new_status = result.new_chat_member.status

    async with aiosqlite.connect(DB_NAME) as db:
        if new_status == "administrator":
            await db.execute("INSERT OR REPLACE INTO active_channels (channel_id, channel_name) VALUES (?, ?)", (chat_id, chat_name))
            logger.info(f"Bot added as admin to channel: {chat_name} ({chat_id})")
        elif new_status in ["left", "kicked"]:
            await db.execute("DELETE FROM active_channels WHERE channel_id = ?", (chat_id,))
            # Optionally remove all tracked users for this channel to save space
            await db.execute("DELETE FROM tracked_users WHERE channel_id = ?", (chat_id,))
            logger.info(f"Bot removed from channel: {chat_name} ({chat_id})")
        await db.commit()

async def track_user_joins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Tracks when a user joins a channel the bot is administering."""
    result = update.chat_member
    if not result or result.chat.type != "channel":
        return

    old_status = result.old_chat_member.status
    new_status = result.new_chat_member.status

    # If the user transitioned from not being a member to being a member
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
        logger.info(f"New user {user_id} joined channel {chat_id} at {current_time}.")

# ==============================================================================
# CORE KICK LOGIC & SCHEDULER
# ==============================================================================
async def kick_user_with_retry(bot, channel_id, user_id, max_retries=3) -> bool:
    """Attempts to kick a user. Handles API rate limits safely."""
    for attempt in range(max_retries):
        try:
            # In Telegram, to 'remove' a user from a channel, you ban then unban them.
            await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
            await bot.unban_chat_member(chat_id=channel_id, user_id=user_id)
            logger.info(f"Successfully kicked user {user_id} from {channel_id}.")
            return True
        except RetryAfter as e:
            logger.warning(f"Rate limited by Telegram API! Sleeping for {e.retry_after}s.")
            await asyncio.sleep(e.retry_after)
        except (BadRequest, Forbidden) as e:
            # This happens if bot loses admin rights, or user already left/was deleted
            logger.error(f"Failed to kick user {user_id} from {channel_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error while kicking: {e}")
            return False
    return False

async def cleanup_job(context: ContextTypes.DEFAULT_TYPE, manual=False):
    """Scans the database and kicks users who exceeded the time threshold."""
    bot = context.bot
    current_time = time.time()
    threshold_seconds = current_time - TIME_THRESHOLD.total_seconds()
    
    kicked_count_this_run = 0

    async with aiosqlite.connect(DB_NAME) as db:
        # Fetch users who have been in the channel longer than the threshold
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT channel_id, user_id FROM tracked_users WHERE join_time < ?", 
            (threshold_seconds,)
        ) as cursor:
            users_to_kick = await cursor.fetchall()

        for row in users_to_kick:
            channel_id = row['channel_id']
            user_id = row['user_id']
            
            # Execute the kick
            success = await kick_user_with_retry(bot, channel_id, user_id)
            
            # Remove from DB whether successful or if it failed due to permissions (cleanup DB)
            await db.execute(
                "DELETE FROM tracked_users WHERE channel_id = ? AND user_id = ?", 
                (channel_id, user_id)
            )
            
            if success:
                kicked_count_this_run += 1
                await db.execute("UPDATE bot_stats SET value = value + 1 WHERE key = 'total_kicked'")
            
            # Small artificial delay to prevent hitting base API limits across 350 channels
            await asyncio.sleep(0.05) 
            
        await db.commit()
    
    if manual and kicked_count_this_run > 0:
        logger.info(f"Manual cleanup finished. Kicked {kicked_count_this_run} users.")

# ==============================================================================
# ADMIN UI INTERFACE (DM ONLY)
# ==============================================================================
def get_main_menu_keyboard():
    keyboard = [
        [InlineKeyboardButton("📊 View Stats", callback_data='menu_stats')],
        [InlineKeyboardButton("⚙️ Current Timer", callback_data='menu_timer')],
        [InlineKeyboardButton("🧹 Manual Cleanup", callback_data='menu_cleanup')]
    ]
    return InlineKeyboardMarkup(keyboard)

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the /start command in private messages."""
    user_id = update.effective_user.id
    if user_id != ADMIN_ID:
        return # Ignore everyone else

    await update.message.reply_text(
        "👋 Welcome to the Channel Admin Manager Bot.\n\n"
        "Please select an option below:",
        reply_markup=get_main_menu_keyboard()
    )

async def menu_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles inline keyboard button presses."""
    query = update.callback_query
    user_id = query.from_user.id
    
    if user_id != ADMIN_ID:
        await query.answer("You are not authorized to use this bot.", show_alert=True)
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
        days = TIME_THRESHOLD.days
        seconds = TIME_THRESHOLD.seconds
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        time_str = []
        if days > 0: time_str.append(f"{days} days")
        if hours > 0: time_str.append(f"{hours} hours")
        if minutes > 0: time_str.append(f"{minutes} minutes")
        if not time_str: time_str.append(f"{seconds} seconds")
        
        text = (
            "⚙️ **Current Timer Configuration**\n\n"
            f"Users are kicked after: **{', '.join(time_str)}**\n\n"
            "*To change this, edit the `TIME_THRESHOLD` variable in the script and restart.*"
        )
        await query.edit_message_text(text, parse_mode='Markdown', reply_markup=get_main_menu_keyboard())

    elif data == 'menu_cleanup':
        await query.edit_message_text(
            "🧹 Manual cleanup triggered. The bot is now scanning the database in the background...",
            reply_markup=get_main_menu_keyboard()
        )
        # Trigger the job asynchronously without waiting for it to finish in the UI
        asyncio.create_task(cleanup_job(context, manual=True))


# ==============================================================================
# MAIN APPLICATION SETUP
# ==============================================================================
def main():
    """Builds and runs the bot."""
    # Ensure event loop compatibility for aiosqlite setup on boot
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(init_db())

    # Create the application
    application = Application.builder().token(BOT_TOKEN).build()

    # Track Bot joining/leaving channels
    application.add_handler(ChatMemberHandler(track_bot_channels, ChatMemberHandler.MY_CHAT_MEMBER))
    
    # Track Users joining channels
    application.add_handler(ChatMemberHandler(track_user_joins, ChatMemberHandler.CHAT_MEMBER))

    # Admin Private UI Handlers
    application.add_handler(CommandHandler("start", start_cmd, filters=filters.ChatType.PRIVATE))
    application.add_handler(CallbackQueryHandler(menu_callback_handler))

    # Setup the background scheduler loop (runs every 60 seconds)
    job_queue = application.job_queue
    job_queue.run_repeating(cleanup_job, interval=60, first=10)

    logger.info("Bot is starting up...")
    
    # Start polling
    # Allowed updates restricts events to only what we need to minimize API bandwidth across 350 channels
    application.run_polling(allowed_updates=[Update.MESSAGE, Update.CHAT_MEMBER, Update.MY_CHAT_MEMBER, Update.CALLBACK_QUERY])

if __name__ == "__main__":
    main()

