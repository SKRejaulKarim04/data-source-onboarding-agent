# Getting Started

A walkthrough for someone who is comfortable engineering but new to web apps and LLM agents. Read it in order the first time; after that use it as a reference.

Estimated time to first working demo: **10 minutes.**

---

## Part 1 — What this thing actually is

You type this into a web page:

> *Onboard our Postgres reporting database at reporting-db.internal, database analytics, read-only.*

You get back a Python file that connects to that database, plus its README, its `requirements.txt`, a plain-English explanation, and a manifest recording exactly how it was made. All of it validated against thirteen coding standards and, optionally, tested against the live database.

That is the whole product. Everything below is how it works.

### The one idea that matters

The brief asks for two things that fight each other:

- accept free-form English
- guarantee the generated code follows fixed enterprise standards

If you let an LLM write the Python, you cannot guarantee the second. Models are creative, and creativity is the opposite of standardisation. Ask the same model twice and you get two different files.

So the LLM never writes code here. It does one job — turning English into a **structured spec** — and a Jinja2 template does the rest:

```
English  ──LLM──▶  SourceSpec  ──template──▶  Python
        understanding        mechanical substitution
```

Because the second arrow is pure substitution, the same spec always produces byte-identical code. Standards conformance stops being something you hope for and becomes something the template guarantees.

If you remember one sentence from this document, that is it. It is also the strongest thing you can say in your final presentation.

---

## Part 2 — Setup

### 2.1 What you need

| | |
|---|---|
| Python | 3.11 or newer (`python3 --version`) |
| Node.js | 18 or newer (`node --version`) — runs the task scripts and the local Postgres |
| Docker | Not required. The live database runs as a plain local process instead (see 3.4). |
| An API key | Optional. The app runs in offline mode without one. |

### 2.2 Install

```bash
cd data-source-onboarding-agent

npm run setup
source .venv/bin/activate
```

`npm run setup` creates a **virtual environment** — a private Python installation for this project so its packages do not collide with anything else on your machine — and installs the Node dependencies used by the task scripts. `source .venv/bin/activate` switches your terminal into it. You will see `(.venv)` appear in your prompt. Run it again in every new terminal.

### 2.3 Check it works

```bash
npm test
```

Expect `273 passed, 5 skipped`. The five skips are the live-database tests, which need `npm run up` running.

If that passes, the project is correctly installed. Nothing after this can fail for setup reasons.

---

## Part 3 — Run it four ways

Start with the smallest and work up. Each one shows you a different part of the system.

### Way 1 — The extractor (English → spec)

```bash
npm run demo
```

Shows a vague request being turned into a partial spec, and the agent asking about what it could not determine. Try a complete one:

```bash
python scripts/extract_demo.py --offline "Onboard our Postgres reporting DB"
```

**What to notice:** the `Assumed:` line. The agent tells you which fields it filled from convention rather than from your words. Port 5432 is a convention. A hostname is not — and the agent will never invent one.

### Way 2 — The generator (spec → validated code)

```bash
npm run generate
```

Prints a thirteen-row checklist, all PASS. Then:

```bash
npm run generate:faults
```

This deliberately corrupts the generated code — inserts a hardcoded password, a `print()`, an `eval()`, an f-string SQL query, a bare `except` — and shows the validator catching each one.

**Why this matters more than the passing run:** a checker that has only ever seen good input has demonstrated nothing. You know this instinct already from verification — a testbench that never fails is a testbench you cannot trust. Same principle.

### Way 3 — The web app

```bash
npm run serve
```

Open **http://localhost:8001**.

The page is a React + TypeScript app (`frontend/`). `npm run serve` builds it the
first time and then serves it from the same FastAPI process as the API. If you
are changing the UI, run `npm run dev` instead — Vite gives you hot reload on
**http://localhost:5173** and proxies `/api` through to uvicorn on `:8001`.

Three example requests are built into the page. Click through them in order:

1. **Complete request** — extracts cleanly, generate immediately.
2. **Incomplete** — the agent asks for the missing host. Answer it, then generate.
3. **Adversarial** — a pasted password. Watch the red banner appear and check that the password never comes back in any response.

The five-stage rail across the top fills in as you go: Request → Spec → Generate → Validate → Connect.

### Way 4 — Against a real database

```bash
npm run up                     # starts Postgres as a local process (no Docker), seeded with 3 tables
set -a && . ./.env && set +a   # loads the connection settings
npm run smoke                  # proves the hand-written connector works
```

Then in the web app, use the first example (it points at this local database), generate the connector, open the **Connection** tab, enter:

- `DSOA_..._USERNAME` → `dsoa`
- `DSOA_..._PASSWORD` → `dsoa_local_dev`

and press **Run connection test**. You will see the real schema come back — the tables, their columns, their primary keys — read by code that did not exist sixty seconds ago.

That is the moment worth demoing.

---

## Part 4 — How the pieces fit

```
        YOU TYPE ENGLISH
               │
    ┌──────────▼───────────┐
    │  agent/security.py   │  redact pasted credentials, flag injection
    └──────────┬───────────┘
    ┌──────────▼───────────┐
    │  agent/extractor.py  │  ask the LLM for a structured spec
    │  agent/spec.py       │  the contract everything else agrees on
    └──────────┬───────────┘
               │ incomplete?
    ┌──────────▼───────────┐
    │  agent/clarify.py    │  ask the user, fold the answers back in
    └──────────┬───────────┘
    ┌──────────▼───────────┐
    │  templates/          │  Jinja2 → Python. No LLM on this path.
    └──────────┬───────────┘
    ┌──────────▼───────────┐
    │  standards/checks.py │  13 checks, reading the AST
    │  validation/static.py│  + ruff, black, bandit
    │  validation/repair.py│  only if something failed
    └──────────┬───────────┘
    ┌──────────▼───────────┐
    │  sandbox/runner.py   │  connect for real, in an isolated process
    │  docs_gen/           │  README, requirements, explanation
    │  artifacts/          │  zip it with a manifest
    └──────────┬───────────┘
               ▼
        DOWNLOADABLE BUNDLE
```

### Reading the code, in the right order

Do not start at the top. Start where the contract is defined:

1. **`agent/spec.py`** — `SourceSpec` and `SpecDraft`. Everything upstream produces one, everything downstream consumes one. Understand this file and the rest follows.
2. **`connectors/base.py`** — the five methods every connector implements.
3. **`connectors/postgresql.py`** — the hand-written reference, about forty lines. This is what the template aims at.
4. **`templates/files/sql_connector.py.j2`** — the template. Diff it mentally against step 3; they are nearly the same file.
5. **`standards/checks.py`** — the thirteen rules, as functions.
6. **`api/main.py`** — how it all gets exposed over HTTP.

---

## Part 5 — Concepts you may not have met

**Virtual environment** — a private Python install per project. `npm run setup` makes one, `source .venv/bin/activate` enters it.

**Pydantic model** — a class that validates its own data. Assign a bad value and it raises immediately rather than failing three layers later. `SourceSpec` is one; that is why an invalid spec cannot reach a template.

**AST (Abstract Syntax Tree)** — Python's parsed representation of source code. The validator reads the AST rather than importing the module, because **importing runs the code**, and running code you have not yet vetted is the exact thing the validator exists to prevent.

**Jinja2 template** — a text file with `{{ placeholders }}`. Feed it data, get text out. Purely mechanical, which is why it is trustworthy for code generation.

**FastAPI** — the Python web framework here. A function decorated with `@app.post("/api/requests")` becomes an HTTP endpoint. It generates its own interactive docs; visit http://localhost:8001/docs while the server runs.

**Structured output / tool use** — instead of asking a model to "reply with JSON" and hoping, you give it a schema and the API enforces it. Removes a whole class of parsing bugs. See `agent/llm.py`.

**Fixtures (pytest)** — reusable setup for tests. A function marked `@pytest.fixture` can be requested by name in any test.

---

## Part 6 — Every command

```bash
npm run            # this list, from the terminal (no arg = list scripts)

# Setup
npm run setup           # venv + Python + Node dependencies
npm run up               # start the seeded local Postgres (no Docker)
npm run down             # stop it (keeps data)
npm run reset            # stop it and wipe the data, forcing a reseed
npm run psql             # open a SQL shell against it
npm run status           # is it running?
npm run logs             # tail the Postgres log

# Run
npm run serve            # web app on http://localhost:8001 (builds the UI if needed)
npm run dev              # UI with hot reload on :5173 + API on :8001
npm run ui:build         # build frontend/dist only
npm run ui:typecheck     # tsc --noEmit over the React app
npm run demo             # Phase 2: extraction walkthrough
npm run generate         # Phase 3: generation + standards checklist
npm run generate:faults  # Phase 3: fault injection
npm run smoke            # Phase 1: live connector proof (needs npm run up)

# Check
npm test                 # everything
npm run test:unit        # fast, no Postgres needed
npm run test:integration # live database tests only
npm run lint             # ruff + black
npm run fmt              # auto-fix formatting
npm run eval:offline     # exercise the eval harness
npm run eval             # score extraction against 30 golden prompts (needs a key)
```

---

## Part 7 — Using a real model

Everything above works with no API key: `ScriptedClient` serves canned responses through the same interface the real client uses, so the whole pipeline runs offline.

To use a live model:

```bash
export ANTHROPIC_API_KEY="your-key"
npm run serve
```

The header will switch from `offline mode` to `live model`.

Then score the extraction quality:

```bash
npm run eval
```

This runs thirty prompts — clean, incomplete, ambiguous, and adversarial — and reports four numbers. Put them in your final presentation:

| Metric | Target | What it measures |
|---|---|---|
| Field accuracy | > 90% | ordinary extraction quality |
| **Hallucination rate** | **< 5%** | **how often it invented a hostname** |
| Clarification recall | > 90% | gaps it should have asked about |
| Security pass rate | 100% | credential leaks, injection, unsupported sources |

Hallucination rate is the interesting one. Field accuracy is easy to score well on. Not inventing a plausible-looking hostname when the user never gave you one is hard, and it is the difference between a usable agent and a confident liar.

---

## Part 8 — When something breaks

**`npm: command not found`** — install Node.js 18+ (macOS: `brew install node`; Windows: the [Node installer](https://nodejs.org) or `winget install OpenJS.NodeJS.LTS`; Ubuntu: `sudo apt install nodejs npm`). Or open `bin/*.sh` / `bin/pg.js` and run the commands inside directly — they're plain bash and Node, nothing `npm` hides from you.

**`ModuleNotFoundError: No module named 'dsoa'`** — the virtual environment is not active. Run `source .venv/bin/activate` (on Windows: `.venv\Scripts\activate`).

**Connection refused on 55432** — the local Postgres process isn't running. Run `npm run status` to check, then `npm run up`. It downloads a real Postgres binary the first time (needs network access once), then runs it as a plain background process — no Docker daemon or elevated permissions required. `npm run logs` shows its output if `up` hangs.

**`ConfigurationError: Missing required environment variables`** — run `set -a && . ./.env && set +a` in the terminal you are using. Environment variables do not carry between terminals.

**Port 8001 already in use** — `PORT=8002 npm run serve`.

**The page loads but looks unstyled, or `/` shows the older single-file UI** — the
React bundle has not been built. Run `npm run ui:build`. Without Node.js the
server intentionally falls back to `src/dsoa/api/static/index.html`, so the app
still works, it just isn't the React one.

**Connection test fails with "password authentication failed"** — the username and password for the local database are `dsoa` / `dsoa_local_dev`. Note the error says *authentication*, not *timeout* — the framework distinguishes them, and only retries the second, because retrying a rejected password locks accounts.

---

## Part 9 — Presenting this

A ten-minute demo that works:

1. **The problem** (1 min). Data teams hand-write connectors. Repetitive, inconsistent, error-prone.
2. **The tension** (1 min). Free-form English versus guaranteed standards. Explain why letting the LLM write code fails.
3. **Live: the happy path** (2 min). Type a request, watch the rail advance, show the thirteen green checks.
4. **Live: the clarification** (2 min). Vague request. The agent asks instead of guessing. *This is the differentiator* — most projects in this space hallucinate the gap.
5. **Live: the adversarial case** (1 min). Paste a password. Show it redacted, show it absent from the artifact.
6. **Live: fault injection** (1 min). `npm run generate:faults`. Five faults, five catches.
7. **Live: the real connection** (1 min). Connect to Postgres, show the schema.
8. **The numbers** (1 min). Eval table. Time-to-onboard versus writing one by hand.

Two things to say out loud that will land with an engineering audience:

- *"The model never writes code. It writes a spec. The template writes the code. That is why conformance is 100% and not 80%."*
- *"The validator is tested by fault injection, not by passing code. A checker that has only ever seen good input has demonstrated nothing."*

---

## Part 10 — What is left

The project covers Phases 0 through 6 of the original plan. Genuine remaining work, worth listing as future scope:

- **REST API connectors.** The spec models them and the registry has a slot; the `RestBaseConnector` framework class is not written. Three SQL dialects are complete.
- **Persistence.** Requests live in memory and vanish when the server restarts. `RequestStore` in `api/main.py` has five methods — swapping it for Postgres is contained.
- **Container isolation.** `sandbox/runner.py` gives process isolation, timeouts, memory caps, and a scrubbed environment. Production wants that same runner inside a locked-down container. The interface does not change.
- **Auth.** No login. Fine for a capstone, not for a deployment.

Being straight about these in your presentation reads as engineering judgement, not as gaps.
