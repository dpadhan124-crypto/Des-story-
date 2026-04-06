import os
import sys
import asyncio
import aiosqlite
import aiohttp
import threading
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from aiohttp import web

# --- THE PYTHON 3.14 / PYROGRAM FIX ---
# We must mock the event loop before Pyrogram is even touched
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

# --- CONFIGURATION ---
API_ID = int(os.getenv("API_ID", 28515728))
API_HASH = os.getenv("API_HASH", "c8df3dfc2cb3cc6b0aa1b6ad6a0f8830")
BOT_TOKEN = os.getenv("BOT_TOKEN", "8552684809:AAGSRPA-3k0huC9fKBAvJGGI-VYfDhe4RJQ")
TARGET_GROUP_ID = int(os.getenv("TARGET_GROUP_ID", -1003742470706))
ADMIN_IDS = [8323137024, 8205396055, 5855151459]
RENDER_URL = os.getenv("RENDER_URL", "https://des-story-tg.onrender.com/")
DB_NAME = "bot_data.db"

# --- KEEP ALIVE LOGIC ---
async def handle_ping(request):
    return web.Response(text="Bot is Running!")

async def start_web_server():
    server = web.Application()
    server.add_routes([web.get('/', handle_ping)])
    runner = web.AppRunner(server)
    await runner.setup()
    port = int(os.getenv("PORT", "8080"))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")

async def ping_self():
    if "onrender.com" not in RENDER_URL: return
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(RENDER_URL) as resp:
                print(f"Self-Ping: {resp.status} at {datetime.now()}")
        except Exception as e:
            print(f"Ping failed: {e}")

async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute('CREATE TABLE IF NOT EXISTS topics (channel_id INTEGER PRIMARY KEY, thread_id INTEGER, title TEXT)')
        await db.execute('CREATE TABLE IF NOT EXISTS admin_channels (channel_id INTEGER PRIMARY KEY, title TEXT)')
        await db.commit()

# --- MAIN RUNNER ---
async def main():
    # Start web server first to pass Render's health check
    await start_web_server()
    await init_db()

    # Delay Pyrogram imports until the loop is confirmed running
    print("Loading Pyrogram...")
    from pyrogram import Client, filters
    from pyrogram.types import Message, ChatMemberUpdated
    from pyrogram.errors import FloodWait
    from pyrogram.enums import ChatMemberStatus

    app = Client("my_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

    @app.on_message((filters.audio | filters.video) & filters.channel)
    async def forwarder(_, message: Message):
        source_id = message.chat.id
        source_title = message.chat.title or "Media Channel"
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT thread_id FROM topics WHERE channel_id=?", (source_id,)) as c:
                row = await c.fetchone()
                thread_id = row[0] if row else None

        if not thread_id:
            try:
                topic = await app.create_forum_topic(TARGET_GROUP_ID, source_title)
                thread_id = topic.id
                async with aiosqlite.connect(DB_NAME) as db:
                    await db.execute("INSERT INTO topics VALUES (?, ?, ?)", (source_id, thread_id, source_title))
                    await db.commit()
            except Exception as e:
                print(f"Topic Error: {e}")
                return
        try:
            await app.forward_messages(TARGET_GROUP_ID, source_id, message.id, message_thread_id=thread_id)
        except Exception as e:
            print(f"Forward Error: {e}")

    async def auto_job():
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT channel_id FROM admin_channels") as c:
                rows = await c.fetchall()
                ids = [r[0] for r in rows]
                if ids:
                    limit = datetime.utcnow() - timedelta(days=7)
                    for cid in ids:
                        try:
                            async for m in app.get_chat_members(cid):
                                if m.status in [ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR]: continue
                                if m.joined_date and m.joined_date < limit:
                                    await app.ban_chat_member(cid, m.user.id)
                                    await app.unban_chat_member(cid, m.user.id)
                                    await asyncio.sleep(1)
                        except: continue

    sch = AsyncIOScheduler()
    sch.add_job(auto_job, "cron", hour=2, minute=30) 
    sch.add_job(ping_self, "interval", minutes=10)   
    sch.start()
    
    print("Bot starting...")
    await app.start()
    print("Bot is LIVE!")
    await asyncio.Event().wait()

if __name__ == "__main__":
    # Get the loop we created at the top
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except (KeyboardInterrupt, SystemExit):
        pass
    finally:
        loop.close()

