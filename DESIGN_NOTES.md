# Design Notes

Answers to the questions a reviewer actually asks, with the mechanism, the file
it lives in, and — where the honest answer is "not yet" — what it would take.

Companion docs: **[WORKFLOW.md](WORKFLOW.md)** for the execution map,
**[README.md](README.md)** for the architecture argument, **[SETUP.md](SETUP.md)**
to run it.

Line numbers were checked against the working tree when written; the call order
and the mechanisms are the durable part.

---

## Understanding

### How does the agent identify source type?

Three layers, in descending order of trust.

**The model proposes, but only from a closed set.** `source_type` is an enum in
the tool schema handed to the model, so it selects a member rather than emitting
a string. It cannot return "postgres-ish" or "our warehouse".

**When it cannot tell, the field stays `None`.** Every field on `SpecDraft` is
optional exactly so the model is never forced to invent a value it did not read
([`agent/spec.py:307`](src/dsoa/agent/spec.py#L307)) — the single most common
failure mode in natural-language-to-structure extraction.

**Missing source type short-circuits everything else.**
[`required_fields()`](src/dsoa/agent/spec.py#L338) returns `("source_type",)` and
nothing else until the engine is known. There is no point asking about ports
before you know what you are connecting to. The clarification library then asks
a closed-option question built from the enum itself.

Name something unsupported — Oracle today — and the model sets
`unsupported_request`; the UI reports it and lists what is available.

The identification always resolves to a `SourceType` member, and that enum is
*generated from `sources.json` at import time*
([`agent/spec.py:38`](src/dsoa/agent/spec.py#L38)) rather than hand-written.

> **Possible addition.** Confidence is a single scalar for the whole extraction.
> Per-field confidence would let the agent re-ask about the one shaky field
> instead of treating the entire draft as suspect.

### How are connector templates managed?

[`TemplateRegistry`](src/dsoa/templates/registry.py#L110), keyed
`source_type:auth_method`, with each entry carrying its template filename,
**version**, and description. Dialect differences live in `DialectProfile` data
loaded from `sources.json`, not in branching inside the templates.

A lookup miss raises `ConfigurationError` **listing the supported keys** — an
error that tells you what you could have asked for instead of just what failed.

Registered today:

```
postgresql:username_password
mysql:username_password
sqlserver:username_password
rest_api:none
```

Versioning is the point: an artifact generated in March against template v1.0.0
must stay explicable in October when the template is at v1.4.0.

> **Possible additions.**
> - The built-in set comes from a hardcoded `_sql_entries()`. Front-matter in
>   each `.j2` (key, version, target, required spec fields) plus a directory scan
>   at registry construction would make adding a template a file-drop, reflected
>   by `/api/templates` without a restart.
> - No test asserts that every `SourceType × AuthMethod` pair either has a
>   template or is explicitly unsupported. That gap is how an enum value nobody
>   can use gets shipped.
> - A golden-output test per template, so a template edit cannot silently change
>   every future artifact.

### How are authentication methods handled?

**Auth is part of the template key**, not a runtime branch inside one template.
Selecting `username_password` selects a different template rather than a
different code path, which keeps each template linear and reviewable.

[`AuthSpec.secret_env_vars`](src/dsoa/agent/spec.py#L216) derives the exact
variable names the generated connector will read, from `env_prefix` plus the
method's secret fields — `DSOA_ANALYTICS_USERNAME`, `DSOA_ANALYTICS_PASSWORD`.
[`valid_for_sql`](src/dsoa/agent/spec.py#L61) constrains which methods are
coherent for a database at all.

Honest state: the `AuthMethod` enum has six values; **two have templates**.
`api_key_header`, `bearer_token`, `basic` and `oauth2_client_credentials` are
modelled but unimplemented. Requesting one produces a clean `ConfigurationError`,
not a broken connector.

> **Possible addition.** OAuth2 client-credentials needs token caching and
> refresh — state the current connector shape has nowhere to keep. That is a
> design task, not a template.

---

## Design

### What is the fallback when the AI generates incorrect code?

**The premise does not hold, and that is the architecture's central claim: the
model never generates the code.** [`template.render()`](src/dsoa/templates/renderer.py#L85)
does. The model fills a spec. So "incorrect code" can only originate in a bad
template or a bad spec — both of which are reviewable artifacts rather than
probabilistic output.

Behind that, six layers:

1. **Deterministic rendering.** Same spec, same bytes.
2. **13 AST checks** ([`standards/checks.py:445`](src/dsoa/standards/checks.py#L445)).
   The source is parsed, never imported — importing runs the code, which is the
   exact thing the validator exists to prevent.
3. **ruff, black, bandit** as subprocesses. A missing tool becomes
   [`tools_skipped`](src/dsoa/validation/static.py#L94) and surfaces as a
   warning; it never silently counts as a pass.
4. **A bounded repair loop with a regression guard**
   ([`validation/repair.py:125`](src/dsoa/validation/repair.py#L125)). At most
   three iterations, and a candidate is adopted only if it *strictly* reduces the
   error count. The returned code is never worse than the input.
5. **Sandboxed execution** against the real target — the only place generated
   code actually runs.
6. **Rejection is a rendered outcome.** Still failing means `accepted=false` and
   the artifact is returned anyway, with findings, so the UI can show what went
   wrong.

And `npm run generate:faults` deliberately corrupts the output — a hardcoded
password, a `print()`, an `eval()`, an f-string SQL query, a bare `except` — to
prove each check fails on cue. A checker that has only ever seen good input has
demonstrated nothing.

> **Possible addition.** The repair loop trusts the checker completely. A fix
> that satisfies an AST rule while quietly altering the SQL would be accepted.
> Constraining a repair to the lines implicated by the findings would close that.

### How does versioning work?

Four independent identities, all recorded in the artifact manifest.

| identity | pins | produced by |
| --- | --- | --- |
| `template_version` | which template shape produced this | registry entry |
| `spec_checksum` | the normalized request it came from | [`renderer.py:53`](src/dsoa/templates/renderer.py#L53) |
| `code_checksum` | the exact bytes emitted | sha256 of the code |
| artifact `semver` | `major.minor` from the template, **patch = repair count** | [`generation.py:53`](src/dsoa/generation.py#L53) |

So `1.0.2` reads as: template 1.0, needed two repair passes. A connector that
struggled to render is distinguishable at a glance from one that came out clean.

`Artifact.to_zip()` writes a fixed timestamp rather than the clock, so packaging
the same artifact twice produces identical bytes — the same reproducibility
argument as the code checksum.

Together these answer the question that actually matters six months later: *why
does this connector in production behave this way?* The chain is
request → spec → template version → code checksum → artifact version.

> **Possible addition.** Nothing pins the **model**. Two artifacts with identical
> `spec_checksum` produced by different model versions are indistinguishable
> today. Record the model id and `PROMPT_VERSION` in provenance.

### How is generated code stored?

Honestly: **it is not, durably.** [`RequestStore`](src/dsoa/api/main.py#L81) is a
dict in process memory and the zip is built on demand. Restart the server and
every request, connector and artifact is gone.

That is deliberate and documented at the top of `api/main.py`: the brief's
Postgres is the *onboarded source*, not the application's own store, and adding
SQLAlchemy models plus migrations to wrap a dictionary would be ceremony without
benefit at this stage.

> **Possible addition.** The swap is contained — the rest of the app only sees
> five methods on `RequestStore`. Real persistence wants:
> - artifacts in object storage **keyed by `code_checksum`** — content-addressed,
>   so byte-identical output deduplicates for free;
> - request and artifact metadata in Postgres;
> - `GET /api/artifacts/{checksum}` for provenance lookups.
>
> That is the point at which "which connector is running in production, and what
> request produced it" becomes an answerable question rather than an argument.

---

## Security

### How are secrets and passwords handled?

Four boundaries, none of which depend on the model behaving well.

**At input.** [`scrub()`](src/dsoa/agent/security.py#L132) redacts credentials
before the prompt reaches the model, and the *stored* prompt is overwritten with
the scrubbed copy ([`api/main.py:362`](src/dsoa/api/main.py#L362)). Scrubbing at
the boundary alone was not enough — the record itself has to hold the clean copy,
or a pasted password survives in every later response for that request.

**In generated code.** Two AST checks — `no-hardcoded-credentials` and
`env-for-secrets` — make a literal credential a **rejection**. The guarantee is
structural rather than a convention someone has to remember.

**In the manifest.** [`required_env`](src/dsoa/artifacts/packager.py#L136)
records variable **names only**. A manifest carrying values would defeat the
entire design.

**At runtime.** The connector reads from the environment in `from_env()`.

### Are credentials stored, or used temporarily?

Temporary, and never written anywhere.

- `TestRequest.credentials` is documented as transient and exists only for the
  duration of one call.
- [`_child_env()`](src/dsoa/sandbox/runner.py#L224) builds the sandbox
  environment from an **allowlist** — `PATH`, `LANG`, `LC_ALL`, `PYTHONPATH`,
  `HOME`, plus only variables matching this spec's prefix. Allowlist rather than
  denylist, because a denylist exposes every newly added secret until someone
  remembers to add it, which is exactly the kind of thing nobody remembers.
- A credential with the wrong prefix is dropped, and the log line records the
  **key name only, never the value**.
- They are dropped when the call returns. Nothing persists them.
- On the browser side the credential form is keyed by request id, so switching
  requests unmounts it and discards what was typed. Nothing touches
  `localStorage`.

> **Possible additions, in the order I would do them.**
> 1. **Authentication and authorization on the API.** There is none. Anyone who
>    can reach the port can generate connectors and run connection tests against
>    internal hosts. This is the largest gap in the project.
> 2. **An audit trail** — who tested which target, when, with which artifact.
>    The first compliance question anyone asks of an enterprise onboarding tool.
> 3. **Egress control.** A generated connector can currently open a socket
>    anywhere. The sandbox gives process isolation, not kernel isolation, and
>    `sandbox/runner.py` says so plainly rather than pretending otherwise. The
>    production shape is the same runner inside a container: non-root, read-only
>    filesystem, egress allowlisted to the target host. The interface does not
>    change; only the wrapper does.
> 4. **Secret-manager integration** so `from_env()` can be pointed at Vault or a
>    cloud secret store instead of raw environment variables.

---

## Scalability

### How easy is it to add Oracle or Snowflake later?

**Oracle is close to a config edit.** `SourceType` is generated from
`sources.json`, `DIALECTS` is built from the same file, and `_sql_entries()`
creates a registry entry for every SQL dialect automatically. One JSON entry
yields the enum member, the dialect profile, the clarifying-question option and
the template key — with no Python change. Add the driver to `requirements.txt`
and it works.

```jsonc
"oracle": {
  "is_sql": true,
  "default_port": 1521,
  "dialect": {
    "label": "Oracle",
    "driver": "oracle+oracledb",
    "version_query": "SELECT banner FROM v$version",
    "driver_package": "oracledb>=2.0"
  }
}
```

**Snowflake is not that easy, and it would be misleading to say otherwise.**

| obstacle | why it does not fit today |
| --- | --- |
| Addressing | Oracle uses a service name / DSN and Snowflake an account identifier — neither is the `host / port / database` triple `SqlConnectionConfig` assumes |
| Warehouse & role | Snowflake needs both; there is no field for either |
| Authentication | Real-world Snowflake is key-pair or SSO. Neither is `username_password`, so it needs a **new `AuthMethod` and its own template** |

So: **Oracle ≈ configuration; Snowflake ≈ configuration + a new auth method +
a template.** Worth saying plainly, because "just add a row" would be wrong.

### Can new templates be plugged in without code changes?

Partly, and the distinction is worth being precise about.

| what you are adding | code change needed |
| --- | --- |
| A new SQL dialect | **No** — `sources.json` only |
| A new template for an existing shape | Small — drop the `.j2`, add a `TemplateEntry`. [`register()`](src/dsoa/templates/registry.py#L140) exists for exactly this, but the built-in set is still assembled in code |
| A new source family (GraphQL, gRPC, object storage) | **Yes** — new template, probably new spec fields, probably new checks |

> **Possible addition.** Front-matter in each `.j2` plus a directory scan at
> registry construction would make the middle row a file-drop too.

---

## Cross-cutting, not yet asked

**Concurrency.** Module-level singletons plus an in-memory store means the app is
effectively **single-worker**. Running `uvicorn --workers 4` today produces four
disjoint request histories and a confusing bug report. Worth fixing before any
real deployment, and it falls out of the persistence work above.

**Cost and latency budget.** One request is 1 extraction call, up to 3 repair
calls, and 1 documentation call. There is no per-request ceiling, so a
pathological repair loop is a billing event. A budget in the request object, and
a hard cap, are cheap insurance.

**Evaluation coverage.** `eval/golden_prompts.yaml` scores extraction across 30
cases. Each new source type needs cases added, or the eval quietly measures a
shrinking fraction of what the agent supports.

**Observability.** There is an activity log per request, which is good for a demo
and insufficient for an operator. Structured events keyed by request id, with
timings per stage, would make "why did that take 40 seconds" answerable.

---

## Where this could go next

The substantial next phase is **generating MCP servers as a second output
target** — describe a database in English, receive a read-only MCP server that
any AI client can query, gated by the same standards pipeline. The architecture
already fits: the registry is versioned and pluggable, the checks are a list, and
the sandbox already spawns a subprocess and parses structured JSON from its
stdout, which is most of what speaking MCP over stdio requires.

The design decision that phase turns on: `template_key` currently encodes two
dimensions (`source_type:auth_method`), and output target is a third. Appending
it to the key string would silently reinterpret every manifest already produced,
so the target belongs as a separate registry dimension with `connector` as the
default.

That work also needs checks a connector does not: a tool's docstring *is* the
description the model reads, an unbounded `SELECT` fills a context window rather
than crashing, and a `query(sql: str)` tool hands arbitrary SQL to a language
model.
