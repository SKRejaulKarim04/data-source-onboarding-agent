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

Runs on macOS, Linux and Windows. The application code is platform-neutral —
what differs is only how you invoke the tasks.

### Two ways to run every command

The `npm run …` tasks are thin bash wrappers. Every step below is given both
ways, so pick a column and stay in it:

- **With bash** — macOS, Linux, WSL, or Windows with Git Bash on `PATH` (run
  `bash --version` to check; Git for Windows ships one).
- **Without bash** — the underlying commands, straight into PowerShell or `cmd`.

The only difference between the columns is the path separator and the venv
layout: POSIX venvs put executables in `.venv/bin`, Windows in `.venv\Scripts`.

---

## Step 1: Install

**With bash**

```bash
cd data-source-onboarding-agent
./bin/install.sh
```

**Without bash** (PowerShell)

```powershell
cd data-source-onboarding-agent
python -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pip install -e .
npm --prefix frontend install
npm --prefix frontend run build
```

Either way you end up with a virtual environment (`.venv`), the Python
dependencies, the front-end dependencies, and a built `frontend/dist`. Both are
safe to repeat.

---

## Step 2: Configure environment variables

**With bash**

```bash
cp .env.example .env
```

**Without bash** (PowerShell)

```powershell
Copy-Item .env.example .env
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

**With bash**

```bash
npm run serve                 # PORT=8002 npm run serve  to change the port
```

Loads `.env`, builds the front end if it has not been built, and starts the API.

**Without bash** (PowerShell)

```powershell
npm --prefix frontend run build          # once, or after any UI change
.venv\Scripts\python -m uvicorn dsoa.api.main:app --port 8001 --env-file .env
```

Either way, open **http://localhost:8001**.

### Working on the front end

**With bash**

```bash
npm run dev                   # API_PORT=8002 npm run dev  to change the API port
```

**Without bash** — two terminals, because the wrapper is what normally
supervises both:

```powershell
# terminal 1
.venv\Scripts\python -m uvicorn dsoa.api.main:app --port 8001 --reload --env-file .env

# terminal 2
npm --prefix frontend run dev
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

### Every task, both ways

`npm run …` needs bash. The right-hand column is what it runs, and works
anywhere Node and Python do. On macOS and Linux, swap `.venv\Scripts\` for
`.venv/bin/`.

| task | with bash | without bash |
| --- | --- | --- |
| install | `./bin/install.sh` | see Step 1 |
| serve | `npm run serve` | `.venv\Scripts\python -m uvicorn dsoa.api.main:app --port 8001 --env-file .env` |
| dev | `npm run dev` | uvicorn `--reload` + `npm --prefix frontend run dev` |
| build the UI | `npm run ui:build` | `npm --prefix frontend run build` |
| install UI deps | `npm run ui:install` | `npm --prefix frontend install` |
| typecheck the UI | `npm run ui:typecheck` | `npm --prefix frontend run typecheck` |
| tests | `npm test` | `.venv\Scripts\python -m pytest tests/` |
| lint | `npm run lint` | `.venv\Scripts\ruff check src tests eval scripts` |
| database up / down | `npm run up` / `npm run down` | `node bin/pg.js up` / `node bin/pg.js down` |
| database status / logs | `npm run status` / `npm run logs` | `node bin/pg.js status` / `node bin/pg.js logs` |

The database tasks are already plain Node, so they behave identically on every
platform.

### What genuinely differs on Windows

Two behaviours, not setup steps — worth knowing rather than discovering:

- **The connection sandbox is a weaker box.** Windows has no `rlimit` and no
  `preexec_fn`, so the memory and CPU caps do not apply; the wall-clock timeout
  and the scrubbed environment are the whole of the isolation. The child still
  runs in its own process group, so a timeout takes its descendants with it.
  Same code path everywhere, different strength — stated plainly at the top of
  `src/dsoa/sandbox/runner.py`.
- **The sandbox environment is slightly wider.** A child interpreter on Windows
  will not start without `SYSTEMROOT` and friends, so those are added to the
  allowlist. Secrets are still excluded, and a test asserts it.

---

## Step 4 (optional): The local test database

To generate a connector and then actually connect it to something real:

```bash
npm install              # root task-runner dependencies, once
npm run up               # or: node bin/pg.js up
```

`bin/pg.js` is plain Node, so `node bin/pg.js up` works identically without
bash. It downloads a real Postgres binary the first time and runs it as an
ordinary background process — no Docker, no service install, no admin rights.

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

**With bash**

```bash
npm test                 # 294 tests
npm run ui:typecheck
curl localhost:8001/api/health
```

**Without bash** (PowerShell)

```powershell
.venv\Scripts\python -m pytest tests/
npm --prefix frontend run typecheck
Invoke-RestMethod http://localhost:8001/api/health
```

`tests/test_portability.py` is the part that matters here: it asserts the
cross-platform invariants — guarded imports, explicit UTF-8, platform-correct
subprocess arguments — so a change that only breaks Windows fails on macOS too.

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
