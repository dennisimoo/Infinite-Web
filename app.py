from flask import Flask, render_template, request, make_response
import requests
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Check which API key is available
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')

if OPENAI_API_KEY:
    import openai
    openai.api_key = OPENAI_API_KEY
    API_TYPE = 'openai'
    print("Using OpenAI GPT-4o-mini")
elif GEMINI_API_KEY:
    API_TYPE = 'gemini'
    API_URL = 'https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent'
    print("Using Gemini 2.0 Flash")
else:
    raise ValueError("No API key found. Please set either OPENAI_API_KEY or GEMINI_API_KEY in your .env file")

def generate_content_with_ai(path_info):
    if path_info and path_info.strip('/'):
        prompt = f"Create a complete HTML webpage about '{path_info}'. Generate everything - all HTML, CSS, JavaScript, content. Do not include any images. IMPORTANT: Include hyperlinks to related subpages using relative URLs like './privacy-policy', './about', './contact', './terms', etc. These links should be relevant to the '{path_info}' topic. Make it a full webpage experience. Return only HTML that goes inside the body tag."
    else:
        prompt = "Create a complete HTML webpage about any topic you choose. Generate everything - all HTML, CSS, JavaScript, content. Do not include any images. IMPORTANT: Include hyperlinks to related subpages using relative URLs like './privacy-policy', './about', './contact', './terms', etc. These links should be relevant to your chosen topic. Make it a full webpage experience. Return only HTML that goes inside the body tag."
    
    try:
        if API_TYPE == 'openai':
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
                return f"<h1>Error generating content</h1><p>API returned status code: {response.status_code}</p>"
        
        # Clean up any markdown formatting
        content = content.replace('```html', '').replace('```', '').strip()
        return content
        
    except Exception as e:
        return f"<h1>Error</h1><p>Failed to generate content: {str(e)}</p>"

@app.route('/')
def home():
    # Check for query parameters
    query_param = request.args.get('query') or request.args.get('prompt') or ''
    for key, value in request.args.items():
        if key not in ['query', 'prompt'] and value:
            query_param = value
            break
    if not query_param:
        query_param = next(iter(request.args.keys()), '') if request.args else ''
    
    path_display = f"/?{query_param}" if query_param else "/"
    print(f"Generating webpage for: {path_display}")
    
    content = generate_content_with_ai(query_param)
    response = make_response(render_template('index.html', content=content))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/<path:path_info>')
def dynamic_page(path_info):
    print(f"Generating webpage for: /{path_info}")
    
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