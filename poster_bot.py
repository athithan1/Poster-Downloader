import os
import requests
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    CallbackContext,
    ConversationHandler,
)
from telegram.request import HTTPXRequest
import httpx

# Configuration
API_KEY = "2a38c80417194db46b7389ec0bc80536"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"
CHANNEL = "@athithan_220"
ADMIN = "@ragnarlothbrockV"
WELCOME_IMG = "https://imgur.com/a/Ky9LsC4.jpg"

# Conversation states
SELECT_TYPE, GET_NAME, GET_YEAR = range(3)

class CustomHTTPXRequest(HTTPXRequest):
    def _build_client(self):
        client_kwargs = self._client_kwargs.copy()
        client_kwargs.pop("proxy", None)
        return httpx.AsyncClient(**client_kwargs)

async def start(update: Update, context: CallbackContext) -> int:
    """Initial command with force sub check"""
    user = update.effective_user
    try:
        member = await context.bot.get_chat_member(CHANNEL, user.id)
        if member.status in ['left', 'kicked']:
            await show_force_sub(update)
            return ConversationHandler.END
    except Exception as e:
        print(f"Force sub check error: {e}")
        await update.message.reply_text("⚠️ Bot configuration error. Please try again later.")
        return ConversationHandler.END

    await send_welcome(update, user)
    return SELECT_TYPE

async def show_force_sub(update: Update):
    """Show force subscription message"""
    keyboard = [
        [InlineKeyboardButton("Join Channel", url=f"https://t.me/{CHANNEL[1:]}")],
        [InlineKeyboardButton("Try Again", callback_data="check_sub")]
    ]
    await update.message.reply_photo(
        photo=WELCOME_IMG,
        caption=f"👋 Hi {update.effective_user.mention_html()}!\n\n"
                f"I'm created by Athithan {ADMIN}\n\n"
                f"⚠️ To use this bot you must join:\n{CHANNEL}",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='HTML'
    )

async def check_subscription(update: Update, context: CallbackContext):
    """Handle subscription check callback"""
    query = update.callback_query
    await query.answer()
    try:
        member = await context.bot.get_chat_member(CHANNEL, query.from_user.id)
        if member.status in ['left', 'kicked']:
            await query.edit_message_caption(caption="❌ You still haven't joined the channel!")
            return
        await query.edit_message_caption(caption="✅ Subscription verified! Press /start to continue")
    except Exception as e:
        await query.edit_message_caption(caption="⚠️ Verification failed. Try again later.")

async def send_welcome(update: Update, user):
    """Send main welcome message"""
    await update.message.reply_photo(
        photo=WELCOME_IMG,
        caption=f"👋 Hi {user.mention_html()}!\n"
                f"Welcome to Media Finder!\n\n"
                f"Created by {ADMIN}\n"
                "Search for movies/series posters!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Start Searching", callback_data="start_search")]
        ]),
        parse_mode='HTML'
    )

async def select_type(update: Update, context: CallbackContext) -> int:
    """Handle media type selection"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "start_search":
        keyboard = [
            [InlineKeyboardButton("Movie", callback_data="movie"),
             InlineKeyboardButton("Series/Anime", callback_data="tv")],
            [InlineKeyboardButton("Other", callback_data="other")]
        ]
        await query.edit_message_caption(
            caption="🎬 Choose content type:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_TYPE
    
    context.user_data["media_type"] = query.data
    await query.edit_message_caption(caption="📝 Enter the name (movie,series):")
    return GET_NAME

async def get_name(update: Update, context: CallbackContext) -> int:
    """Store name and ask for year"""
    context.user_data["name"] = update.message.text
    await update.message.reply_text(
        "📅 Enter release year (or /skip):",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Skip Year", callback_data="skip")]])
    )
    return GET_YEAR

async def skip_year(update: Update, context: CallbackContext) -> int:
    """Handle year skipping"""
    query = update.callback_query
    await query.answer()
    context.user_data["year"] = None
    await query.edit_message_text("🔍 Searching...")
    await search_media(query.message, context)
    return ConversationHandler.END

async def get_year(update: Update, context: CallbackContext) -> int:
    """Store year and initiate search"""
    context.user_data["year"] = update.message.text
    await update.message.reply_text("🔍 Searching...")
    await search_media(update.message, context)
    return ConversationHandler.END

async def search_media(message: Update, context: CallbackContext):
    """Search TMDb and handle results"""
    media_type = context.user_data["media_type"]
    name = context.user_data["name"]
    year = context.user_data.get("year")

    params = {
        "api_key": API_KEY,
        "query": name,
        "language": "en-US",
        "include_adult": False
    }

    if year:
        key = "year" if media_type == "movie" else "first_air_date_year"
        params[key] = year

    try:
        response = requests.get(f"{BASE_URL}/search/{media_type}", params=params)
        response.raise_for_status()
        data = response.json()
        
        if not data["results"]:
            await message.reply_text("❌ No results found")
            return

        item = data["results"][0]
        context.user_data.update({
            "title": item.get("title") or item.get("name"),
            "item_id": item["id"],
            "year": (item.get("release_date") or item.get("first_air_date"))[:4] if item.get("release_date") else "Unknown"
        })

        await message.reply_text(
            f"🎉 Found: {context.user_data['title']}\n"
            f"📅 Year: {context.user_data['year']}"
        )
        await fetch_images(message, context)

    except Exception as e:
        await message.reply_text(f"⚠️ Error: {str(e)}")

async def fetch_images(message: Update, context: CallbackContext):
    """Fetch and send images from TMDb"""
    media_type = context.user_data["media_type"]
    item_id = context.user_data["item_id"]
    title = context.user_data["title"]

    try:
        response = requests.get(f"{BASE_URL}/{media_type}/{item_id}/images", params={"api_key": API_KEY})
        response.raise_for_status()
        images = response.json()

        sent = False
        for poster in images.get("posters", [])[:3]:
            url = IMAGE_BASE_URL + poster["file_path"]
            file_path = os.path.join("posters", os.path.basename(poster["file_path"]))
            try:
                with open(file_path, "wb") as f:
                    f.write(requests.get(url).content)
                await message.reply_photo(open(file_path, "rb"), caption=f"📸 {title}")
                sent = True
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

        for backdrop in images.get("backdrops", [])[:3]:
            url = IMAGE_BASE_URL + backdrop["file_path"]
            file_path = os.path.join("backdrops", os.path.basename(backdrop["file_path"]))
            try:
                with open(file_path, "wb") as f:
                    f.write(requests.get(url).content)
                await message.reply_photo(open(file_path, "rb"), caption=f"🏞 {title}")
                sent = True
            finally:
                if os.path.exists(file_path):
                    os.remove(file_path)

        if sent:
            await message.reply_text("🎉 Thanks (This Msg From Athithan) for using me!\n⭐ Press /start to search again")
        else:
            await message.reply_text("🖼 No images found for this title")

    except Exception as e:
        await message.reply_text(f"⚠️ Image error: {str(e)}")

def main() -> None:
    """Run the bot"""
    app = Application.builder() \
        .token("7896935352:AAEE_s_CU6q9ww7ovlD-9pGJo2OD3P4Mqsc") \
        .request(CustomHTTPXRequest()) \
        .build()

    app.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_sub$"))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_TYPE: [CallbackQueryHandler(select_type)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            GET_YEAR: [
                CallbackQueryHandler(skip_year, pattern="^skip$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, get_year)
            ],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    app.run_polling()

if __name__ == "__main__":
    main()
