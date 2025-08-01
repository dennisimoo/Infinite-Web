import os
import re
import json
import logging
import bleach
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Check which API key is available
OPENROUTER_API_KEY = os.getenv('OPENROUTER_API_KEY')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

# Initialize API clients
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

def extract_navigation_links(content, current_path=""):
    """Extract navigation links from generated content"""
    links = []
    # Look for links in the format href="./path" - must start with ./
    link_patterns = [
        r'href=["\']\./(.*?)["\']',
    ]
    
    for pattern in link_patterns:
        matches = re.findall(pattern, content, re.IGNORECASE)
        for match in matches:
            if match and match not in links and not match.startswith('http') and 'favicon' not in match:
                # Clean up the link
                clean_link = match.strip('/')
                
                # Remove any duplicated path segments completely
                path_parts = clean_link.split('/')
                unique_parts = []
                seen_parts = set()
                
                for part in path_parts:
                    if part not in seen_parts:
                        unique_parts.append(part)
                        seen_parts.add(part)
                
                clean_link = '/'.join(unique_parts)
                
                # Allow deeper paths but prevent exact word repetition
                # Split current path and link path into words
                current_words = set(word.lower() for word in current_path.split('/') if word) if current_path else set()
                link_words = [word.lower() for word in clean_link.split('/') if word]
                
                # Check if any word from current path appears in the link
                has_repeated_words = any(word in current_words for word in link_words)
                
                # Allow paths up to 4 levels deep, no repeated words from current path
                if (clean_link and len(clean_link) < 50 and '.' not in clean_link and 
                    clean_link.count('/') < 4 and not has_repeated_words):
                    links.append(clean_link)
    
    # Ensure we never return more than 5 links
    unique_links = list(set(links))
    return unique_links[:5]

def generate_content_with_ai(path_info):
    """Generate HTML content using AI"""
    # Load prompt from JSON
    with open('prompts.json', 'r') as f:
        prompts = json.load(f)
    
    base_prompt_lines = prompts['base_prompt']
    
    if path_info and path_info.strip('/'):
        topic_text = f" about '{path_info}'"
        nav_format = f"./{path_info}/subtopic"
        current_path = path_info
    else:
        topic_text = " about any interesting topic you choose"
        nav_format = "./topic/subtopic"
        current_path = "HOME"
    
    # Join lines and format
    base_prompt = "\n".join(base_prompt_lines)
    prompt = base_prompt.format(topic_text=topic_text, nav_format=nav_format, current_path=current_path)
    
    # Sanitize the path_info to prevent injection attacks
    safe_path_info = sanitize_input(path_info) if path_info else ""
    
    try:
        logger.info(f"GENERATING: {safe_path_info or 'HOME'}")
        if API_TYPE == 'openrouter':
            response = openrouter_client.chat.completions.create(
                model="google/gemini-2.5-flash",
                messages=[
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                timeout=15  # 15 second timeout
            )
            content = response.choices[0].message.content
            logger.info(f"COMPLETED: {safe_path_info or 'HOME'} ({len(content)} chars)")
            
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