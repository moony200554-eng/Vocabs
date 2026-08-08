import os
import logging
from datetime import datetime, timedelta, date

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)
from supabase import create_client, Client

from words_data import WORDS

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ["BOT_TOKEN"]
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_KEY = os.environ["SUPABASE_KEY"]

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

DAILY_COUNT = 15
EXTRA_COUNT = 5
TOTAL_WORDS = len(WORDS)


def get_user(chat_id: int):
    res = supabase.table("vocab_users").select("*").eq("chat_id", chat_id).execute()
    return res.data[0] if res.data else None


def upsert_user(chat_id: int, **fields):
    fields["chat_id"] = chat_id
    supabase.table("vocab_users").upsert(fields).execute()


def format_words(word_list):
    lines = []
    for i, w in enumerate(word_list, 1):
        lines.append(
            f"*{i}. {w['word']}*\n"
            f"   Meaning: {w['meaning']}\n"
            f"   Hindi: {w['hindi']}\n"
            f"   Example: _{w['example']}_"
        )
    return "\n\n".join(lines)


def next_batch(start_index: int, count: int):
    """Return `count` words starting at start_index, wrapping around the list."""
    batch = []
    idx = start_index
    for _ in range(count):
        batch.append(WORDS[idx % TOTAL_WORDS])
        idx += 1
    return batch, idx % TOTAL_WORDS


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    username = update.effective_user.username or update.effective_user.first_name
    user = get_user(chat_id)
    if not user:
        upsert_user(chat_id, username=username, word_index=0, daily_time="09:00")
        msg = (
            "Namaste! 👋 Main tumhara daily English vocab bot hoon.\n\n"
            f"Har din {DAILY_COUNT} words bhejunga — mix of simple & tough, "
            "with meaning, Hindi hint aur example sentence.\n\n"
            "Default time set hai *09:00 (IST)*. Change karne ke liye:\n"
            "`/settime 20:30` (24hr format, IST)\n\n"
            "Jab bhi extra words chahiye ho, bas bhejo:\n"
            "`/more` — turant 5 aur words milenge.\n\n"
            "Apna progress dekhne ke liye `/stats` bhejo."
        )
    else:
        msg = "Tum already registered ho! `/more` se extra words lo, ya `/stats` se progress dekho."
    await update.message.reply_text(msg, parse_mode="Markdown")


async def settime(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not context.args:
        await update.message.reply_text("Format: `/settime 20:30` (24hr, IST)", parse_mode="Markdown")
        return
    time_str = context.args[0]
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await update.message.reply_text("Galat format. Use `/settime HH:MM`, jaise `/settime 08:30`", parse_mode="Markdown")
        return
    user = get_user(chat_id)
    if not user:
        upsert_user(chat_id, username=update.effective_user.username, word_index=0, daily_time=time_str)
    else:
        upsert_user(chat_id, daily_time=time_str)
    await update.message.reply_text(f"Daily words ab *{time_str} IST* pe aayenge. ✅", parse_mode="Markdown")


async def more(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user:
        await update.message.reply_text("Pehle `/start` karo.")
        return
    batch, new_index = next_batch(user["word_index"], EXTRA_COUNT)
    upsert_user(
        chat_id,
        word_index=new_index,
        total_words_sent=(user.get("total_words_sent") or 0) + EXTRA_COUNT,
    )
    text = f"Yeh lo {EXTRA_COUNT} extra words 📚\n\n" + format_words(batch)
    await update.message.reply_text(text, parse_mode="Markdown")


async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user = get_user(chat_id)
    if not user:
        await update.message.reply_text("Pehle `/start` karo.")
        return
    total = user.get("total_words_sent") or 0
    await update.message.reply_text(
        f"📊 Ab tak seekhe: *{total}* words\n"
        f"Daily time: *{user.get('daily_time')} IST*",
        parse_mode="Markdown",
    )


async def send_daily_batches(context: ContextTypes.DEFAULT_TYPE):
    """Runs every minute. Checks each user's daily_time against current IST time."""
    now_utc = datetime.utcnow()
    ist_now = now_utc + timedelta(minutes=330)
    current_hm = ist_now.strftime("%H:%M")
    today = ist_now.date().isoformat()

    res = supabase.table("vocab_users").select("*").eq("daily_time", current_hm).execute()
    for user in res.data:
        if user.get("last_sent_date") == today:
            continue  # already sent today
        batch, new_index = next_batch(user["word_index"], DAILY_COUNT)
        text = f"🌟 Aaj ke {DAILY_COUNT} words:\n\n" + format_words(batch)
        try:
            await context.bot.send_message(chat_id=user["chat_id"], text=text, parse_mode="Markdown")
            upsert_user(
                user["chat_id"],
                word_index=new_index,
                last_sent_date=today,
                total_words_sent=(user.get("total_words_sent") or 0) + DAILY_COUNT,
            )
        except Exception as e:
            logger.error(f"Failed to send to {user['chat_id']}: {e}")


def main():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("settime", settime))
    app.add_handler(CommandHandler("more", more))
    app.add_handler(CommandHandler("stats", stats))

    app.job_queue.run_repeating(send_daily_batches, interval=60, first=5)

    logger.info("Bot starting...")
    app.run_polling()


if __name__ == "__main__":
    main()
