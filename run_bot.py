import os
import sys
import subprocess
import signal
import time

def kill_existing_instances():
    """Kill any existing bot instances"""
    print("Checking for existing bot instances...")
    try:
        # List all Python processes
        process = subprocess.Popen(['ps', 'aux'], stdout=subprocess.PIPE)
        output, error = process.communicate()
        
        # Keep track of killed processes
        killed = False
        
        # Look for poster_bot processes
        for line in output.decode('utf-8').split('\n'):
            if 'poster_bot_v2.py' in line and 'run_bot.py' not in line:
                try:
                    pid = int(line.split()[1])
                    print(f"Killing process with PID {pid}")
                    os.kill(pid, signal.SIGTERM)
                    killed = True
                except Exception as e:
                    print(f"Error killing process: {e}")
        
        # If we killed any processes, wait a moment for them to terminate
        if killed:
            print("Waiting for processes to terminate...")
            time.sleep(2)
            
        return killed
    except Exception as e:
        print(f"Error checking for existing processes: {e}")
        return False

def run_bot():
    """Run the bot script"""
    print("Starting Telegram bot...")
    
    # Make sure we're in the right directory
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Kill any existing instances
    kill_existing_instances()
    
    # Run the bot with a clean environment
    env = os.environ.copy()
    
    # The bot script path
    bot_script = os.path.join(script_dir, "poster_bot_v2.py")
    
    print(f"Launching bot from: {bot_script}")
    
    # Run the bot and wait for it to complete
    try:
        process = subprocess.Popen([sys.executable, bot_script], env=env)
        print(f"Bot started with PID: {process.pid}")
        
        # Wait for the process to complete
        process.wait()
        
        print("Bot process has exited")
        return process.returncode
    except KeyboardInterrupt:
        print("Interrupted by user. Stopping bot...")
        return 1
    except Exception as e:
        print(f"Error running bot: {e}")
        return 1

if __name__ == "__main__":
    sys.exit(run_bot()) 