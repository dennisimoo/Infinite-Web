from flask import Flask, render_template, request, make_response
import requests
import os
import re
import logging
import bleach
from dotenv import load_dotenv
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

load_dotenv()

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
        prompt = f"Create a focused HTML webpage about '{path_info}'. Focus on ONE main concept - if it's '/game', create ONE specific game with related components (score, controls, levels). If it's '/calculator', create ONE calculator with related functions. Be more interactive and creative - add animations, hover effects, dynamic content, or unique interactions. All components should relate to the main topic. Use completely unique themes and backgrounds each time - dark modes, bright colors, gradients, patterns, textures. Create navigation links to related subtopics using './{path_info}/subtopic' format. Make it cohesive, creative, and focused on the main idea. Return ONLY clean HTML code for inside the body tag with embedded CSS and JavaScript - no comments, no extra spaces, no explanations."
    else:
        prompt = "Create a focused HTML webpage about any interesting topic you choose. Focus on ONE main concept with related components that work together. Be more interactive and creative - add animations, hover effects, dynamic content, or unique interactions. Use completely unique themes and backgrounds each time - dark modes, bright colors, gradients, patterns, textures. Create navigation links to related subtopics using './topic/subtopic' format. Make it cohesive, creative, and focused on the main idea. Return ONLY clean HTML code for inside the body tag with embedded CSS and JavaScript - no comments, no extra spaces, no explanations."
    
    # Sanitize the path_info to prevent injection attacks
    safe_path_info = sanitize_input(path_info) if path_info else ""
    
    try:
        logger.info(f"Generating content for sanitized path: {safe_path_info}")
        if API_TYPE == 'openrouter':
            response = openrouter_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7
            )
            content = response.choices[0].message.content
            
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
        logger.error(f"Content generation failed: {str(e)}")
        return "<h1>Service Temporarily Unavailable</h1><p>Our website is currently overloaded with requests. Please try again later.</p>"

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
    real_ip = request.headers.get('X-Forwarded-For', get_remote_address())
    logger.info(f"Home route accessed: {path_display} from IP: {real_ip}")
    
    content = generate_content_with_ai(query_param)
    response = make_response(render_template('index.html', content=content))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/<path:path_info>')
def dynamic_page(path_info):
    # Sanitize path_info immediately
    path_info = sanitize_input(path_info)
    real_ip = request.headers.get('X-Forwarded-For', get_remote_address())
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
    
    content = generate_content_with_ai(full_path_info)
    response = make_response(render_template('index.html', content=content))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

if __name__ == '__main__':
    port = int(os.getenv('PORT', 3000))
    app.run(host='0.0.0.0', port=port, debug=False)