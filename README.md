# Poster-Downloader Bot

A Telegram bot that can download posters/backdrops from movies and TV shows, as well as download content from Instagram posts, reels, and profiles.

## Features

- Movie/TV Show poster and backdrop downloads
- Instagram content downloader
  - Posts
  - Reels
  - Profile pictures

## Deployment to Railway

### Prerequisites

1. A Railway account (https://railway.app/)
2. Git installed on your computer
3. Your Telegram Bot Token (from BotFather)

### Deployment Steps

1. Fork this repository to your GitHub account.

2. Log in to Railway and click "New Project" > "Deploy from GitHub repo"

3. Connect your GitHub account and select the forked repository.

4. Add the following environment variables in Railway dashboard:
   - `BOT_TOKEN`: Your Telegram bot token from BotFather
   - `WEB_APP_URL`: Your Railway app URL (you'll get this after first deploy)

5. After first deployment, go to Settings > Domains to get your app URL
   - Copy the URL
   - Go back to Variables and add it as `WEB_APP_URL`
   - Redeploy the project

6. Your bot should now be running on Railway!

## Local Development

To run the bot locally:

1. Clone the repository
2. Install the dependencies:
   ```
   pip install -r requirements.txt
   ```
3. Run the bot:
   ```
   python poster_bot_v2.py
   ```

## Notes

- The bot will automatically detect if it's running on Railway and use webhooks.
- For local development, it will use polling.
- All downloaded files are properly cleaned up after sending to keep storage usage low.