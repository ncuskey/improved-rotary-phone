#!/usr/bin/env python3
"""
Server Health Monitor with Auto-Restart

Continuously monitors the ISBN web server and automatically restarts it if it goes down.
"""

import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Configuration
SERVER_URL = "http://localhost:8000"
HEALTH_ENDPOINT = f"{SERVER_URL}/health"
CHECK_INTERVAL = 10  # seconds
MAX_FAILURES = 3  # restart after this many consecutive failures
SERVER_START_COMMAND = [
    sys.executable,
    "-m",
    "uvicorn",
    "isbn_web.main:app",
    "--host",
    "0.0.0.0",
    "--port",
    "8000",
    "--reload",
]

# State
server_process = None
consecutive_failures = 0
last_restart_time = None


def log(message: str, level: str = "INFO"):
    """Log a message with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    color_codes = {
        "INFO": "\033[0;32m",  # Green
        "WARNING": "\033[1;33m",  # Yellow
        "ERROR": "\033[0;31m",  # Red
        "SUCCESS": "\033[1;32m",  # Bright green
    }
    reset = "\033[0m"
    color = color_codes.get(level, "")
    print(f"{color}[{timestamp}] [{level}] {message}{reset}")


def check_server_health() -> bool:
    """Check if server is responding to health endpoint."""
    try:
        response = requests.get(HEALTH_ENDPOINT, timeout=5)
        return response.status_code == 200 and response.json().get("status") == "healthy"
    except Exception as e:
        log(f"Health check failed: {e}", "WARNING")
        return False


def start_server():
    """Start the server process."""
    global server_process, last_restart_time

    log("Starting server...", "INFO")

    # Change to project root
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    # Start server in background
    server_process = subprocess.Popen(
        SERVER_START_COMMAND,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    last_restart_time = datetime.now()
    log(f"Server started with PID {server_process.pid}", "SUCCESS")

    # Wait for server to be ready
    log("Waiting for server to be ready...", "INFO")
    for i in range(30):  # Wait up to 30 seconds
        time.sleep(1)
        if check_server_health():
            log("Server is healthy and responding!", "SUCCESS")
            return True

    log("Server started but not responding to health checks", "WARNING")
    return False


def stop_server():
    """Stop the server process."""
    global server_process

    if server_process and server_process.poll() is None:
        log(f"Stopping server (PID {server_process.pid})...", "INFO")
        server_process.terminate()
        try:
            server_process.wait(timeout=10)
            log("Server stopped gracefully", "INFO")
        except subprocess.TimeoutExpired:
            log("Server didn't stop gracefully, killing...", "WARNING")
            server_process.kill()
            server_process.wait()
            log("Server killed", "INFO")

    server_process = None


def restart_server():
    """Restart the server."""
    log("Restarting server...", "WARNING")
    stop_server()
    time.sleep(2)  # Brief pause before restart
    return start_server()


def monitor_loop():
    """Main monitoring loop."""
    global consecutive_failures

    log("=== ISBN Server Monitor Started ===", "SUCCESS")
    log(f"Monitoring: {HEALTH_ENDPOINT}", "INFO")
    log(f"Check interval: {CHECK_INTERVAL} seconds", "INFO")
    log(f"Auto-restart after {MAX_FAILURES} failures", "INFO")
    print()

    # Start server initially
    if not start_server():
        log("Failed to start server initially", "ERROR")
        sys.exit(1)

    print()
    log("=== Monitoring Active ===", "SUCCESS")
    print()

    try:
        while True:
            time.sleep(CHECK_INTERVAL)

            # Check health
            is_healthy = check_server_health()

            if is_healthy:
                if consecutive_failures > 0:
                    log("Server recovered!", "SUCCESS")
                consecutive_failures = 0
                log(f"✓ Server healthy", "INFO")
            else:
                consecutive_failures += 1
                log(
                    f"✗ Server unhealthy ({consecutive_failures}/{MAX_FAILURES})",
                    "ERROR"
                )

                if consecutive_failures >= MAX_FAILURES:
                    log(
                        f"Server failed {MAX_FAILURES} consecutive health checks - restarting",
                        "ERROR"
                    )
                    if restart_server():
                        consecutive_failures = 0
                    else:
                        log("Failed to restart server!", "ERROR")
                        time.sleep(30)  # Wait before trying again

    except KeyboardInterrupt:
        print()
        log("Monitor stopped by user", "INFO")
        stop_server()
        log("Shutdown complete", "SUCCESS")
        sys.exit(0)


if __name__ == "__main__":
    monitor_loop()
