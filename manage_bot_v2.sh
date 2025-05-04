#!/bin/bash

# Script to manage the Poster Downloader Bot v2

VENV_PATH="/home/athithan1/prac/FileStoreLink/venv/bin/activate"
BOT_PATH="/home/athithan1/prac/Poster-Downloader/poster_bot_v2.py"
PID_FILE="/home/athithan1/prac/Poster-Downloader/bot_v2.pid"
LOG_FILE="/home/athithan1/prac/Poster-Downloader/bot_v2.log"

function start_bot() {
    echo "Starting Poster Downloader Bot v2..."
    source $VENV_PATH
    
    # Kill any existing instances of v2
    pkill -9 -f "python.*poster_bot_v2.py" 2>/dev/null
    
    # Start the bot in the background and save PID
    nohup python $BOT_PATH > $LOG_FILE 2>&1 &
    echo $! > $PID_FILE
    echo "Bot v2 started with PID $(cat $PID_FILE)"
}

function stop_bot() {
    echo "Stopping Poster Downloader Bot v2..."
    if [ -f "$PID_FILE" ]; then
        PID=$(cat $PID_FILE)
        if ps -p $PID > /dev/null; then
            kill -9 $PID
            echo "Bot v2 with PID $PID stopped"
        else
            echo "Bot v2 is not running with PID $PID"
        fi
        rm $PID_FILE
    else
        # Try to find and kill by name
        pkill -9 -f "python.*poster_bot_v2.py" 2>/dev/null
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
            echo "Bot v2 is running with PID $PID"
        else
            echo "Bot v2 is not running (stale PID file exists)"
        fi
    else
        echo "Bot v2 is not running (no PID file)"
    fi
}

function view_log() {
    if [ -f "$LOG_FILE" ]; then
        tail -n 50 $LOG_FILE
    else
        echo "No log file found"
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
    log)
        view_log
        ;;
    *)
        echo "Usage: $0 {start|stop|restart|status|log}"
        exit 1
        ;;
esac

exit 0 