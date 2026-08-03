from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/", tags=["Home"])
async def home():
    return {
        "service": "AI PR Reviewer",
        "status": "running",
        "version": "1.0.0",
        "endpoints": {
          "home": "GET /",
          "health": "GET /health",
          "review": "POST /review  (body: {\"pr_url\": \"https://github.com/owner/repo/pull/1\"})",
          "openapi": "GET /openapi.json",
        },
    }


@router.get("/home", tags=["Home"])
async def home_alias():
    return await home()


@router.get("/index", response_class=HTMLResponse, tags=["Home"])
async def index_page():
    return """
<!DOCTYPE html>
<html>
<head>
  <title>AI PR Reviewer</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 720px; margin: 2rem auto; padding: 0 1rem; }
    code { background: #f4f4f4; padding: 2px 6px; border-radius: 4px; }
    a { color: #0969da; }
  </style>
</head>
<body>
  <h1>AI PR Reviewer</h1>
  <p>Server is running.</p>
  <ul>
    <li><a href="/health">/health</a> — health check</li>
    <li><code>POST /review</code> — review a GitHub PR</li>
  </ul>
  <h2>Example</h2>
  <pre>curl -X POST http://127.0.0.1:8000/review \\
  -H "Content-Type: application/json" \\
  -d '{"pr_url":"https://github.com/owner/repo/pull/1"}'</pre>
</body>
</html>
"""
