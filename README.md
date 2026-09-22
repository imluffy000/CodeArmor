# CodeArmor

**AI pull request review with a merge-readiness gate.**

Sign in with GitHub, pick a repository, open one of its pull requests, and six
specialist agents read the diff in parallel — security, code quality,
performance, testing, architecture and integration. You get findings with
copy-paste-ready fixes, and a deterministic verdict on whether the change is
safe to merge.

CodeArmor never approves a pull request. It reports; a human decides.

---

## Table of contents

- [What it does](#what-it-does)
- [How a review works](#how-a-review-works)
- [The six agents](#the-six-agents)
- [The merge gate](#the-merge-gate)
- [Architecture](#architecture)
- [Security model](#security-model)
- [What happens to your code](#what-happens-to-your-code)
- [Running it locally](#running-it-locally)
- [Configuration](#configuration)
- [Deploying](#deploying)
- [API reference](#api-reference)
- [Testing](#testing)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Roadmap](#roadmap)

---

## What it does

The whole product is one loop:

```
Sign in with GitHub
   └─> Pick a repository you can access
         └─> See its pull requests
               └─> Run a review on one
                     ├─ 6 agents read the diff in parallel
                     ├─ deterministic checks read GitHub (CI, conflicts, drift)
                     ├─ findings are deduplicated and ranked
                     └─ a merge gate returns: blocked / caution / clear
                           └─> Read it, ask questions, optionally post it to the PR
```

Each review gives you:

| | |
|---|---|
| **Findings** | Grouped by file, worst first, each with the offending code and a complete corrected version |
| **Merge verdict** | `blocked`, `caution` or `clear`, with a named reason per gate |
| **Score** | 0–100, computed server-side from severity and coverage, so it is stored and reproducible |
| **Coverage** | How much of the diff was actually read — a partial review says so, loudly |
| **Agent health** | Which reviewers completed. A review missing its security pass is never presented as clean |
| **Chat** | Ask follow-up questions about the findings |
| **History** | Reviews are stored, so closing the tab does not destroy one |

---

## How a review works

```
                       GET /reviews/stream?repo_id&pr_number
                                    │
                    ┌───────────────▼────────────────┐
                    │  1. Gather (deterministic)     │
                    │  · PR metadata + diff          │
                    │  · changed files with patches  │
                    │  · mergeable state, CI checks  │
                    │  · base-branch drift           │
                    │  · dependency / migration /    │
                    │    contract / config deltas    │
                    └───────────────┬────────────────┘
                                    │
                    ┌───────────────▼────────────────┐
                    │  2. Budget the diff per file   │
                    │  rank by review value, fit to  │
                    │  budget, always name every     │
                    │  changed file                  │
                    └───────────────┬────────────────┘
                                    │
       ┌──────────┬──────────┬──────┴─────┬──────────┬────────────┐
       ▼          ▼          ▼            ▼          ▼            ▼
   security   quality   performance    testing  architecture  integration
       │          │          │            │          │            │
       └──────────┴──────────┴──────┬─────┴──────────┴────────────┘
                                    │  (LangGraph fan-in)
                    ┌───────────────▼────────────────┐
                    │  3. Reconcile                  │
                    │  · dedupe across agents        │
                    │  · agreement count as signal   │
                    │  · rank worst-first            │
                    └───────────────┬────────────────┘
                    ┌───────────────▼────────────────┐
                    │  4. Merge gate (deterministic) │
                    │  10 gates -> blocked/caution/  │
                    │  clear + named blockers        │
                    └───────────────┬────────────────┘
                    ┌───────────────▼────────────────┐
                    │  5. Summarise, score, store    │
                    └───────────────┬────────────────┘
                                    ▼
                      SSE `complete` → stored Review
                                    │
                        (optional, explicit)
                                    ▼
                     POST /reviews/{id}/publish → GitHub
```

Progress streams over SSE as each agent finishes, so you watch six reviewers
work rather than a spinner.

**Caching.** A review is keyed on the PR's head commit SHA. Re-opening a report
returns the stored result instantly; pushing a new commit invalidates it. Pass
`refresh=true` to force a re-run.

---

## The six agents

Each agent is one model call over the same budgeted diff, with a shared output
contract and a shared severity rubric so their findings are comparable.

| Agent | Question it answers |
|---|---|
| **Security** | Can this be exploited? Injection, authorization gaps, leaked secrets, unsafe deserialization, path traversal, weak crypto, secrets in logs, SSRF |
| **Quality** | Will this cost someone time later? Duplication, misleading names, swallowed errors, dead code, unreleased resources, boundary conditions |
| **Performance** | Does it do work it doesn't need to? N+1 queries, repeated computation, blocking I/O on async paths, unbounded memory, missing indexes, complexity that won't scale |
| **Testing** | Is this change verified? Untested branches, untested error paths, weak assertions, flaky patterns, a fix with no reproducing test |
| **Architecture** | Does the structure hold? Layer coupling, misplaced logic, missing or premature abstractions, circular dependencies, hardcoded configuration |
| **Integration** | **What breaks when this merges?** Removed routes and exported symbols, non-backward-compatible migrations, dependency drift, new required config, conflicts, CI state, base drift |

### Why integration is different

The other five agents reason from the diff. Integration questions are
relational — *"is this compatible with code the diff does not contain?"* — and
no amount of prompt engineering gets an LLM to answer that from a diff alone.

So [`integration_context_service.py`](backend/app/services/integration_context_service.py)
computes the facts first, deterministically and with no model involved:

- **Contracts** — removed or renamed routes across FastAPI, Express, Flask,
  Spring and ASP.NET; removed public functions and exports; edited OpenAPI,
  GraphQL and protobuf schemas; deleted and renamed files
- **Schema** — migration files, destructive SQL (`DROP COLUMN`, `SET NOT NULL`,
  type narrowing, renames), and model-changed-without-migration in either direction
- **Dependencies** — added, removed and bumped packages with major-version
  detection; manifest changed without its lockfile; unpinned additions
- **Configuration** — new `os.getenv` / `process.env` lookups with no default
  and no matching `.env.example` entry
- **Live GitHub state** — `mergeable`, CI check runs and legacy statuses, and
  `behind_by` with the specific overlap between base-branch changes and the
  files this PR touches

The agent then judges consequences and deploy ordering over those facts, rather
than guessing at them.

### Severity calibration

Six independent agents will not agree on what "HIGH" means unless you tell
them. [`severity_rubric.txt`](backend/app/prompts/_shared/severity_rubric.txt)
anchors each level with examples, and only SECURITY and INTEGRATION findings may
be CRITICAL. Severity and category are then validated against an enum
server-side — an unrecognised value used to fall out of every histogram, so a
pull request with ten "SEVERE" findings displayed as a perfect score.

### Deduplication

Six agents reading the same code find the same problem and name it three
different ways. Findings at the same location with substantially the same text
collapse into one, which records how many agents agreed. Agreement becomes a
confidence signal instead of triple-counting one defect.

---

## The merge gate

The "before merging" half of the product, in
[`merge_gate_service.py`](backend/app/services/merge_gate_service.py). It is
deliberately deterministic — a gate a model can talk its way past is not a gate.

Ten independent gates, each reporting `pass` / `warn` / `fail` / `unknown`:

| Gate | Fails when |
|---|---|
| `conflicts` | The branch conflicts with its base |
| `ci` | A check run or commit status is failing |
| `base_drift` | The base changed files this PR also changes — merges cleanly, still breaks |
| `schema` | A migration drops, renames or narrows something |
| `contracts` | A route or public symbol was removed or renamed |
| `dependencies` | A manifest changed without its lockfile |
| `config` | *(warns)* A new required environment variable is undocumented |
| `findings` | There is a CRITICAL finding |
| `coverage` | *(warns)* Only part of the diff was reviewed |
| `pipeline` | *(warns)* A reviewer did not complete |

Any failure → `blocked`. Any warning → `caution`. Otherwise → `clear`, which
reads *"Nothing blocking was found. A human review is still required."*

That phrasing is the point. `clear` is not approval, and the difference matters
most exactly when the review was partial or an agent died.

---

## Architecture

```
┌─────────────────────────┐        ┌──────────────────────────────────┐
│  React + Vite (Vercel)  │        │      FastAPI (Render)            │
│                         │        │                                  │
│  repo picker            │  HTTPS │  /auth    GitHub OAuth, sessions  │
│  PR list                │◄──────►│  /repos   connect, sync, PRs      │
│  live SSE progress      │ cookie │  /reviews run, stream, publish    │
│  merge gate panel       │  +CSRF │                                  │
│  findings + chat        │        │  LangGraph: 6 agents ─> fan-in    │
│  review history         │        │  merge gate (deterministic)       │
└─────────────────────────┘        └───────┬──────────────┬───────────┘
                                           │              │
                                    ┌──────▼─────┐  ┌─────▼──────┐
                                    │ GitHub API │  │ OpenRouter │
                                    │ user token │  │  (the LLM) │
                                    └────────────┘  └────────────┘
                                           │
                                    ┌──────▼──────────────┐
                                    │ Postgres (or SQLite)│
                                    │ users, repos, jobs, │
                                    │ stored reviews      │
                                    └─────────────────────┘
```

**Backend** — Python 3.11, FastAPI, LangGraph + LangChain, Peewee, httpx, PyJWT,
cryptography (Fernet).
**Frontend** — React 18, Vite 5, no UI framework, hand-written CSS.
**Model** — any OpenRouter model; default `deepseek/deepseek-chat-v3-0324`.

### One pipeline, not two

The review used to be implemented twice — once through LangGraph for the
non-streaming endpoint and once by hand for the SSE stream. The copies had
already diverged on error handling, so a bug fixed in one stayed live in the
other. Now `stream_review()` is the only orchestrator and the non-streaming
caller drains its generator.

LangGraph owns the fan-out as six real parallel nodes with
`Annotated[..., operator.add]` reducers on the fields more than one branch
writes. `graph.astream(stream_mode="updates")` gives a per-agent completion
event for free, which is what makes progress streaming need no second
implementation.

---

## Security model

The threat model: CodeArmor holds GitHub tokens that can read and write users'
private repositories. A compromise of this service is a compromise of their
source code.

### Authentication and sessions

- GitHub OAuth authorization code flow, with a signed, short-lived, single-use
  `state` cookie
- Session is a JWT in an `httpOnly` cookie, `Secure` + `SameSite=None` in
  production (a Vercel → Render call is cross-site; a `SameSite=Lax` cookie is
  never sent on `fetch` or `EventSource`, which is why production login could
  not work before)
- The JWT carries the user's `session_version`. Signing out increments it, which
  **invalidates every cookie ever issued to that user** — a copied session stops
  working immediately rather than lasting out its TTL
- `iss`, `aud`, `iat` and `exp` are all required on decode; the algorithm is
  pinned to HS256
- In production the app **refuses to start** with a default or short
  `SESSION_SECRET`, a missing `TOKEN_ENCRYPTION_KEY`, a non-HTTPS URL, a
  plaintext CORS origin, or `SameSite=None` without `Secure`

### Authorization

- Every data endpoint requires a session. There is no anonymous path and **no
  server-wide GitHub token** — the fallback that let an unauthenticated caller
  read any private diff the operator's token could reach, and post a review
  under the operator's identity, is gone
- A review is addressed by `repo_id` + `pr_number`, never a free-text URL. The
  server builds the GitHub URL from a repository row the caller owns, so an
  attacker-chosen repository path never reaches the GitHub API — and a private
  repository name never lands in an access log
- Every query is scoped to the current user; cross-user access returns 404, not
  403, because whether an id exists is not the caller's business
- Double-submit CSRF (`X-CSRF-Token` + cookie) plus an `Origin` allowlist on
  every state-changing request, since `SameSite=None` no longer does that job
- Per-user rate limits on reviews and chat

### Token storage

- GitHub tokens are encrypted at rest with Fernet, under `TOKEN_ENCRYPTION_KEY`
- That key is **separate from `SESSION_SECRET`**. Previously one secret did both
  jobs, so rotating a leaked signing key silently made every stored token
  undecryptable — which meant nobody rotated it
- `MultiFernet` supports rotation with no downtime:
  `python -m app.scripts.reencrypt_tokens`
- A token that cannot be decrypted returns 401 "sign in again", not a 500

### Prompt injection

The diff is written by whoever opened the pull request, and the review can be
posted back to GitHub. That is a complete attack chain if the model treats diff
content as instructions.

- A system message states the instruction hierarchy explicitly and tells agents
  to report any embedded directive as a HIGH security finding rather than obey it
- The diff goes in a **user** message, inside a fence tagged with a per-request
  random nonce the author cannot forge
- Findings echoing injection phrasing set `injection_suspected`, which downgrades
  a `clear` verdict to `caution` and adds a visible warning
- **CodeArmor only ever posts `COMMENT`.** An `APPROVE` can satisfy a
  branch-protection rule, so an automated approval driven by attacker-controlled
  text is a way to merge unreviewed code. (GitHub also rejects
  `APPROVE`/`REQUEST_CHANGES` on your own PR with a 422, which is the common case
  here — the old code's default failed every time.)

### Output handling

- Findings are validated per item, so one malformed entry no longer discards the
  other nine — a silent total loss that looked exactly like a clean pull request
- Errors return a generic message plus an `X-Request-ID`; upstream GitHub bodies
  are never echoed, because they can name private repositories and disclose the
  token owner's user id
- Every log record passes a redaction filter (GitHub tokens, Fernet ciphertext,
  `sk-` keys, `Authorization` headers), attached to uvicorn's loggers too

### Deleting your data

`DELETE /auth/account` revokes CodeArmor's GitHub grant and deletes the user row;
connected repositories, sync jobs and stored reviews cascade with it.

---

## What happens to your code

Be clear-eyed about this, because it is the honest cost of the product.

**Leaves the system.** To review a pull request, its diff is sent to
[OpenRouter](https://openrouter.ai), which relays it to whichever provider serves
the configured model. That is **six calls per review**, one per agent, plus the
summary. CodeArmor sets `data_collection: "deny"` so OpenRouter routes only to
providers that do not store or train on prompts, and sets an explicit timeout and
retry cap — but your source code does reach a third party. Set your OpenRouter
account's data policy accordingly, and tell your users.

**Stored.** Your GitHub profile, an encrypted access token, connected repository
metadata, and completed reviews (findings, snippets and the summary). Review
payloads include the code snippets the agents quoted.

**Not stored.** The raw diff. It lives in memory for the duration of a review and
is never written to disk.

**Pinned off.** LangChain enables LangSmith tracing from environment variables
alone, and it uploads full prompt payloads — your source code, mirrored to a
second third party, with no code change. `config.py` explicitly sets those
variables to `false` so a stray dashboard setting cannot switch it on.

---

## Running it locally

### Prerequisites

- Python 3.11 (see [`backend/.python-version`](backend/.python-version))
- Node.js 20+
- A GitHub OAuth App
- An OpenRouter API key

### 1. Create a GitHub OAuth App

github.com → Settings → Developer settings → OAuth Apps → New OAuth App.

| Field | Value |
|---|---|
| Homepage URL | `http://127.0.0.1:5173` |
| Authorization callback URL | `http://127.0.0.1:8000/auth/github/callback` |

The callback must exactly match `$BACKEND_URL/auth/github/callback`, or GitHub
returns `redirect_uri_mismatch`.

### 2. Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
```

Fill in `.env`. Generate the two secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"                        # SESSION_SECRET
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"  # TOKEN_ENCRYPTION_KEY
```

```bash
python run.py
```

`http://127.0.0.1:8000` — with interactive docs at `/docs`.

### 3. Frontend

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

`http://127.0.0.1:5173`.

> Use `127.0.0.1`, not `localhost`. They are separate origins with separate
> cookie jars, and the OAuth callback lands on `127.0.0.1`. In development the
> app redirects you automatically; in production, `SameSite=None` cookies make
> this moot.

---

## Configuration

Everything is environment-driven; see [`backend/.env.example`](backend/.env.example).

| Variable | Required | Notes |
|---|---|---|
| `ENVIRONMENT` | yes | `development` or `production`. `production` arms the fail-fast checks |
| `OPENROUTER_API_KEY` | yes | Reviews fail without it |
| `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET` | yes | From your OAuth App |
| `SESSION_SECRET` | yes | 32+ random chars. Signs session JWTs **only** |
| `TOKEN_ENCRYPTION_KEY` | yes in prod | A Fernet key. Encrypts stored GitHub tokens |
| `TOKEN_ENCRYPTION_KEY_OLD` | no | Set only during a rotation |
| `FRONTEND_URL` / `BACKEND_URL` | yes | Must be `https://` in production |
| `ALLOWED_ORIGINS` | yes | Comma-separated exact origins. Never `*` with credentials |
| `COOKIE_SECURE` / `COOKIE_SAMESITE` | yes | `true`/`none` cross-site; `false`/`lax` for local HTTP |
| `DATABASE_URL` | prod | Postgres. Without it, SQLite — which a container wipes on every deploy |
| `GITHUB_OAUTH_SCOPES` | no | Default `read:user repo`. Use `read:user public_repo` for public repos only |
| `LLM_MODEL` | no | Any OpenRouter model id |
| `LLM_TIMEOUT_SECONDS` | no | Default 120 |
| `REVIEW_RATE_LIMIT_PER_HOUR` | no | Default 20 per user |
| `CHAT_RATE_LIMIT_PER_HOUR` | no | Default 60 per user |
| `MAX_DIFF_CHARS` / `AGENT_DIFF_CHARS` | no | 60000 / 24000 |

### A note on `repo` scope

`repo` grants read **and write** on every repository the user can access. It is
the only classic OAuth scope that can list and diff private repositories, which
this product requires, and it is also what lets CodeArmor post its comment.

If you only review public repositories, set
`GITHUB_OAUTH_SCOPES="read:user public_repo"`. The durable fix is a GitHub App
with per-repository installation, granular permissions and short-lived tokens —
see [Roadmap](#roadmap).

---

## Deploying

The repository ships [`render.yaml`](render.yaml) and
[`frontend/vercel.json`](frontend/vercel.json), so the deployment is reviewable
rather than living in a dashboard nobody can diff.

### Backend on Render

Render Dashboard → New → Blueprint → point at this repo. Then set the four
`sync: false` secrets and replace the `REPLACE-ME` URLs.

If you configure it by hand instead:

| Setting | Value |
|---|---|
| Root directory | `backend` |
| Build command | `pip install --upgrade pip && pip install -r requirements.txt` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 1 --timeout-keep-alive 75 --proxy-headers --forwarded-allow-ips='*'` |
| Health check path | `/health` |

`--host 0.0.0.0` is not optional: Render port-scans the container and fails the
deploy with "no open ports detected" for a `127.0.0.1` bind.

### Frontend on Vercel

| Setting | Value |
|---|---|
| Root directory | `frontend` |
| Framework | Vite |
| Install / Build | `npm ci` / `npm run build` |
| Output | `dist` |
| Env (Production **and** Preview) | `VITE_API_URL=https://your-api.onrender.com` |

Do **not** set `NODE_ENV=production` on Vercel: `vite` is a devDependency, npm
would skip it, and the build fails with `vite: not found`.

Everything `VITE_*` is inlined into the public bundle. Never put a secret there.

### After deploying

1. Update the OAuth App: homepage to the Vercel URL, callback to
   `https://your-api.onrender.com/auth/github/callback`
2. Set `BACKEND_URL` to exactly that host — `build_authorize_url` derives the
   callback from it, and a mismatch is `redirect_uri_mismatch`
3. Confirm `ALLOWED_ORIGINS` contains your **stable** production domain, not a
   per-deploy preview URL
4. Check `GET /readyz` — it reports config validity and database reachability

### Why Postgres, not SQLite

A Render filesystem is wiped on every deploy, every restart, every free-tier
spin-up and every instance replacement. On SQLite that takes every user, every
connected repository, every stored OAuth token and every saved review with it —
and existing session cookies still verify, so users are ejected mid-session with
a confusing 401. `DATABASE_URL` is the fix, and `render.yaml` provisions it.

---

## API reference

All endpoints require a session cookie. Every state-changing request also
requires `X-CSRF-Token` matching the `csrf_token` cookie.

### Auth

| | |
|---|---|
| `GET /auth/github/login` | Start the OAuth flow (`?prompt=select_account` to force the picker) |
| `GET /auth/github/callback` | OAuth callback |
| `GET /auth/me` | Current user + CSRF token |
| `POST /auth/logout` | Sign out **everywhere** — invalidates every issued session |
| `POST /auth/switch` | Sign out and revoke the GitHub grant |
| `DELETE /auth/account` | Revoke access and erase all your data |

### Repositories

| | |
|---|---|
| `GET /repos/available?page&search` | Repositories you can access (search runs on GitHub) |
| `POST /repos/connect` | Connect one — `{"full_name": "owner/repo"}` or `{"url": "..."}` |
| `GET /repos` | Your connected repositories |
| `GET /repos/{id}/sync` | Sync status |
| `POST /repos/{id}/sync` | Re-sync metadata |
| `GET /repos/{id}/pulls?state&page` | Pull requests (`open` / `closed` / `all`) |
| `DELETE /repos/{id}` | Disconnect |

### Reviews

| | |
|---|---|
| `POST /reviews` | Run a review — `{"repo_id": 1, "pr_number": 42, "post_to_github": false}` |
| `GET /reviews/stream?repo_id&pr_number&refresh` | Run one, streaming progress over SSE |
| `GET /reviews?repo_id&pr_number&limit` | Review history |
| `GET /reviews/{id}` | A stored review |
| `POST /reviews/{id}/publish` | Post it to the PR as a comment |
| `DELETE /reviews/{id}` | Delete it |
| `POST /reviews/chat` | Ask about a stored review |

### SSE events

| Event | Data |
|---|---|
| `step` | `fetch_diff_start`, `fetch_diff_done`, `summary_done` |
| `coverage` | JSON: reviewed percent and unreviewed files, when the diff was budgeted |
| `agent_done` / `agent_failed` | The agent's name |
| `cached` | A stored review for this head SHA is being returned |
| `complete` | The full review payload as JSON |
| `error` | A client-safe message |

---

## Testing

```bash
cd backend
python -m pytest tests -q          # 128 tests
```

```bash
cd frontend
npm run build
```

The suite is organised around the properties that must not regress:

| File | Covers |
|---|---|
| `test_security.py` | Anonymous access is refused on every data endpoint; forged and revoked sessions; CSRF; cross-user isolation; token encryption; the production config guards; rate limits; log redaction |
| `test_integration_checks.py` | Every deterministic integration check and all ten merge gates, including that a partial or incomplete review is never `clear` |
| `test_findings.py` | Severity and category validation, the JSON parser, deduplication, ordering, the directory/filename tree collision, scoring |
| `test_pipeline.py` | Prompt assembly, per-item validation, the six-agent fan-out, failure degradation, injection handling, the GitHub message |

CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the tests,
pylint, bandit, the frontend build, gitleaks, and a guard that fails the build if
a database file, an env file or a virtualenv is ever committed.

---

## Project layout

```
CodeArmor/
├── render.yaml                     Render Blueprint
├── .github/workflows/ci.yml        Tests, lint, security scan, artifact guard
│
├── backend/
│   ├── run.py                      Dev entrypoint (env-aware host/port)
│   ├── .python-version             3.11.9
│   ├── .env.example
│   └── app/
│       ├── main.py                 App, CORS, request ids, error handlers
│       ├── core/
│       │   ├── config.py           Env config + fail-fast production guards
│       │   ├── constants.py        Severity/category vocabulary and aliases
│       │   └── logging.py          Redaction filter + audit trail
│       ├── github/client.py        The single GitHub client (async, per-user token)
│       ├── db/                     Peewee models, migrations, job reconciliation
│       ├── graph/                  LangGraph: 6 parallel nodes -> fan-in
│       ├── agents/                 One module per agent
│       ├── prompts/
│       │   ├── _shared/            System prompt, severity rubric, output contract
│       │   └── *_prompt.txt        Per-agent role and checklist
│       ├── services/
│       │   ├── review_service.py             The one orchestrator
│       │   ├── integration_context_service.py Deterministic integration facts
│       │   ├── merge_gate_service.py         The merge verdict
│       │   ├── llm_service.py                Prompting + output validation
│       │   ├── issue_service.py              Dedupe, ranking, scoring
│       │   ├── auth_service.py               Sessions, CSRF
│       │   ├── crypto_service.py             Token encryption + rotation
│       │   └── rate_limit_service.py
│       ├── static_analysis/        Not wired in — see the package docstring
│       ├── scripts/                Key rotation, exposure response
│       └── visualizer/             Folder tree, response shaping
│
└── frontend/
    ├── vercel.json
    └── src/
        ├── api.js                  CSRF, timeouts, typed errors
        ├── App.jsx
        ├── lib/markdown.jsx        Safe model-output rendering
        └── components/
            ├── RepoConnect.jsx     Server-side repo search
            ├── RepoList.jsx        Connected repos, sync polling
            ├── PullRequestList.jsx PR list, state filter, post toggle
            ├── ReviewDashboard.jsx Live progress + the report
            ├── MergeGate.jsx       The verdict panel
            ├── ReviewHistory.jsx   Stored reviews
            └── ErrorBoundary.jsx
```

### Static analysis is deliberately not wired in

`backend/app/static_analysis/` wraps bandit, pylint, semgrep, eslint, SpotBugs,
Roslyn and sqlfluff behind a language-detecting registry. It is good code, it is
tested, and the review pipeline does not call it.

The reason is in the package docstring: a static analyser needs a checkout, and
CodeArmor never clones the pull request. The previous wiring pointed the runners
at a server-side `STATIC_ANALYSIS_ROOT`, so it analysed **CodeArmor's own source
tree** and attributed the findings to the user's pull request — then offered to
post them to that repository. Turning it on properly means cloning the PR head
into a sandbox; until then the pipeline does not pretend to run it.

---

## Troubleshooting

**Signed in, but the app still shows the login card.**
The session cookie is not reaching the API. Check `ALLOWED_ORIGINS` contains your
exact frontend origin, and that `COOKIE_SECURE=true` and `COOKIE_SAMESITE=none`
in production. A cross-site cookie is dropped by every browser unless it is both.

**`redirect_uri_mismatch` from GitHub.**
`BACKEND_URL` and the OAuth App's callback URL disagree. The callback must be
exactly `$BACKEND_URL/auth/github/callback`.

**The app refuses to start in production.**
That is deliberate. The error names the setting — a default `SESSION_SECRET`, a
missing `TOKEN_ENCRYPTION_KEY`, an `http://` URL, or `SameSite=None` without
`Secure`. Booting wide open is worse than not booting.

**"Your GitHub authorization needs to be renewed."**
`TOKEN_ENCRYPTION_KEY` changed and the stored ciphertext no longer opens. Either
restore the old key as `TOKEN_ENCRYPTION_KEY_OLD` and run
`python -m app.scripts.reencrypt_tokens`, or have users sign in again.

**The review says it only covered part of the diff.**
It did, and it is telling you rather than hiding it. Raise `AGENT_DIFF_CHARS`,
or split the pull request. The named-but-unreviewed files are listed in the
report.

**A repository is stuck on "Syncing…".**
Syncs run as in-process tasks, so a restart abandons them. Startup marks
interrupted jobs failed, and the UI stops polling after two minutes. Click
**Re-sync**.

**Everyone was signed out after a deploy.**
Probably SQLite on an ephemeral filesystem. Set `DATABASE_URL`.

---

## Roadmap

Known gaps, roughly in order of value:

- **GitHub App instead of an OAuth App** — per-repository installation, granular
  permissions (`Contents: read`, `Pull requests: write`), and short-lived
  installation tokens instead of a long-lived `repo`-scoped token at rest. This
  largely dissolves the token-storage risk
- **A worker queue** — reviews and syncs run in-process, so they die on restart
  and cannot scale past one instance. Postgres `SELECT ... FOR UPDATE SKIP LOCKED`
  is the cheapest durable option
- **An evaluation harness** — a golden set of frozen diffs with labelled expected
  findings, scored for precision, recall, schema validity and injection
  resistance. Without it, every prompt edit is an unmeasured change to product
  behaviour. This is the single biggest quality gap
- **Inline PR comments** — findings carry a `line`, so they could be posted
  against the diff instead of as one body. Needs snippet-to-hunk anchoring first
- **Suggestion validation** — check that a finding's `file` is actually in the
  PR, that its `code_snippet` appears in the diff, and that its
  `suggestion_snippet` parses
- **Static analysis on a real checkout** — clone the PR head into a sandbox and
  wire up the existing registry
- **Token and cost accounting** — capture per-agent usage and enforce a per-review
  ceiling
- **Frontend tests and linting** — Vitest plus eslint-plugin-react-hooks

## License

No license is declared. Add one before publishing.
