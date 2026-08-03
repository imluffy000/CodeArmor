# AI PR Reviewer

AI PR Reviewer is a full-stack GitHub pull request review assistant built around a FastAPI backend, a Vite + React frontend, and a multi-agent review pipeline powered by LLM-based analysis. It can inspect PR diffs, run specialist review agents for security, quality, performance, testing, and architecture, optionally enrich results with static-analysis tooling, and post a review back to GitHub.

## Overview

This repository contains two main parts:

- `backend/` — FastAPI application, GitHub OAuth, PR review orchestration, database models, LLM integrations, and static analysis runners.
- `frontend/` — React + Vite interface for authenticating with GitHub, connecting repositories, browsing pull requests, and triggering reviews.

## Features

- GitHub OAuth sign-in and account session management
- Repository connection and pull-request listing from GitHub
- AI-driven PR review using specialized agents
- Structured summary output with file-level and issue-level analysis
- Optional streaming review progress event updates
- Static-analysis integrations for Python, JavaScript, C#, Java, and SQL tooling
- GitHub review posting support with `APPROVE` / `REQUEST_CHANGES`
- SQLite-backed persistence for user and repository state

## Tech Stack

### Backend
- Python 3.11+
- FastAPI
- Uvicorn
- Pydantic
- LangGraph / LangChain-based multi-agent workflow
- Peewee ORM
- GitHub OAuth + session handling
- OpenRouter/OpenAI-compatible LLM access

### Frontend
- React 18
- Vite 5
- Modern single-page UI for review actions and repo management

## Project Structure

```text
AI_PR_REVIEWER/
├── backend/
│   ├── app/
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   └── package.json
└── README.md
```

## Prerequisites

Before running the project, make sure you have:

- Python 3.11+
- Node.js 18+
- npm
- A GitHub OAuth App for authentication
- An OpenRouter or OpenAI API key
- Access to the repositories you want to review

## Environment Configuration

Create a `.env` file in the `backend/` directory with values like the following:

```env
OPENROUTER_API_KEY=your_openrouter_key
# or set OPENAI_API_KEY instead if you prefer direct OpenAI usage

GITHUB_TOKEN=your_github_personal_access_token
GITHUB_CLIENT_ID=your_github_oauth_client_id
GITHUB_CLIENT_SECRET=your_github_oauth_client_secret
SESSION_SECRET=change_this_to_a_secure_secret
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://127.0.0.1:8000
DATABASE_PATH=app_data.db
```

### Notes

- `OPENROUTER_API_KEY` is used by the OpenRouter client and is also mirrored into `OPENAI_API_KEY` when the latter is not explicitly set.
- `GITHUB_TOKEN` is used for direct GitHub API access during diff fetching and review posting.
- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are required for GitHub OAuth login.
- `SESSION_SECRET` should be a strong secret in production.
- `STATIC_ANALYSIS_ROOT` can be exported in the shell if you want the backend to run the static-analysis pass on a repository root.

## Local Development

### 1) Install backend dependencies

```bash
cd backend
python -m pip install -r requirements.txt
```

### 2) Install frontend dependencies

```bash
cd frontend
npm install
```

### 3) Start the backend

From the repository root:

```bash
cd backend
python run.py
```

This starts the FastAPI app on:

- `http://127.0.0.1:8000/`
- `http://127.0.0.1:8000/health`
- `POST http://127.0.0.1:8000/review`

### 4) Start the frontend

```bash
cd frontend
npm run dev
```

The frontend dev server usually runs on:

- `http://localhost:5173`

## Backend API

The FastAPI backend exposes the following primary endpoints:

### Health and service metadata

- `GET /` — simple service metadata
- `GET /health` — health check
- `GET /openapi.json` — OpenAPI schema

### Review endpoints

- `POST /review` — submit a GitHub PR URL and receive a structured review response
- `GET /review/stream` — stream review progress and final output as SSE events
- `POST /review/chat` — chat over the review findings using the LLM assistant

### Auth endpoints

- `GET /auth/github/login` — redirect the user into GitHub OAuth login
- `GET /auth/github/callback` — OAuth callback handler
- `GET /auth/me` — fetch the current signed-in user
- `POST /auth/logout` — clear the session cookie
- `POST /auth/switch` — sign out and revoke the GitHub grant for account switching

### Repository endpoints

- `GET /repos/available` — list available user repositories from GitHub
- `POST /repos/connect` — connect a repository to the app and queue a sync job
- `GET /repos` — list connected repositories for the current user
- `GET /repos/{repo_id}/sync` — fetch sync status for a connected repo
- `GET /repos/{repo_id}/pulls` — list pull requests for a connected repository
- `DELETE /repos/{repo_id}` — disconnect a repository

## Example Review Request

```bash
curl -X POST http://127.0.0.1:8000/review \
  -H "Content-Type: application/json" \
  -d '{"pr_url":"https://github.com/owner/repo/pull/1"}'
```

## Review Workflow

The review process follows this general flow:

1. Fetch the PR diff from GitHub.
2. Parse the diff into a structured representation.
3. Run the specialist review agents:
   - security
   - quality
   - performance
   - testing
   - architecture
4. Merge and summarize findings.
5. Build a structured JSON response.
6. Optionally post the review back to GitHub.

## Static Analysis

The project includes specialized runners for multiple languages and toolchains, including:

- Bandit
- Pylint
- Semgrep
- ESLint
- SpotBugs
- SQLFluff
- C# Roslyn-based analysis support

These tools are intended to complement the LLM review flow with deterministic rule-based scanning.

## Testing

The backend test suite uses Python's built-in `unittest` framework.

Run tests with:

```bash
cd backend
python -m unittest discover -s tests
```

## Production Notes

- The backend CORS policy currently allows local frontend development on `localhost:5173` and `127.0.0.1:5173`.
- For production deployment, restrict CORS origins and tighten authentication/session settings.
- The default session secret is intentionally permissive for local development only.

## License

This project does not currently declare a license in the repository structure. Add a license file before public distribution if you want to publish it externally.

## Contributing

Contributions are welcome. If you are improving the backend review engine, frontend UI, or static-analysis coverage, please keep the following in mind:

- add or update tests where behavior changes
- preserve the FastAPI/React monorepo split
- document configuration changes in this README

## Troubleshooting

### Backend fails to start

Check that:

- Python dependencies are installed
- your `.env` file is present and contains valid keys
- your GitHub OAuth client settings match `FRONTEND_URL` and `BACKEND_URL`

### GitHub login does not work

Confirm that:

- `GITHUB_CLIENT_ID` and `GITHUB_CLIENT_SECRET` are correctly set
- your GitHub OAuth App callback URL matches the app's expected backend callback route
- the frontend is being served from the configured `FRONTEND_URL`

### Review requests fail

Verify that:

- `GITHUB_TOKEN` is valid and has the required scopes
- the PR URL is publicly accessible or the token can read it
- the LLM provider credentials are configured properly

## Roadmap

Potential areas for expansion include:

- better repository sync progress and history tracking
- stronger review result persistence
- richer dashboard analytics for review outcomes
- broader language coverage and annotation support
- deployment configuration for Docker/Kubernetes or serverless hosting
