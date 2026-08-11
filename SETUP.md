# Project Setup & Run Guide

How to set up and run the Data Source Onboarding Agent from scratch on any system.

## What you are running

Two halves, one URL:

| half | what it is | lives in |
| --- | --- | --- |
| **Backend** | FastAPI + the agent pipeline | [`src/dsoa/`](src/dsoa/) |
| **Front end** | React 18 + TypeScript, built by Vite | [`frontend/`](frontend/) |

The front end compiles to plain static files (`frontend/dist/`) that FastAPI
serves itself. In normal use there is **one process on one port** — no separate
Node server, and no CORS configuration anywhere, because the browser only ever
talks to a single origin. Node is needed to *build* the UI, not to run it.

---

## Prerequisites

1. **Python 3.11+**
2. **Node.js 18+** — builds the React front end and runs the local test database.

Without Node the server still starts, but it falls back to the older single-file
UI in `src/dsoa/api/static/`. You want Node.

---

## Step 1: Install

```bash
cd data-source-onboarding-agent
./bin/install.sh
```

This creates a virtual environment (`.venv`), installs the Python dependencies,
installs the front-end dependencies, and builds `frontend/dist`. Re-run it any
time; it is safe to repeat.

---

## Step 2: Configure environment variables

```bash
cp .env.example .env
```

Then add a key for whichever model you want. The backend accepts Anthropic,
Gemini, or DeepSeek:

```env
ANTHROPIC_API_KEY=your_key_here
# or
GEMINI_API_KEY=your_key_here
# or
DEEPSEEK_API_KEY=your_key_here
```

**No key? Everything still works.** With none set, the app uses `ScriptedClient`,
which serves canned responses through the same interface as a real provider. The
header shows `offline — scripted`, and all three example requests run end to end.
This is the reliable way to demo the project.

`.env` is gitignored. Never commit real credentials — this project exists to
demonstrate that connectors read secrets from the environment, so the repo has to
practise what it generates.

---

## Step 3: Run it

```bash
npm run serve
```

Loads `.env`, builds the front end if it has not been built, and starts the API.
Open **http://localhost:8001**.

Override the port with `PORT=8002 npm run serve`.

### Working on the front end

```bash
npm run dev
```

Two processes: Vite with hot reload, and uvicorn for the API.

| | address | reloads on |
| --- | --- | --- |
| React (Vite) | **http://localhost:5173** ← open this one | changes under `frontend/src/` |
| API (uvicorn) | http://127.0.0.1:8001 | changes under `src/dsoa/` |

Vite proxies `/api` through to uvicorn, so the browser still sees one origin.
Stopping the script stops both. Override the API port with `API_PORT=8002 npm run dev`
(the proxy follows automatically).

> Use the hostname `localhost:5173`, not `127.0.0.1:5173` — Vite binds to the
> IPv6 loopback, so the IPv4 address will refuse the connection.

### Driving uvicorn yourself

Build the UI once, then run whatever command you like:

```bash
npm run ui:build
./.venv/bin/python -m uvicorn dsoa.api.main:app --port 8001 --env-file .env
```

### All front-end tasks

| command | what it does |
| --- | --- |
| `npm run serve` | build the UI, serve everything from one port |
| `npm run dev` | hot-reloading UI + API |
| `npm run ui:build` | build `frontend/dist` only |
| `npm run ui:install` | install front-end dependencies |
| `npm run ui:typecheck` | `tsc --noEmit` over the React app |

---

## Step 4 (optional): The local test database

To generate a connector and then actually connect it to something real:

```bash
npm install     # root task-runner dependencies (only needed for the database)
npm run up      # downloads and runs Postgres as a local process — no Docker
```

Seeded on `localhost:55432`, database `dsoa_source`, user `dsoa`, password
`dsoa_local_dev`. Stop it with `npm run down`, wipe and reseed with `npm run reset`.

Prefer Docker? `docker compose up -d postgres` uses the same seed file and the
same port. Use one or the other, not both — they compete for port 55432.

**Try it in the app:** pick the first example ("Connect a local PostgreSQL
database"), generate the connector, open the **Connection** tab, enter `dsoa` /
`dsoa_local_dev`, and run the test. You should see three tables — `customers`,
`orders`, `products` — with their primary keys.

---

## Verifying the setup

```bash
npm test                # 280 tests
npm run ui:typecheck    # front end typechecks clean
curl localhost:8001/api/health
```

A healthy server answers:

```json
{"status":"ok","llm":"AnthropicClient","live_model":true}
```

`"llm":"ScriptedClient"` with `"live_model":false` means no API key was found —
which is fine, and is what the offline demo runs on.

---

## Troubleshooting

**The page looks like the old UI, or unstyled.** The React bundle is not built.
Run `npm run ui:build`. The server deliberately falls back to the single-file UI
rather than failing when `frontend/dist` is missing.

**Port already in use.** `PORT=8002 npm run serve`. Note that a *previously
started* uvicorn keeps serving the code it loaded at startup, so an old process on
the port will keep showing an old UI no matter how often you rebuild. Find it with
`lsof -ti:8001` and stop it.

**Every request fails at extraction with a provider error.** Your API key is
rejected — commonly an exhausted credit balance. The error appears in the chat as
a red bubble; everything after extraction still works. To fall back to scripted
mode, comment the key out of `.env`, or start uvicorn without loading it:

```bash
.venv/bin/python -m uvicorn dsoa.api.main:app --port 8001
```

Note that `npm run serve` sources `.env` itself, so unsetting the variable in your
shell before calling it has no effect — the file wins.

**`npm run status` says Postgres is not running, but connections succeed.** You
have a Docker container on 55432 instead of the embedded one. `docker ps` will
show `dsoa-postgres`. Both work; only the status command is confused.

**Connection test fails with "password authentication failed".** The local
credentials are `dsoa` / `dsoa_local_dev`. The error says *authentication*, not
*timeout* — the framework distinguishes the two and only retries the latter,
because retrying a rejected password locks accounts.

**`ModuleNotFoundError: No module named 'dsoa'`.** The virtual environment is not
active: `source .venv/bin/activate` (Windows: `.venv\Scripts\activate`).

**`npm: command not found`.** Install Node.js 18+ (macOS: `brew install node`).

---

That's it — the agent pipeline, the React UI, and the test suite are all live.
For a guided walkthrough of what the app actually does, read
[GETTING_STARTED.md](GETTING_STARTED.md).
