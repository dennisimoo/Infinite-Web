import os
import time
import threading
import logging
from dotenv import load_dotenv
from ai_service import generate_content_with_ai, extract_navigation_links

load_dotenv()

logger = logging.getLogger(__name__)

PRELOAD_ENABLED = os.getenv('PRELOAD', 'False').lower() == 'true'

# Global cache for preloaded content
content_cache = {}
cache_lock = threading.Lock()
# Track ongoing preload requests
preload_status = {}  # path -> 'generating' | 'completed'

def preload_content_async(path_info, depth=0):
    """Generate content in background thread"""
    # Prevent infinite recursion and bad paths
    if depth > 0 or not path_info or 'favicon' in path_info or path_info.startswith('.'):
        return
    
    # Check if already preloading or cached
    with cache_lock:
        if path_info in preload_status:
            logger.info(f"ALREADY PRELOADING: {path_info}")
            return
        if path_info in content_cache:
            logger.info(f"SKIP PRELOAD - CACHED: {path_info}")
            return
        preload_status[path_info] = 'generating'
        
    def generate():
        try:
            content = generate_content_with_ai(path_info)
            
            with cache_lock:
                content_cache[path_info] = {
                    'content': content,
                    'timestamp': time.time(),
                    'expires_at': time.time() + 3600  # Cache for 1 hour
                }
                preload_status[path_info] = 'completed'
                logger.info(f"PRELOAD COMPLETED AND CACHED: {path_info}")
                        
        except Exception as e:
            logger.error(f"PRELOAD FAILED: {path_info}")
            with cache_lock:
                if path_info in preload_status:
                    del preload_status[path_info]
    
    threading.Thread(target=generate, daemon=True).start()

def get_cached_content(path_info):
    """Get content from cache if available and not expired"""
    with cache_lock:
        if path_info in content_cache:
            cache_entry = content_cache[path_info]
            if time.time() < cache_entry['expires_at']:
                return cache_entry['content']
            else:
                # Remove expired content
                del content_cache[path_info]
                if path_info in preload_status:
                    del preload_status[path_info]
    return None

def wait_for_preload(path_info, max_wait=5):
    """Wait for ongoing preload to complete"""
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        with cache_lock:
            if path_info not in preload_status:
                # Not being preloaded
                return None
            
            current_status = preload_status[path_info]
            
            if current_status == 'completed':
                # Preload completed, try to get cached content
                cached_content = get_cached_content(path_info)
                if cached_content:
                    return cached_content
        
        time.sleep(0.1)  # Wait 100ms before checking again
    
    # Timeout - clean up and give up
    logger.warning(f"TIMEOUT waiting for preload: {path_info}")
    with cache_lock:
        if path_info in preload_status:
            del preload_status[path_info]
    return None

def start_preloading(content, current_path=""):
    """Start preloading linked content in background if enabled"""
    if PRELOAD_ENABLED and content:
        links = extract_navigation_links(content, current_path)
        if links:
            logger.info(f"FOUND LINKS in {current_path or 'HOME'}: {', '.join(links)}")
            for link in links:
                if get_cached_content(link) is None:  # Only preload if not already cached
                    logger.info(f"PRELOADING: {link}")
                    preload_content_async(link, depth=0)
                else:
                    logger.info(f"ALREADY CACHED: {link}")