# Data Source Onboarding Agent

An AI agent that turns a plain-English request — *"onboard our Postgres analytics DB at reporting.internal, read-only, service account in env"* — into a validated, standards-compliant, versioned Python connector plus its onboarding documentation.

**Complete.** All six phases built. New here? Read **[GETTING_STARTED.md](GETTING_STARTED.md)** instead — it walks through setup and the demo step by step.

Other docs: **[SETUP.md](SETUP.md)** to install and run · **[WORKFLOW.md](WORKFLOW.md)** for the execution map — what runs, in what order, calling what, from the browser to the downloaded zip.

---

## Quick start

```bash
git clone <your-repo> && cd data-source-onboarding-agent

npm run setup                     # venv + Python dependencies
source .venv/bin/activate

cp .env.example .env
set -a && . ./.env && set +a      # export the DSOA_PG_* variables

npm run up                        # start + seed Postgres on localhost:55432 (no Docker needed)
npm test                          # 280 tests
npm run smoke                     # Phase 1: live connector proof
npm run demo                      # Phase 2: extraction walkthrough
npm run generate                  # generation + standards checklist
npm run generate:faults           # fault injection
npm run serve                     # web app on http://localhost:8001
```

The web app is a React + TypeScript single-page app (`frontend/`) served by the
same FastAPI process as the API, so there is one origin and no CORS. `npm run
serve` builds it on first run. While working on the UI, use `npm run dev`
instead: uvicorn on `:8001` and Vite with hot reload on `:5173`, proxying `/api`
to uvicorn.

| task | what it does |
| --- | --- |
| `npm run serve` | production-ish: build the UI, serve everything from `:8001` |
| `npm run dev` | hot-reloading UI on `:5173` + API on `:8001` |
| `npm run ui:build` | build `frontend/dist` only |
| `npm run ui:typecheck` | `tsc --noEmit` over the front end |

Task orchestration is plain `bash` scripts under `bin/`, wired up as `npm run` targets in `package.json` — there is no `make` dependency. Postgres runs as a local process managed by Node's `embedded-postgres` package (`bin/pg.js` / `bin/pg-daemon.js`), so it works without Docker or any special permissions.

### Without a real Postgres/Docker install, or an API key

`npm run up` already avoids Docker — it downloads a real Postgres binary once and runs it as a plain background process (see `bin/pg-daemon.js`). Beyond that, everything except five Postgres-dialect tests runs with nothing installed and nothing running. The connector tests use in-memory SQLite; the agent tests use `ScriptedClient`, which serves canned payloads through the same `LLMClient` protocol the real provider uses. `npm run demo` and `npm run eval:offline` both work on a plane.

To score extraction against a live model, export `ANTHROPIC_API_KEY` and run `npm run eval`.

---

## Why there is no AI in this repo yet

The brief asks for two things in tension: free-form natural language input, and *"generated connectors follow predefined enterprise coding standards."* If the model free-writes Python you get variety, which is the opposite of standardization.

The resolution is spec-first generation:

```
Natural language  ──LLM──►  SourceSpec (validated)  ──Jinja2──►  Connector
                                                        ▲
                                    LLM fills only bounded blocks:
                                    query logic, pagination, docstrings
```

Structure comes from templates; understanding and explanation come from the model. Standards are then enforced *by construction* rather than by hope.

That plan has a prerequisite: the templates must render toward something. `src/dsoa/connectors/postgresql.py` is that something — written by hand, reviewed, and tested, so the Phase 3 validator has a concrete standard to judge generated code against. Build the target before building the generator.

---

## Current structure

```
.
├── docker/postgres/01_seed.sql     3 tables, 1 view, FKs, a read-only role (seeds the embedded Postgres too)
├── package.json                    npm run <task> — replaces the old Makefile
├── bin/                            bash + Node.js task scripts (install, test, lint, pg.js, ...)
├── pyproject.toml                  ruff + black + pytest config
├── .env.example                    credentials live here, never in code
│
├── src/dsoa/
│   ├── logging_config.py
│   └── connectors/
│       ├── __init__.py             public surface — generated code imports only this
│       ├── base.py                 BaseConnector ABC: the contract
│       ├── sql_base.py             SQLAlchemy engine, safe reads, error translation
│       ├── postgresql.py           reference implementation (~40 lines)
│       ├── config.py               SqlConnectionConfig — secrets from env only
│       ├── models.py               ConnectionTestResult, TableSchema, ColumnSchema
│       ├── retry.py                exponential backoff, transient errors only
│       └── exceptions.py           one vocabulary across all source types
│
│   ├── generation.py               spec -> render -> validate -> repair
│   ├── api/                        FastAPI app; serves frontend/dist, falls back to static/index.html
│   ├── sandbox/runner.py           isolated execution of generated code
│   ├── docs_gen/                   README, requirements, explanation
│   ├── artifacts/                  versioned zip bundles + manifest
│   ├── templates/
│   │   ├── registry.py             dialect profiles + versioned registry
│   │   ├── renderer.py             deterministic Jinja2 rendering
│   │   └── files/sql_connector.py.j2
│   ├── standards/
│   │   ├── checks.py               13 AST checks — the enterprise rules
│   │   └── models.py               Finding, Severity, ValidationReport
│   ├── validation/
│   │   ├── static.py               AST + ruff + black + bandit
│   │   └── repair.py               bounded loop with a regression guard
│   └── agent/
│       ├── spec.py                 SourceSpec + SpecDraft — the contract
│       ├── extractor.py            NL -> draft, with graceful degradation
│       ├── clarify.py              templated question library
│       ├── security.py             credential scrubbing, injection detection
│       ├── prompts.py              versioned prompt + tool schema
│       └── llm.py                  LLMClient protocol, Anthropic + Scripted
│
├── frontend/                       React + Vite + TypeScript UI
│   ├── src/api/                    client.ts (one fetch wrapper) + types.ts (mirrors the API)
│   ├── src/hooks/                  useOnboarding (all app behaviour), useResizer, useHealth
│   ├── src/components/             Header, Sidebar, chat/, output/ (one file per tab)
│   ├── src/styles/                 tokens.css, base.css, primitives.css
│   └── dist/                       build output, served by FastAPI at /
│
├── eval/
│   ├── golden_prompts.yaml         30 cases: clean, incomplete, ambiguous, adversarial
│   └── runner.py                   field accuracy, hallucination rate, recall
│
├── tests/                          280 tests
└── scripts/
    ├── smoke_test.py               Phase 1 gate
    ├── extract_demo.py             Phase 2 walkthrough
    └── generate_demo.py            Phase 3 walkthrough + fault injection
```

### Target structure (end of Phase 6)

```
src/dsoa/
├── connectors/          ← done
├── agent/               nodes.py graph.py spec.py prompts.py
├── templates/           postgresql.py.j2 mysql.py.j2 sqlserver.py.j2 rest.py.j2
├── standards/           checks.py profiles.py
├── validation/          static.py sandbox.py
├── docs_gen/            readme.py explain.py dependencies.py
├── registry/            templates.py versioning.py
└── api/                 main.py routes/ schemas.py
frontend/                React + Vite + TS
eval/                    golden_prompts.yaml runner.py
```

---

## The contract

Every connector — hand-written or generated — implements five methods:

| Method | Returns | Note |
|---|---|---|
| `_create_connection()` | engine | called lazily, verified eagerly |
| `_dispose(conn)` | — | idempotent |
| `describe_target()` | `str` | credential-free, safe to log |
| `test_connection()` | `ConnectionTestResult` | **never raises** — failure is data the agent reads |
| `fetch_schema()` | `Sequence[TableSchema]` | |
| `read(query, params)` | `list[dict]` | bound parameters only |

Adding a dialect is four class attributes and one hook:

```python
class PostgresqlConnector(SQLBaseConnector):
    source_type = "postgresql"
    driver = "postgresql+psycopg"
    default_port = 5432
    version_query = "SELECT version()"

    def _connect_args(self) -> dict[str, Any]:
        return {"connect_timeout": ..., "sslmode": ..., "application_name": ...}
```

That thinness is the deliverable. When the agent generates a MySQL connector in Phase 3, this is the shape of what it has to produce.

---

## Standards enforced today

These become machine-checked assertions in `standards/checks.py` in Phase 3. Right now they're enforced by ruff config and tests.

- [x] Subclass of `BaseConnector` implementing every abstract method
- [x] Zero hardcoded credentials — `SecretStr` + `from_env()` only
- [x] Type hints on all public methods (ruff `ANN`)
- [x] Module, class, and method docstrings
- [x] Structured logging, no `print()`
- [x] Explicit exception types, no bare `except:`
- [x] Context manager support — connections always closed
- [x] Retry with backoff on transient errors only
- [x] Parameterized queries; f-string SQL is impossible via `read()`
- [x] Multi-statement and write payloads rejected before reaching the server
- [x] `ruff` and `black` clean

Test evidence: `test_parameter_binding_neutralises_injection`, `test_password_never_appears_in_repr_or_dump`, `test_comment_smuggling_is_rejected`, `test_auth_errors_are_not_retried`.

---

## Roadmap

| Phase | Deliverable | Status |
|---|---|---|
| 0 | Repo, compose, CI, tooling | done |
| 1 | Connector framework + Postgres reference | done |
| 2 | `SourceSpec`, NL extraction, clarification loop | done |
| 3 | Jinja2 templates, static validator, repair loop | done |
| 4 | Sandboxed connection testing, versioned artifacts | done |
| 5 | Generated docs, dependencies, code explanation | done |
| 6 | Web frontend, activity log, eval report | done |

**Remaining scope**, worth naming honestly rather than hiding:

- **REST connectors.** The spec models them and the registry has a slot, but `RestBaseConnector` is unwritten. Three SQL dialects are complete.
- **Persistence.** Requests live in memory. `RequestStore` has five methods; swapping it for Postgres is contained.
- **Container isolation.** `sandbox/runner.py` gives process isolation, timeouts, memory caps, and a scrubbed allowlisted environment. Production wants that same runner inside a locked-down container — the interface does not change, only the wrapper.
- **Auth.** No login.

---

## How generation works

```
SourceSpec
  -> registry      resolve template_key -> versioned template + dialect profile
  -> render        Jinja2, StrictUndefined, deterministic
  -> validate      parse -> 13 AST checks -> ruff -> black -> bandit
  -> repair        only if validation failed, max 3 bounded iterations
  -> artifact      code + report + provenance + semver
```

**The LLM writes no code on this path.** Rendering is pure template substitution, so the same spec and template version produce byte-identical output every time — which is what makes the checksum meaningful and standards conformance structural rather than probabilistic. The model's job ended at Phase 2, when it produced the spec.

**Validation never imports the candidate.** Every check reads the AST. Importing a module executes its top-level code, so a validator that imports what it is validating has already run the thing it was meant to vet. Execution happens exactly once, in the Phase 4 sandbox. `test_validation_never_imports_the_candidate` asserts this.

**The repair loop cannot make things worse.** Each iteration is accepted only if it strictly reduces the error count; otherwise the previous candidate is kept and the loop stops. Without that guard, a model that fixes one error while introducing two will oscillate until the cap and ship whichever attempt happened to be last.

**Lint findings are warnings, not errors.** Promoting every ruff nit to blocking would send the repair loop chasing whitespace instead of fixing hardcoded credentials.

## Standards, machine-checked

Thirteen checks in `standards/checks.py`, each one a bullet from the list above turned into a function:

| Check | Severity |
|---|---|
| subclasses-base-connector | error |
| class-naming | error |
| declares-source-type | error |
| no-hardcoded-credentials | error |
| env-for-secrets | error |
| no-dynamic-sql | error |
| no-dangerous-calls | error |
| no-print | error |
| no-bare-except | error / warning |
| no-wildcard-imports | error |
| type-hints | error |
| docstrings | error |
| no-todo-markers | warning |

**These are tested by fault injection, not by passing code.** `tests/test_standards.py` takes one conforming module and mutates it in twenty specific ways — a hardcoded password, an f-string query, an `eval`, a bare except — and asserts each fault is caught by name. A validator that has only ever seen clean code has demonstrated nothing.

`npm run generate:faults` runs the same idea live:

```
CAUGHT  hardcoded credential -> no-hardcoded-credentials
CAUGHT  print statement      -> no-print
CAUGHT  dangerous call       -> bandit:B307, no-dangerous-calls
CAUGHT  dynamic SQL          -> bandit:B608, no-dynamic-sql
CAUGHT  bare except          -> no-bare-except
```

---

## How extraction works

```
raw prompt
  -> scrub          redact credentials, flag injection
  -> fence          mark as data, not instruction
  -> LLM            structured tool call, temperature 0, all fields nullable
  -> SpecDraft      nulls preserved
  -> defaults       conventional values only, each one recorded
  -> questions      for whatever is still missing
```

Two rules carry most of the weight:

**Nulls are preserved.** The tool schema makes every field nullable, and the prompt says a null is a useful signal. A model forced to emit a hostname will emit a plausible one. `test_apply_defaults_never_invents_a_hostname` locks this in: a default port is a convention, a hostname is knowledge.

**Questions are templated, not generated.** `clarify.py` holds one fixed question per field with fixed options. A model asked to phrase its own questions will sometimes ask about something it already knows, or ask two things at once. The model decides *what* is missing; the library decides *how* to ask. Answers then fold back in with no second model call.

## Evaluation

`eval/golden_prompts.yaml` holds 30 cases across four categories. The balance is deliberate — a set of only clean prompts measures nothing, since every model handles "connect to Postgres at host X, database Y".

| Metric | Target | What it catches |
|---|---|---|
| Field accuracy | > 90% | ordinary extraction quality |
| **Hallucination rate** | **< 5%** | **invented hostnames — the metric that matters** |
| Clarification recall | > 90% | gaps the agent should have asked about |
| Security pass rate | 100% | credential leaks, injection, unsupported sources |

Hallucination rate is the one to put on a slide. A wrong hostname is caught at connection time; a confidently invented one wastes a reviewer's afternoon.

---

## Notes for later

- `SqliteConnector` in `conftest.py` is the proof that the extension points work without a network. Keep it — Phase 3 can reuse it as a fixture for testing generated code.
- The `dsoa_reader` role in the seed SQL exists so generated connectors can demonstrate least privilege. Worth one slide in the final presentation.
- Host port is 55432, not 5432, to avoid colliding with a local Postgres install.
- `test_connection()` returning a result object rather than raising is load-bearing for Phase 3 — the repair loop needs to read the failure text and feed it back to the model.
