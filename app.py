from flask import Flask, render_template, request, make_response
import os
import logging
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from ai_service import generate_content_with_ai, sanitize_input
from cache_service import get_cached_content, wait_for_preload, start_preloading

load_dotenv()

app = Flask(__name__)

# Configure logging - hide noisy logs
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Hide httpx logs
logging.getLogger("httpx").setLevel(logging.WARNING)

# Rate limiting
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per day", "50 per hour"]
)

# Custom error handler for rate limit exceeded
@app.errorhandler(429)
def ratelimit_handler(e):
    logger.warning(f"Rate limit exceeded for IP: {get_remote_address()}")
    return render_template('index.html', 
                         content="<h1>Service Temporarily Unavailable</h1><p>Our website is currently overloaded with requests. Please try again in a few minutes.</p><p>We appreciate your patience!</p>"), 429

@app.route('/favicon.ico')
def favicon():
    return '', 204  # No content

@app.route('/')
def home():
    # Check for query parameters and sanitize them
    query_param = request.args.get('query') or request.args.get('prompt') or ''
    for key, value in request.args.items():
        if key not in ['query', 'prompt'] and value:
            query_param = value
            break
    if not query_param:
        query_param = next(iter(request.args.keys()), '') if request.args else ''
    
    # Sanitize the query parameter
    query_param = sanitize_input(query_param)
    
    path_display = f"/?{query_param}" if query_param else "/"
    # Get the real IP from headers - try multiple methods
    real_ip = None
    if 'CF-Connecting-IP' in request.headers:
        real_ip = request.headers['CF-Connecting-IP']
    elif 'X-Forwarded-For' in request.headers:
        # Get the last IP in the chain (original client)
        ips = request.headers['X-Forwarded-For'].split(',')
        real_ip = ips[-1].strip()
    elif 'X-Real-IP' in request.headers:
        real_ip = request.headers['X-Real-IP']
    else:
        real_ip = get_remote_address()
    logger.info(f"Home route accessed: {path_display} from IP: {real_ip}")
    
    # HOME should never be cached - always generate fresh content
    if not query_param:
        logger.info(f"GENERATING: HOME")
        content = generate_content_with_ai(query_param)
    else:
        # Use query_param as cache key for non-home paths
        cache_key = query_param
        
        # Try to get cached content first
        cached_content = get_cached_content(cache_key)
        
        if cached_content:
            logger.info(f"CACHED: {query_param}")
            content = cached_content
        else:
            # Check if currently being preloaded
            preload_content = wait_for_preload(cache_key)
            if preload_content:
                logger.info(f"PRELOAD READY: {query_param}")
                content = preload_content
            else:
                logger.info(f"GENERATING: {query_param}")
                content = generate_content_with_ai(query_param)
    
    # Start preloading linked content in background if enabled
    start_preloading(content, query_param)
    
    # Check if content is a complete HTML document
    if content.strip().startswith('<!DOCTYPE html') or content.strip().startswith('<html'):
        # Return complete HTML document directly
        response = make_response(content)
    else:
        # Wrap fragment in template
        response = make_response(render_template('index.html', content=content))
    
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/<path:path_info>')
def dynamic_page(path_info):
    # Sanitize path_info immediately
    path_info = sanitize_input(path_info)
    
    # Enforce maximum depth of 4 levels - redirect to simpler path if exceeded
    path_levels = path_info.count('/') + 1
    if path_levels > 4:
        logger.warning(f"Path too deep ({path_levels} levels): {path_info}")
        # Take only the last segment as a simple redirect
        simple_path = path_info.split('/')[-1]
        return f"<h1>Path Too Deep</h1><p>Redirecting to: <a href='/{simple_path}'>{simple_path}</a></p><script>setTimeout(() => window.location.href='/{simple_path}', 2000);</script>"
    # Get the real IP from headers - try multiple methods
    real_ip = None
    if 'CF-Connecting-IP' in request.headers:
        real_ip = request.headers['CF-Connecting-IP']
    elif 'X-Forwarded-For' in request.headers:
        # Get the last IP in the chain (original client)
        ips = request.headers['X-Forwarded-For'].split(',')
        real_ip = ips[-1].strip()
    elif 'X-Real-IP' in request.headers:
        real_ip = request.headers['X-Real-IP']
    else:
        real_ip = get_remote_address()
    logger.info(f"Dynamic page accessed: /{path_info} from IP: {real_ip}")
    
    # Check if this is a subpage and provide context
    path_parts = path_info.split('/')
    if len(path_parts) > 1:
        parent_topic = path_parts[0]
        subpage = '/'.join(path_parts[1:])
        context_prompt = f"This is a subpage '{subpage}' under the main topic '{parent_topic}'. Create content specifically for this subpage while relating it back to {parent_topic}."
        full_path_info = f"{path_info} ({context_prompt})"
    else:
        full_path_info = path_info
    
    # Try to get cached content first
    cached_content = get_cached_content(path_info)
    
    if cached_content:
        logger.info(f"CACHED: {path_info}")
        content = cached_content
    else:
        # Check if currently being preloaded, but don't wait too long
        preload_content = wait_for_preload(path_info, max_wait=5)  # Only wait 5 seconds
        if preload_content:
            logger.info(f"PRELOAD READY: {path_info}")
            content = preload_content
        else:
            logger.info(f"GENERATING: {path_info}")
            content = generate_content_with_ai(full_path_info)
    
    # Start preloading linked content in background if enabled
    start_preloading(content, path_info)
    
    # Check if content is a complete HTML document
    if content.strip().startswith('<!DOCTYPE html') or content.strip().startswith('<html'):
        # Return complete HTML document directly
        response = make_response(content)
    else:
        # Wrap fragment in template
        response = make_response(render_template('index.html', content=content))
    
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)