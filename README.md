# Infinite Web

AI-generated websites on demand using Gemini 2.0 Flash.

## Features

- Visit any path and get a unique AI-generated webpage
- Every refresh creates completely new content
- No caching - always fresh AI creativity
- Pure AI design - no hardcoded styling

## Usage

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

The AI generates complete HTML pages including CSS, JavaScript, and content. Every visit triggers a new generation, making each page unique even for the same URL.