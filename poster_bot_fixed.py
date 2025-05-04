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
SELECT_TYPE, GET_NAME, SELECT_RESULT = range(3)

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
        # Skip force subscription if there's an error (usually means bot is not admin)
        print("Skipping force subscription due to error")
        
    # Continue with welcome message and conversation
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
    keyboard = [
        [InlineKeyboardButton("Search Movies/Series", callback_data="start_search")]
    ]
    
    await update.message.reply_photo(
        photo=WELCOME_IMG,
        caption=f"👋 Hi {user.mention_html()}!\n"
                f"Welcome to Media Finder!\n\n"
                f"Created by {ADMIN}\n"
                "Search for movies/series posters!",
        reply_markup=InlineKeyboardMarkup(keyboard),
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

async def search_media_options(message: Update, context: CallbackContext) -> int:
    """Search TMDb and display multiple options"""
    media_type = context.user_data["media_type"]
    name = context.user_data["name"]

    params = {
        "api_key": API_KEY,
        "query": name,
        "language": "en-US",
        "include_adult": False
    }

    try:
        response = requests.get(f"{BASE_URL}/search/{media_type}", params=params)
        response.raise_for_status()
        data = response.json()
        
        results = data.get("results", [])
        
        if not results:
            await message.reply_text("❌ No results found. Please try a different search term.")
            return ConversationHandler.END
        
        # Store all results for later use
        context.user_data["search_results"] = results[:10]  # Limit to 10 results
        
        # Create buttons for each result
        keyboard = []
        for i, item in enumerate(results[:10]):
            title = item.get("title") or item.get("name", "Unknown")
            year_str = ""
            
            # Get year from release date or first air date
            if item.get("release_date"):
                year_str = f" ({item['release_date'][:4]})"
            elif item.get("first_air_date"):
                year_str = f" ({item['first_air_date'][:4]})"
                
            # Add media type indicator
            type_emoji = "🎬" if media_type == "movie" else "📺"
            
            # Create button with title, year and index
            btn_text = f"{type_emoji} {title}{year_str}"
            keyboard.append([InlineKeyboardButton(btn_text, callback_data=f"result_{i}")])
        
        # Add cancel button
        keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data="cancel_search")])
        
        await message.reply_text(
            f"📋 Found {len(results[:10])} results for '{name}'.\nSelect one:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        return SELECT_RESULT
        
    except Exception as e:
        print(f"Search error: {e}")
        await message.reply_text(f"⚠️ Error: {str(e)}")
        return ConversationHandler.END

async def select_search_result(update: Update, context: CallbackContext) -> int:
    """Handle selection of a search result"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "cancel_search":
        await query.edit_message_text("🚫 Search cancelled. Press /start to search again.")
        return ConversationHandler.END
    
    # Extract the index from the callback data
    result_index = int(query.data.split("_")[1])
    selected_item = context.user_data["search_results"][result_index]
    
    # Store item details
    context.user_data.update({
        "title": selected_item.get("title") or selected_item.get("name"),
        "item_id": selected_item["id"],
        "year": (selected_item.get("release_date") or selected_item.get("first_air_date"))[:4] if (selected_item.get("release_date") or selected_item.get("first_air_date")) else "Unknown"
    })
    
    await query.edit_message_text(
        f"🎉 Selected: {context.user_data['title']}\n"
        f"📅 Year: {context.user_data['year']}\n\n"
        f"Fetching images..."
    )
    
    await fetch_images(query.message, context)
    return ConversationHandler.END

async def get_name(update: Update, context: CallbackContext) -> int:
    """Store name and search for results"""
    context.user_data["name"] = update.message.text
    await update.message.reply_text("🔍 Searching...")
    return await search_media_options(update.message, context)

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

        # Filter backdrops to only include those with a language specified
        language_backdrops = [b for b in images.get("backdrops", []) if b.get("iso_639_1") is not None]
        
        if language_backdrops:
            for backdrop in language_backdrops:
                url = IMAGE_BASE_URL + backdrop["file_path"]
                file_path = os.path.join("backdrops", os.path.basename(backdrop["file_path"]))
                language_code = backdrop.get("iso_639_1", "unknown")
                try:
                    with open(file_path, "wb") as f:
                        f.write(requests.get(url).content)
                    await message.reply_photo(open(file_path, "rb"), caption=f"🏞 {title} - Language: {language_code.upper()}")
                    sent = True
                finally:
                    if os.path.exists(file_path):
                        os.remove(file_path)
        else:
            await message.reply_text("No language-specific backdrops found for this title.")

        if sent:
            await message.reply_text("🎉 Thanks (This Msg From Athithan) for using me!\n⭐ Press /start to search again")
        else:
            await message.reply_text("🖼 No images found for this title")

    except Exception as e:
        await message.reply_text(f"⚠️ Image error: {str(e)}")

async def error_handler(update, context):
    """Handle errors in the dispatcher."""
    error = context.error
    print(f"Error occurred: {error}")
    
    if hasattr(update, 'effective_message') and update.effective_message:
        if 'Conflict' in str(error):
            await update.effective_message.reply_text("Bot is already running in another instance. Please try again later.")
        else:
            await update.effective_message.reply_text("An error occurred. Please try again later.")

def main() -> None:
    """Run the bot"""
    # Use a unique session name to prevent conflicts
    app = Application.builder() \
        .token("7896935352:AAEE_s_CU6q9ww7ovlD-9pGJo2OD3P4Mqsc") \
        .concurrent_updates(False) \
        .request(CustomHTTPXRequest()) \
        .build()

    app.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_sub$"))

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_TYPE: [CallbackQueryHandler(select_type)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            SELECT_RESULT: [CallbackQueryHandler(select_search_result)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    print("Starting bot with polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    os.makedirs("posters", exist_ok=True)
    os.makedirs("backdrops", exist_ok=True)
    main() 