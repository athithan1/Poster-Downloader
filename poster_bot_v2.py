import os
import requests
import tempfile
import shutil
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
import logging
import instaloader
from datetime import datetime
import re

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration
API_KEY = "2a38c80417194db46b7389ec0bc80536"
BASE_URL = "https://api.themoviedb.org/3"
IMAGE_BASE_URL = "https://image.tmdb.org/t/p/original"

# *** IMPORTANT: Update these with your own channel and admin username ***
# Also make sure to add your bot as admin to this channel with permission to check members
CHANNEL = "@athithan_220"  # Your channel username
ADMIN = "@ragnarlothbrockV"  # Your admin username
WELCOME_IMG = "https://imgur.com/a/Ky9LsC4.jpg"

# Conversation states
SELECT_TYPE, GET_NAME, SELECT_RESULT, GET_INSTAGRAM_URL = range(4)

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
        logger.error(f"Force sub check error: {e}")
        # Skip force subscription if there's an error (usually means bot is not admin)
        logger.info("Skipping force subscription due to error")
        
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
        [InlineKeyboardButton("Search Movies/Series", callback_data="start_search")],
        [InlineKeyboardButton("Instagram Downloader", callback_data="instagram_downloader")]
    ]
    
    await update.message.reply_photo(
        photo=WELCOME_IMG,
        caption=f"👋 Hi {user.mention_html()}!\n"
                f"Welcome to Media Finder!\n\n"
                f"Created by {ADMIN}\n"
                "Choose an option below:",
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
    elif query.data == "instagram_downloader":
        await query.edit_message_text(
            "📷 Instagram Downloader\n\n"
            "Send me an Instagram post, reel, or profile URL to download content."
        )
        return GET_INSTAGRAM_URL
    
    context.user_data["media_type"] = query.data
    await query.edit_message_caption(caption="📝 Enter the name (movie,series):")
    return GET_NAME

async def get_instagram_url(update: Update, context: CallbackContext) -> int:
    """Process Instagram URL"""
    url = update.message.text
    
    # Check if this is a valid Instagram URL
    if not is_valid_instagram_url(url):
        await update.message.reply_text(
            "❌ This doesn't look like a valid Instagram URL.\n\n"
            "Please send a valid Instagram post, reel, or profile URL."
        )
        return GET_INSTAGRAM_URL
    
    await update.message.reply_text("⏳ Processing Instagram content... This may take a moment.")
    
    try:
        # Download Instagram content
        result = await download_from_instagram(url, update, context)
        if result:
            await update.message.reply_text(
                "✅ Download completed!\n\n"
                "Press /start to download more content."
            )
        else:
            await update.message.reply_text(
                "❌ Failed to download content.\n\n"
                "This might be a private profile or the content may no longer be available."
            )
    except Exception as e:
        logger.error(f"Instagram download error: {e}")
        await update.message.reply_text(
            f"❌ Error downloading content: {str(e)}\n\n"
            "Please try again with a different link."
        )
    
    return ConversationHandler.END

def is_valid_instagram_url(url):
    """Check if a URL is a valid Instagram URL"""
    instagram_regex = r'(https?:\/\/)?(www\.)?(instagram\.com|instagr\.am)\/([a-zA-Z0-9_\.]+(\/)?|p\/[a-zA-Z0-9_-]+\/?|reel\/[a-zA-Z0-9_-]+\/?)'
    return re.match(instagram_regex, url) is not None

async def download_from_instagram(url, update, context):
    """Download content from Instagram"""
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False
    )
    
    # Create temp directory for downloads
    temp_dir = tempfile.mkdtemp()
    try:
        # Extract shortcode from URL
        if '/p/' in url or '/reel/' in url:
            shortcode = url.split('/p/')[-1].split('/')[0] if '/p/' in url else url.split('/reel/')[-1].split('/')[0]
            shortcode = shortcode.split('?')[0]  # Remove query parameters
            
            # Download post
            post = instaloader.Post.from_shortcode(L.context, shortcode)
            L.download_post(post, target=temp_dir)
            
            # Send media files
            media_sent = False
            for filename in os.listdir(temp_dir):
                filepath = os.path.join(temp_dir, filename)
                if filename.endswith('.jpg') and not filename.endswith('_profile_pic.jpg'):
                    # It's a photo
                    await update.message.reply_photo(
                        photo=open(filepath, 'rb'),
                        caption=f"📸 Instagram Photo\nFrom: {post.owner_username}"
                    )
                    media_sent = True
                elif filename.endswith('.mp4'):
                    # It's a video
                    await update.message.reply_video(
                        video=open(filepath, 'rb'),
                        caption=f"🎥 Instagram Video\nFrom: {post.owner_username}"
                    )
                    media_sent = True
            
            return media_sent
        
        # Handle profile URLs
        elif re.search(r'instagram\.com/([a-zA-Z0-9_\.]+)/?$', url):
            username = url.split('instagram.com/')[-1].strip('/')
            # Download profile pic only
            profile = instaloader.Profile.from_username(L.context, username)
            L.download_profilepic(profile)
            
            # Find the profile pic
            for filename in os.listdir('.'):
                if username in filename and filename.endswith('.jpg'):
                    await update.message.reply_photo(
                        photo=open(filename, 'rb'),
                        caption=f"👤 Profile Picture of @{username}\n"
                               f"Full name: {profile.full_name}\n"
                               f"Bio: {profile.biography[:100]}..."
                    )
                    os.remove(filename)  # Clean up
                    return True
        
        return False
    
    except Exception as e:
        logger.error(f"Error in Instagram download: {e}")
        raise
    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)

async def get_name(update: Update, context: CallbackContext) -> int:
    """Store name and search for results"""
    context.user_data["name"] = update.message.text
    await update.message.reply_text("🔍 Searching...")
    return await search_media_options(update.message, context)

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
        logger.error(f"Search error: {e}")
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
    
    # Create keyboard with download options
    keyboard = [
        [InlineKeyboardButton("Download Preview (3 Posters)", callback_data="preview_posters")],
        [InlineKeyboardButton("Download All Posters & Backdrops", callback_data="download_all")]
    ]
    
    await query.edit_message_text(
        f"🎉 Selected: {context.user_data['title']}\n"
        f"📅 Year: {context.user_data['year']}\n\n"
        f"Choose download option:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )
    
    # Add handler for the download options
    app = context.application
    app.add_handler(CallbackQueryHandler(handle_download_option, pattern="^(preview_posters|download_all)$"))
    
    return ConversationHandler.END

async def handle_download_option(update: Update, context: CallbackContext):
    """Handle download option selection"""
    query = update.callback_query
    await query.answer()
    
    download_all = query.data == "download_all"
    
    await query.edit_message_text(
        f"🔍 Fetching images for {context.user_data['title']}...\n"
        f"This may take a moment."
    )
    
    await fetch_images(query.message, context, download_all=download_all)

async def fetch_images(message: Update, context: CallbackContext, download_all=False):
    """Fetch and send images from TMDb"""
    media_type = context.user_data["media_type"]
    item_id = context.user_data["item_id"]
    title = context.user_data["title"]

    try:
        response = requests.get(f"{BASE_URL}/{media_type}/{item_id}/images", params={"api_key": API_KEY})
        response.raise_for_status()
        images = response.json()

        sent = False
        posters = images.get("posters", [])
        
        # Limit posters to 3 unless download_all is True
        poster_count = len(posters) if download_all else min(3, len(posters))
        
        if poster_count > 0:
            await message.reply_text(f"📸 Downloading {poster_count} posters...")
            
            for poster in posters[:poster_count]:
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
            await message.reply_text(f"🏞 Downloading {len(language_backdrops)} language backdrops...")
            
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
        logger.error(f"Image error: {e}")
        await message.reply_text(f"⚠️ Image error: {str(e)}")

async def error_handler(update, context):
    """Handle errors in the dispatcher."""
    error = context.error
    logger.error(f"Error occurred: {error}")
    
    if hasattr(update, 'effective_message') and update.effective_message:
        if 'Conflict' in str(error):
            await update.effective_message.reply_text("Bot is already running in another instance. Please try again later.")
        else:
            await update.effective_message.reply_text("An error occurred. Please try again later.")

def main() -> None:
    """Run the bot"""
    # Make sure directories exist
    os.makedirs("posters", exist_ok=True)
    os.makedirs("backdrops", exist_ok=True)
    
    # *** IMPORTANT: Replace this with your new bot token from BotFather ***
    BOT_TOKEN = "8068956847:AAGhaww4_8cLJune7Qsl615oEf5xvHky6XI"
    
    # Use a unique token identifier to prevent conflicts
    app = Application.builder() \
        .token(BOT_TOKEN) \
        .concurrent_updates(False) \
        .request(CustomHTTPXRequest()) \
        .build()

    # Force delete webhook and drop pending updates
    try:
        import asyncio
        loop = asyncio.get_event_loop()
        loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
        logger.info("Deleted webhook and dropped pending updates")
    except Exception as e:
        logger.error(f"Error deleting webhook: {e}")

    # Add subscription check handler
    app.add_handler(CallbackQueryHandler(check_subscription, pattern="^check_sub$"))

    # Main conversation flow
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_TYPE: [CallbackQueryHandler(select_type)],
            GET_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_name)],
            SELECT_RESULT: [CallbackQueryHandler(select_search_result, pattern="^(result_|cancel_search)")],
            GET_INSTAGRAM_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_instagram_url)],
        },
        fallbacks=[],
    )

    app.add_handler(conv_handler)
    
    # Add error handler
    app.add_error_handler(error_handler)
    
    logger.info("Starting bot with polling...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main() 