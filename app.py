from flask import Flask, render_template, request, make_response
import requests
import os
import re
import logging
import httpx
import bleach
import threading
import time
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

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

# Check which API key is available
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
PRELOAD_ENABLED = os.getenv('PRELOAD', 'False').lower() == 'true'

# Global cache for preloaded content
content_cache = {}
cache_lock = threading.Lock()
# Track ongoing preload requests
preload_status = {}  # path -> 'generating' | 'completed'

if OPENROUTER_API_KEY:
    import openai
    import httpx
    openrouter_client = openai.OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY,
        http_client=httpx.Client()
    )
    API_TYPE = 'openrouter'
    print("Using Gemini 2.5 Flash via OpenRouter")
elif OPENAI_API_KEY:
    import openai
    openai.api_key = OPENAI_API_KEY
    API_TYPE = 'openai'
    print("Using OpenAI GPT-4o-mini")
elif GEMINI_API_KEY:
    API_TYPE = 'gemini'
    API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent'
    print("Using Gemini 2.5 Flash")
else:
    raise ValueError("No API key found. Please set either OPENROUTER_API_KEY, OPENAI_API_KEY, or GEMINI_API_KEY in your .env file")

def extract_navigation_links(content):
    """Extract navigation links from generated content"""
    links = []
    # Look for links in the format href="./path"
    link_patterns = [
        r'href=["\']\./(.*?)["\']',
    ]
    
    for pattern in link_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            if match and match not in links and not match.startswith('http') and 'favicon' not in match:
                # Clean up the link
                clean_link = match.strip('/')
                if clean_link and len(clean_link) < 100 and '.' not in clean_link:  # No file extensions
                    links.append(clean_link)
    
    return list(set(links))[:5]  # Limit to 5 links to avoid overload

def preload_content_async(path_info, depth=0):
    """Generate content in background thread"""
    # Prevent infinite recursion and bad paths
    if depth > 0 or not path_info or 'favicon' in path_info or path_info.startswith('.'):
        return
    
    # Check if already preloading or cached
    with cache_lock:
        if path_info in preload_status or path_info in content_cache:
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

def wait_for_preload(path_info, max_wait=10):
    """Wait for ongoing preload to complete"""
    start_time = time.time()
    
    while time.time() - start_time < max_wait:
        with cache_lock:
            if path_info not in preload_status:
                # Not being preloaded
                return None
            if preload_status[path_info] == 'completed':
                # Preload completed, try to get cached content
                return get_cached_content(path_info)
        
        logger.info(f"WAITING for preload: {path_info}")
        time.sleep(0.5)  # Wait 500ms before checking again
    
    logger.info(f"TIMEOUT waiting for preload: {path_info}")
    return None

def sanitize_input(text):
    """Sanitize user input to prevent XSS attacks"""
    if not text:
        return ""
    # Remove any potentially dangerous characters and HTML tags
    cleaned = bleach.clean(text, tags=[], attributes={}, strip=True)
    # Additional safety: remove any remaining script-like content
    cleaned = re.sub(r'<script[^>]*>.*?</script>', '', cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r'javascript:', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()

def generate_content_with_ai(path_info):
    if path_info and path_info.strip('/'):
        prompt = f"Create a focused HTML webpage about '{path_info}'. Focus on ONE main concept - if it's '/game', create ONE specific game with related components (score, controls, levels). If it's '/calculator', create ONE calculator with related functions. Be more interactive and creative - add animations, hover effects, dynamic content, or unique interactions. All components should relate to the main topic. Use completely unique themes and backgrounds each time - dark modes, bright colors, gradients, patterns, textures. Create navigation links to related subtopics using './{path_info}/subtopic' format. Make it cohesive, creative, and focused on the main idea. IMPORTANT: Only use images if you know they exist and are publicly accessible - avoid placeholder images or unsplash URLs that might not work. Return ONLY functional HTML code for inside the body tag with embedded CSS and JavaScript. No comments in code (no /* */ or // comments), no extra spaces, no explanations. Code must just work - no one will read it."
    else:
        prompt = "Create a focused HTML webpage about any interesting topic you choose. Focus on ONE main concept with related components that work together. Be more interactive and creative - add animations, hover effects, dynamic content, or unique interactions. Use completely unique themes and backgrounds each time - dark modes, bright colors, gradients, patterns, textures. Create navigation links to related subtopics using './topic/subtopic' format. Make it cohesive, creative, and focused on the main idea. IMPORTANT: Only use images if you know they exist and are publicly accessible - avoid placeholder images or unsplash URLs that might not work. Return ONLY functional HTML code for inside the body tag with embedded CSS and JavaScript. No comments in code (no /* */ or // comments), no extra spaces, no explanations. Code must just work - no one will read it."
    
    # Sanitize the path_info to prevent injection attacks
    safe_path_info = sanitize_input(path_info) if path_info else ""
    
    try:
        logger.info(f"Generating content for sanitized path: {safe_path_info}")
        if API_TYPE == 'openrouter':
            logger.info(f"API REQUEST: {safe_path_info[:30]}...")
            response = openrouter_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                timeout=15  # 15 second timeout
            )
            content = response.choices[0].message.content
            logger.info(f"API RESPONSE: {len(content)} chars received")
            
        elif API_TYPE == 'openai':
            response = openai.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                max_tokens=16000
            )
            content = response.choices[0].message.content
            
        elif API_TYPE == 'gemini':
            response = requests.post(
                API_URL,
                headers={
                    'Content-Type': 'application/json',
                    'X-goog-api-key': GEMINI_API_KEY
                },
                json={
                    'contents': [{
                        'parts': [{
                            'text': prompt
                        }]
                    }]
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['candidates'][0]['content']['parts'][0]['text']
            else:
                return "<h1>Service Temporarily Unavailable</h1><p>Our website is currently overloaded with requests. Please try again in a few minutes.</p><p>We appreciate your patience!</p>"
        
        # Clean up any markdown formatting
        content = content.replace('```html', '').replace('```', '').strip()
        return content
        
    except Exception as e:
        logger.error(f"GENERATION FAILED for {safe_path_info}: {str(e)}")
        return "<h1>Service Temporarily Unavailable</h1><p>Our website is currently overloaded with requests. Please try again later.</p>"

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
    
    # Try to get cached content first
    cached_content = get_cached_content(query_param) if query_param else None
    
    if cached_content:
        logger.info(f"CACHED: {query_param or 'HOME'}")
        content = cached_content
    else:
        # Check if currently being preloaded
        if query_param:
            preload_content = wait_for_preload(query_param)
            if preload_content:
                logger.info(f"PRELOAD READY: {query_param}")
                content = preload_content
            else:
                logger.info(f"GENERATING: {query_param or 'HOME'}")
                content = generate_content_with_ai(query_param)
        else:
            logger.info(f"GENERATING: {query_param or 'HOME'}")
            content = generate_content_with_ai(query_param)
    
    # Start preloading linked content in background if enabled
    if PRELOAD_ENABLED and content:
        links = extract_navigation_links(content)
        if links:
            logger.info(f"PRELOADING: {', '.join(links[:3])}{'...' if len(links) > 3 else ''}")
        for link in links:
            if get_cached_content(link) is None:  # Only preload if not already cached
                preload_content_async(link, depth=0)
    
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
        # Check if currently being preloaded
        preload_content = wait_for_preload(path_info)
        if preload_content:
            logger.info(f"PRELOAD READY: {path_info}")
            content = preload_content
        else:
            logger.info(f"GENERATING: {path_info}")
            content = generate_content_with_ai(full_path_info)
    
    # Start preloading linked content in background if enabled
    if PRELOAD_ENABLED and content:
        links = extract_navigation_links(content)
        if links:
            logger.info(f"PRELOADING: {', '.join(links[:3])}{'...' if len(links) > 3 else ''}")
        for link in links:
            if get_cached_content(link) is None:  # Only preload if not already cached
                preload_content_async(link, depth=0)
    
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