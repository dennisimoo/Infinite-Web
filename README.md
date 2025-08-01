# Infinite Web

AI-generated websites on demand using Gemini 2.0 Flash.

🌐 **Live Demo**: https://infinitewebai.fly.dev/

## Features

- Visit any path and get a unique AI-generated webpage
- Every refresh creates completely new content
- No caching - always fresh AI creativity
- Pure AI design - no hardcoded styling
- **Infinite hyperlinks** - AI creates links to subpages that generate more content
- **Nested navigation** - Follow links to explore infinitely branching content trees

## Live Examples

Try these paths on the live site:
- https://infinitewebai.fly.dev/ - AI picks any topic
- https://infinitewebai.fly.dev/cats - AI creates content about cats
- https://infinitewebai.fly.dev/space/exploration - AI creates space exploration content
- https://infinitewebai.fly.dev/?gaming - AI creates content about gaming

## Local Development

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Add your Gemini API key to `.env`:
```
GEMINI_API_KEY=your_api_key_here
```

3. Run the Flask app:
```bash
python app.py
```

4. Visit `localhost:3000` and explore:
   - `localhost:3000/` - AI picks any topic
   - `localhost:3000/cats` - AI creates content about cats
   - `localhost:3000/?topic` - AI creates content about topic
   - `localhost:3000/anything/you/want` - AI interprets the path

## How it works

The AI generates complete HTML pages including CSS, JavaScript, and content. Every visit triggers a new generation, making each page unique even for the same URL. The AI also generates hyperlinks to related subpages, creating an infinite web of interconnected content.

