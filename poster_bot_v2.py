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
    PicklePersistence,
)
from telegram.request import HTTPXRequest
import httpx
import logging
import instaloader
from datetime import datetime
import re
import signal
import subprocess
import sys
import asyncio

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

# Railway specific configuration for deployment 
PORT = int(os.environ.get('PORT', 8443))
WEB_APP_URL = os.environ.get('WEB_APP_URL', None)

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
        try:
            # Try to edit caption if it's a photo message
            await query.edit_message_caption(
                caption="📷 Instagram Downloader\n\n"
                "Send me an Instagram post, reel, or profile URL to download content."
            )
        except Exception:
            # If it's a text message, edit the text instead
            try:
                await query.edit_message_text(
                    "📷 Instagram Downloader\n\n"
                    "Send me an Instagram post, reel, or profile URL to download content."
                )
            except Exception as e:
                # If both fail, send a new message
                logger.error(f"Edit message error: {e}")
                await query.message.reply_text(
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
    logger.info(f"Received potential Instagram URL: {url}")
    
    # Check if user wants to cancel
    if url.lower() in ['/start', '/cancel', 'cancel']:
        await update.message.reply_text("Operation cancelled. Press /start to begin again.")
        return ConversationHandler.END
    
    # Check if this is a valid Instagram URL
    if not is_valid_instagram_url(url):
        await update.message.reply_text(
            "❌ This doesn't look like a valid Instagram URL.\n\n"
            "Please send a URL like:\n"
            "• https://www.instagram.com/p/Abc123/\n"
            "• https://www.instagram.com/reel/Xyz789/\n"
            "• https://www.instagram.com/username\n\n"
            "Or type 'cancel' to go back to the main menu."
        )
        return GET_INSTAGRAM_URL
    
    processing_message = await update.message.reply_text(
        "⏳ Processing Instagram content...\n"
        "This may take a moment depending on the content size."
    )
    
    try:
        # Download Instagram content
        result = await download_from_instagram(url, update, context)
        if result:
            await update.message.reply_text(
                "✅ Download completed successfully!\n\n"
                "Press /start to download more content."
            )
        else:
            await update.message.reply_text(
                "❌ Failed to download content.\n\n"
                "This might be a private profile or the content may no longer be available.\n"
                "Try another URL or press /start to go back to the main menu."
            )
    except Exception as e:
        error_message = str(e)
        logger.error(f"Instagram download error: {error_message}")
        
        # Determine the type of error for better user guidance
        if "login_required" in error_message.lower():
            await update.message.reply_text(
                "❌ This content is from a private account and requires login.\n\n"
                "Try downloading content from public accounts instead."
            )
        elif "not found" in error_message.lower():
            await update.message.reply_text(
                "❌ Content not found.\n\n"
                "The post may have been deleted or the URL is incorrect."
            )
        elif "429" in error_message or "too many" in error_message.lower():
            await update.message.reply_text(
                "❌ Instagram is rate limiting our requests.\n\n"
                "Please try again later when the rate limit resets."
            )
        else:
            await update.message.reply_text(
                f"❌ Error downloading content: {error_message[:100]}...\n\n"
                "Please try again with a different link or later."
            )
    
    return ConversationHandler.END

def is_valid_instagram_url(url):
    """Check if a URL is a valid Instagram URL"""
    instagram_regex = r'(https?:\/\/)?(www\.)?(instagram\.com|instagr\.am)\/([a-zA-Z0-9_\.]+(\/)?|p\/[a-zA-Z0-9_-]+\/?|reel\/[a-zA-Z0-9_-]+\/?)'
    return re.match(instagram_regex, url) is not None

async def download_from_instagram(url, update, context):
    """Download content from Instagram"""
    logger.info(f"Attempting to download from Instagram: {url}")
    
    # Normalize URL
    if "instagram.com" not in url and "instagr.am" not in url:
        # Try to fix URL if user just sent a username or shortcode
        if url.startswith('@'):
            url = f"https://www.instagram.com/{url[1:]}/"
        elif url.strip().isalnum():
            # Assume it's a shortcode if it's just alphanumeric
            url = f"https://www.instagram.com/p/{url}/"
        else:
            url = f"https://www.instagram.com/{url}/"
    
    # Ensure URL has https:// prefix
    if not url.startswith('http'):
        url = 'https://' + url
    
    logger.info(f"Normalized URL: {url}")
    await update.message.reply_text(f"Processing: {url}")
    
    # Modified instaloader setup with more robust settings
    L = instaloader.Instaloader(
        download_videos=True,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        max_connection_attempts=5,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36",
        request_timeout=60
    )
    
    # Create temp directory for downloads
    temp_dir = tempfile.mkdtemp()
    temp_files = []  # Track all files we create for cleanup
    logger.info(f"Created temp directory: {temp_dir}")
    
    try:
        # Attempt to download the content directly without instaloader first
        try:
            # If it's a post or reel, try a more direct approach first
            if '/p/' in url or '/reel/' in url:
                direct_url = None
                direct_caption = None
                
                # Make a direct request to get the OG meta tags
                try:
                    logger.info("Attempting direct method with OG meta tags")
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Cache-Control': 'max-age=0'
                    }
                    response = requests.get(url, headers=headers, timeout=30)
                    
                    # Check if we got a proper response
                    if response.status_code != 200:
                        logger.error(f"Direct method failed with status code: {response.status_code}")
                        await update.message.reply_text(f"Got status code {response.status_code} when accessing Instagram. Trying alternative method...")
                    else:
                        # Extract the image/video URL from OG meta tags
                        if 'og:image' in response.text:
                            match = re.search(r'<meta property="og:image" content="([^"]+)"', response.text)
                            if match:
                                direct_url = match.group(1)
                                logger.info(f"Found direct image URL: {direct_url}")
                        
                        # Try to get video URL if it's a video
                        if 'og:video' in response.text:
                            match = re.search(r'<meta property="og:video" content="([^"]+)"', response.text)
                            if match:
                                direct_url = match.group(1)
                                logger.info(f"Found direct video URL: {direct_url}")
                        
                        # Get the caption/title
                        if 'og:title' in response.text:
                            match = re.search(r'<meta property="og:title" content="([^"]+)"', response.text)
                            if match:
                                direct_caption = match.group(1)
                        
                        # If we found a direct URL, download and send it
                        if direct_url:
                            await update.message.reply_text(f"Found content directly! Downloading now...")
                            
                            file_path = os.path.join(temp_dir, "instagram_content")
                            # Add extension based on content type
                            if direct_url.endswith('.mp4'):
                                file_path += '.mp4'
                            else:
                                file_path += '.jpg'
                            
                            # Download the content
                            with open(file_path, "wb") as f:
                                media_response = requests.get(direct_url, headers=headers, timeout=30)
                                f.write(media_response.content)
                            
                            # Modified video sending code to ensure file cleanup
                            if file_path.endswith('.mp4'):
                                try:
                                    with open(file_path, 'rb') as video_file:
                                        await update.message.reply_video(
                                            video=video_file,
                                            caption=f"🎥 Instagram Video\nCaption: {direct_caption[:100] if direct_caption else 'No caption'}"
                                        )
                                    # Clean up immediately after sending
                                    if os.path.exists(file_path):
                                        os.unlink(file_path)
                                        logger.info(f"Deleted temp file: {file_path}")
                                    return True
                                except Exception as e:
                                    logger.error(f"Error sending video: {e}")
                                    # Try as document
                                    try:
                                        with open(file_path, 'rb') as doc_file:
                                            await update.message.reply_document(
                                                document=doc_file,
                                                caption=f"🎥 Instagram Video (as document)\nCaption: {direct_caption[:100] if direct_caption else 'No caption'}"
                                            )
                                        # Clean up immediately after sending
                                        if os.path.exists(file_path):
                                            os.unlink(file_path)
                                            logger.info(f"Deleted temp file: {file_path}")
                                        return True
                                    except Exception as doc_e:
                                        logger.error(f"Error sending document: {doc_e}")
                                        return False
                            else:
                                await update.message.reply_photo(
                                    photo=open(file_path, 'rb'),
                                    caption=f"📸 Instagram Photo\nCaption: {direct_caption[:100] if direct_caption else 'No caption'}"
                                )
                                # Clean up immediately after sending
                                if os.path.exists(file_path):
                                    os.unlink(file_path)
                                    logger.info(f"Deleted temp file: {file_path}")
                                return True
                except Exception as direct_e:
                    logger.error(f"Error with direct download approach: {direct_e}")
                    await update.message.reply_text("Direct download failed, trying alternative method...")
        
        except Exception as pre_e:
            logger.error(f"Error in preliminary download attempt: {pre_e}")
        
        # If direct download failed, try with instaloader
        try:
            # Extract shortcode from URL
            if '/p/' in url or '/reel/' in url:
                logger.info("Detected post or reel URL")
                if '/p/' in url:
                    shortcode = url.split('/p/')[-1].split('/')[0]
                else:
                    shortcode = url.split('/reel/')[-1].split('/')[0]
                
                shortcode = shortcode.split('?')[0]  # Remove query parameters
                logger.info(f"Extracted shortcode: {shortcode}")
                
                # Download post
                try:
                    await update.message.reply_text(f"Fetching content for shortcode: {shortcode}")
                    
                    # Try to get post without login
                    try:
                        post = instaloader.Post.from_shortcode(L.context, shortcode)
                        logger.info(f"Found post by user: {post.owner_username}")
                        
                        await update.message.reply_text(f"Downloading content from @{post.owner_username}...")
                        
                        # Check if post is from private account
                        if post.owner_profile.is_private:
                            logger.warning(f"Post {shortcode} is from private account: {post.owner_username}")
                            await update.message.reply_text(
                                f"⚠️ Note: The post is from a private account (@{post.owner_username}).\n"
                                "But we'll try to download it anyway since we found it..."
                            )
                        
                        # Download only the media files
                        try:
                            # First try a simpler approach - just get the image URL
                            if post.is_video:
                                video_url = post.video_url
                                logger.info(f"Direct video URL: {video_url}")
                                video_path = os.path.join(temp_dir, f"{shortcode}.mp4")
                                
                                # Download video
                                with open(video_path, "wb") as f:
                                    f.write(requests.get(video_url).content)
                                
                                temp_files.append(video_path)
                                
                                try:
                                    with open(video_path, 'rb') as video_file:
                                        await update.message.reply_video(
                                            video=video_file,
                                            caption=f"🎥 Instagram Video\nFrom: {post.owner_username}"
                                        )
                                    return True
                                except Exception as e:
                                    logger.error(f"Error sending video: {e}")
                                    with open(video_path, 'rb') as doc_file:
                                        await update.message.reply_document(
                                            document=doc_file,
                                            caption=f"🎥 Instagram Video (as document)\nFrom: {post.owner_username}"
                                        )
                                    return True
                            else:
                                # It's a photo post
                                photo_url = post.url
                                logger.info(f"Direct photo URL: {photo_url}")
                                photo_path = os.path.join(temp_dir, f"{shortcode}.jpg")
                                
                                # Download photo
                                with open(photo_path, "wb") as f:
                                    f.write(requests.get(photo_url).content)
                                
                                temp_files.append(photo_path)
                                
                                await update.message.reply_photo(
                                    photo=open(photo_path, 'rb'),
                                    caption=f"📸 Instagram Photo\nFrom: {post.owner_username}"
                                )
                                return True
                        
                        except Exception as direct_dl_e:
                            logger.error(f"Error with direct download: {direct_dl_e}")
                            # Fall back to regular download
                            L.download_post(post, target=temp_dir)
                        
                    except Exception as post_e:
                        logger.error(f"Error getting post: {post_e}")
                        await update.message.reply_text(f"Error: {str(post_e)[:100]}")
                        return False
                    
                    # List downloaded files for debugging
                    files = os.listdir(temp_dir)
                    logger.info(f"Downloaded files: {files}")
                    
                    if not files:
                        await update.message.reply_text("No files were downloaded. Instagram may be blocking the request.")
                        return False
                    
                    # Send media files
                    media_sent = False
                    for filename in files:
                        filepath = os.path.join(temp_dir, filename)
                        logger.info(f"Processing file: {filename}")
                        
                        if filename.endswith('.jpg') and not filename.endswith('_profile_pic.jpg'):
                            # It's a photo
                            logger.info("Sending photo to user")
                            await update.message.reply_photo(
                                photo=open(filepath, 'rb'),
                                caption=f"📸 Instagram Photo\nFrom: {post.owner_username}"
                            )
                            media_sent = True
                        elif filename.endswith('.mp4'):
                            # It's a video
                            logger.info("Sending video to user")
                            try:
                                await update.message.reply_text("Uploading video... Please wait.")
                                await update.message.reply_video(
                                    video=open(filepath, 'rb'),
                                    caption=f"🎥 Instagram Video\nFrom: {post.owner_username}"
                                )
                                media_sent = True
                            except Exception as e:
                                logger.error(f"Error sending video: {e}")
                                await update.message.reply_text(f"Error sending video: {str(e)[:100]}...")
                                # Try to send as document if video fails
                                try:
                                    await update.message.reply_document(
                                        document=open(filepath, 'rb'),
                                        caption=f"🎥 Instagram Video (as document)\nFrom: {post.owner_username}"
                                    )
                                    media_sent = True
                                except Exception as doc_e:
                                    logger.error(f"Error sending document: {doc_e}")
                    
                    return media_sent
                except Exception as e:
                    logger.error(f"Error downloading post: {e}")
                    await update.message.reply_text(f"Error downloading post: {str(e)[:100]}...")
                    return False
            
            # Handle profile URLs
            elif re.search(r'instagram\.com/([a-zA-Z0-9_\.]+)/?$', url):
                username = url.split('instagram.com/')[-1].strip('/')
                logger.info(f"Detected profile URL for user: {username}")
                
                # Try a more direct approach for profile pictures
                try:
                    # Try to get profile picture directly from HTML
                    headers = {
                        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.5',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1',
                        'Cache-Control': 'max-age=0'
                    }
                    response = requests.get(f"https://www.instagram.com/{username}/", headers=headers, timeout=30)
                    
                    if response.status_code != 200:
                        logger.error(f"Direct profile method failed with status code: {response.status_code}")
                        await update.message.reply_text(f"Got status code {response.status_code} when accessing profile. Trying alternative method...")
                    else:
                        # Check if profile is actually private
                        is_private = '"is_private":true' in response.text
                        if is_private:
                            logger.warning(f"Profile @{username} is private according to page HTML")
                            await update.message.reply_text(
                                f"⚠️ The profile @{username} appears to be private.\n"
                                "I'll try to get the profile picture anyway..."
                            )
                        
                        # Extract profile pic URL 
                        profile_pic_match = re.search(r'\"profile_pic_url_hd\":\"([^\"]+)\"', response.text)
                        if profile_pic_match:
                            profile_pic_url = profile_pic_match.group(1).replace('\\u0026', '&')
                            
                            # Download the profile pic
                            pic_path = os.path.join(temp_dir, f"{username}_profile.jpg")
                            with open(pic_path, "wb") as f:
                                pic_response = requests.get(profile_pic_url, headers=headers, timeout=30)
                                f.write(pic_response.content)
                            
                            temp_files.append(pic_path)
                            
                            # Extract some profile info if available
                            full_name = username
                            bio = "No bio available"
                            
                            name_match = re.search(r'\"full_name\":\"([^\"]+)\"', response.text)
                            if name_match:
                                full_name = name_match.group(1)
                            
                            bio_match = re.search(r'\"biography\":\"([^\"]+)\"', response.text)
                            if bio_match:
                                bio = bio_match.group(1).replace('\\n', '\n')
                            
                            await update.message.reply_photo(
                                photo=open(pic_path, 'rb'),
                                caption=f"👤 Profile Picture of @{username}\n"
                                       f"Full name: {full_name}\n"
                                       f"Bio: {bio[:100]}..."
                            )
                            return True
                        else:
                            # If we can't find the profile pic but got a 200 response
                            if "Page Not Found" in response.text or "Sorry, this page isn't available" in response.text:
                                logger.error(f"Profile @{username} doesn't exist")
                                await update.message.reply_text(f"⚠️ The profile @{username} doesn't seem to exist.")
                            else:
                                logger.error("Couldn't extract profile picture URL from page")
                                await update.message.reply_text("Couldn't find the profile picture URL. Trying alternative method...")
                
                except Exception as direct_profile_e:
                    logger.error(f"Direct profile pic download failed: {direct_profile_e}")
                
                # Fall back to instaloader method
                try:
                    await update.message.reply_text(f"Fetching profile information for: @{username}")
                    
                    try:
                        profile = instaloader.Profile.from_username(L.context, username)
                        
                        logger.info(f"Found profile: {profile.full_name}")
                        logger.info(f"Profile is private: {profile.is_private}")
                        
                        if profile.is_private:
                            await update.message.reply_text(
                                f"⚠️ The profile @{username} is private.\n"
                                "I can only download the profile picture."
                            )
                        
                        await update.message.reply_text(f"Downloading profile picture for: @{username}")
                        
                        # Try direct download of profile pic if it's available
                        profile_pic_url = profile.profile_pic_url
                        logger.info(f"Profile pic URL: {profile_pic_url}")
                        
                        if profile_pic_url:
                            # Download directly
                            pic_path = os.path.join(temp_dir, f"{username}_profile.jpg")
                            with open(pic_path, "wb") as f:
                                pic_response = requests.get(profile_pic_url, headers={
                                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'
                                }, timeout=30)
                                f.write(pic_response.content)
                            
                            temp_files.append(pic_path)
                            
                            await update.message.reply_photo(
                                photo=open(pic_path, 'rb'),
                                caption=f"👤 Profile Picture of @{username}\n"
                                       f"Full name: {profile.full_name}\n"
                                       f"Bio: {profile.biography[:100] if profile.biography else 'No bio available'}..."
                            )
                            return True
                        else:
                            # Fall back to downloading via instaloader
                            L.download_profilepic(profile)
                            logger.info("Downloaded profile picture")
                            
                            # Find the profile pic
                            profile_pic_found = False
                            for filename in os.listdir('.'):
                                if username in filename and filename.endswith('.jpg'):
                                    logger.info(f"Found profile picture: {filename}")
                                    await update.message.reply_photo(
                                        photo=open(filename, 'rb'),
                                        caption=f"👤 Profile Picture of @{username}\n"
                                               f"Full name: {profile.full_name}\n"
                                               f"Bio: {profile.biography[:100] if profile.biography else 'No bio available'}..."
                                    )
                                    os.remove(filename)  # Clean up
                                    profile_pic_found = True
                            
                            if not profile_pic_found:
                                logger.error("Profile picture file not found after download")
                                await update.message.reply_text("Could not find the downloaded profile picture file.")
                            
                            return profile_pic_found
                    
                    except instaloader.exceptions.ProfileNotExistsException:
                        logger.error(f"Profile @{username} does not exist")
                        await update.message.reply_text(f"❌ The profile @{username} does not exist.")
                        return False
                    except instaloader.exceptions.LoginRequiredException:
                        logger.error(f"Login required to access profile @{username}")
                        await update.message.reply_text(
                            f"❌ This profile (@{username}) is private and requires login to access.\n"
                            "Try downloading content from public accounts instead."
                        )
                        return False
                    except instaloader.exceptions.ConnectionException as ce:
                        logger.error(f"Connection error when accessing profile @{username}: {ce}")
                        await update.message.reply_text(
                            f"❌ Connection error when accessing @{username}.\n"
                            "Instagram may be rate limiting our requests. Please try again later."
                        )
                        return False
                    
                except Exception as e:
                    logger.error(f"Error downloading profile: {e}")
                    
                    # Give more specific error message based on error text
                    error_text = str(e).lower()
                    if "too many requests" in error_text or "429" in error_text:
                        await update.message.reply_text(
                            f"❌ Instagram is rate limiting our requests.\n"
                            "Please try again later when the rate limit resets."
                        )
                    elif "private profile" in error_text:
                        await update.message.reply_text(
                            f"❌ The profile @{username} is private.\n"
                            "I cannot access its content without authentication."
                        )
                    else:
                        await update.message.reply_text(f"Error downloading profile: {str(e)[:100]}...")
                    return False
            else:
                logger.error(f"URL not recognized as post, reel, or profile: {url}")
                await update.message.reply_text("URL format not recognized. Please make sure it's a valid Instagram post, reel, or profile URL.")
                return False
        
        except Exception as e:
            logger.error(f"Error in Instagram download: {e}")
            
            # Give more specific error message based on error text
            error_text = str(e).lower()
            if "login_required" in error_text:
                await update.message.reply_text(
                    "❌ Instagram requires login to access this content.\n"
                    "This usually happens with private profiles or when Instagram restricts content."
                )
            elif "not found" in error_text or "404" in error_text:
                await update.message.reply_text(
                    "❌ Content not found.\n"
                    "The post may have been deleted or the URL is incorrect."
                )
            elif "too many requests" in error_text or "429" in error_text:
                await update.message.reply_text(
                    "❌ Instagram is rate limiting our requests.\n"
                    "Please try again later when the rate limit resets."
                )
            else:
                await update.message.reply_text(f"Error downloading from Instagram: {str(e)[:100]}...")
            return False
    finally:
        # Clean up temp directory and any tracked files
        try:
            for f in temp_files:
                if os.path.exists(f):
                    os.unlink(f)
                    logger.info(f"Cleaned up temp file: {f}")
            
            # Then clean up directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temp directory: {temp_dir}")
        except Exception as e:
            logger.error(f"Error cleaning up temporary files: {e}")

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
    
    # Force kill any other Python processes that might be using this bot token
    try:
        my_pid = os.getpid()
        
        # Find and kill other bot instances
        process = subprocess.Popen(['ps', 'aux'], stdout=subprocess.PIPE)
        output, error = process.communicate()
        
        for line in output.decode('utf-8').split('\n'):
            if 'poster_bot' in line and str(my_pid) not in line:
                try:
                    pid = int(line.split()[1])
                    os.kill(pid, signal.SIGKILL)
                    print(f"Killed conflicting process with PID {pid}")
                except:
                    pass
    except:
        pass
    
    # *** IMPORTANT: Replace this with your new bot token from BotFather ***
    BOT_TOKEN = "8068956847:AAGhaww4_8cLJune7Qsl615oEf5xvHky6XI"
    
    # Use a unique session name to prevent conflicts
    persistence = PicklePersistence(filepath="bot_data_v2.pickle")
    
    # Use a unique token identifier to prevent conflicts
    app = Application.builder() \
        .token(BOT_TOKEN) \
        .persistence(persistence) \
        .concurrent_updates(False) \
        .request(CustomHTTPXRequest()) \
        .build()

    # Force delete webhook and drop pending updates
    try:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
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
    
    # Check if we're on Railway by looking for the PORT environment variable
    if WEB_APP_URL:
        # Use webhook mode for Railway
        logger.info(f"Starting bot with webhook at {WEB_APP_URL}")
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=BOT_TOKEN,
            webhook_url=f"{WEB_APP_URL}/{BOT_TOKEN}"
        )
    else:
        # Use polling mode for local development
        logger.info("Starting bot with polling...")
        app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main() 