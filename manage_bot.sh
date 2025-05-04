#!/bin/bash

# Script to manage the Poster Downloader Bot

VENV_PATH="/home/athithan1/prac/FileStoreLink/venv/bin/activate"
BOT_PATH="/home/athithan1/prac/Poster-Downloader/poster_bot.py"
PID_FILE="/home/athithan1/prac/Poster-Downloader/bot.pid"

function start_bot() {
    echo "Starting Poster Downloader Bot..."
    source $VENV_PATH
    # Kill any existing instances
    pkill -9 -f "python.*poster_bot.py" 2>/dev/null
    
    # Start the bot in the background and save PID
    nohup python $BOT_PATH > bot.log 2>&1 &
    echo $! > $PID_FILE
    echo "Bot started with PID $(cat $PID_FILE)"
}

function stop_bot() {
    echo "Stopping Poster Downloader Bot..."
    if [ -f "$PID_FILE" ]; then
        PID=$(cat $PID_FILE)
        if ps -p $PID > /dev/null; then
            kill -9 $PID
            echo "Bot with PID $PID stopped"
        else
            echo "Bot is not running with PID $PID"
        fi
        rm $PID_FILE
    else
        # Try to find and kill by name
        pkill -9 -f "python.*poster_bot.py" 2>/dev/null
        echo "Attempted to stop bot by name"
    fi
}

function restart_bot() {
    stop_bot
    sleep 2
    start_bot
}

function status_bot() {
    if [ -f "$PID_FILE" ]; then
        PID=$(cat $PID_FILE)
        if ps -p $PID > /dev/null; then
            echo "Bot is running with PID $PID"
        else
            echo "Bot is not running (stale PID file exists)"
        fi
    else
        echo "Bot is not running (no PID file)"
    fi
}

case "$1" in
    start)
        start_bot
        ;;
    stop)
        stop_bot
        ;;
    restart)
        restart_bot
        ;;
    status)
        status_bot
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac

exit 0 