
import threading
import time
import requests
import os
import logging

logger = logging.getLogger(__name__)

def start_keep_alive():
    """
    Starts a background thread to ping the application every 14 minutes.
    Only runs if RENDER_EXTERNAL_URL environment variable is set.
    """
    url = os.environ.get('RENDER_EXTERNAL_URL')
    
    if not url:
        logger.info("Keep-alive disabled: RENDER_EXTERNAL_URL not set")
        return

    # Ensure URL ends with /api/health
    if not url.endswith('/api/health'):
        url = f"{url.rstrip('/')}/api/health"

    logger.info(f"KeepAlive initialized for URL: {url}")

    def ping():
        while True:
            try:
                response = requests.get(url, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Keep-alive ping successful: {response.status_code}")
                else:
                    logger.warning(f"Keep-alive ping failed: {response.status_code}")
            except Exception as e:
                logger.error(f"Keep-alive error: {str(e)}")
            
            # Sleep for 14 minutes (840 seconds)
            time.sleep(840)

    thread = threading.Thread(target=ping, daemon=True)
    thread.start()
