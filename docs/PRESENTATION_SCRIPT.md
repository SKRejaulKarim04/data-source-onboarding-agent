# Presentation script — Data Source Onboarding Agent

A speaker's script for the 12-slide deck in `docs/Data-Source-Onboarding-Agent.pptx`,
written for a 40-minute slot.

---

## How to use this document

Each slide has four parts:

| Part | What it is |
|---|---|
| **Open (plain)** | Say this first. No jargon. Anyone in the room can follow it. |
| **Go deeper (technical)** | The engineering substance. Names, mechanisms, numbers. |
| **Land it** | One or two sentences that close the point and set up the next slide. |
| **Follow-ups** | Questions an evaluator is likely to ask on *this* slide, with answers. |

The plain and technical parts are roughly **60/40 by time**. That ratio is
deliberate: a mixed room stays with you through the plain framing, and the
technical section is what earns the marks. If you sense the room is heavily
technical, shorten "Open" and let "Go deeper" run.

Passages marked **[EXPAND]** are optional. Passages marked **[CUT FIRST]** are
what you drop when you are running behind — decide that at the 15-minute mark,
not at slide 11.

### Calibrating to your own pace

The spoken text here is **4,217 words** in the core script, **4,494** with every
EXPAND block included. Divide by your own speaking rate:

| Pace | Core | With EXPAND |
|---|---|---|
| 130 wpm (measured, deliberate) | 32.4 min | 34.6 min |
| 140 wpm (normal) | 30.1 min | 32.1 min |
| 150 wpm (brisk) | 28.1 min | 30.0 min |

Word count *under*-predicts real delivery by roughly 10–15%, because pauses,
slide transitions, looking at the screen and small interruptions aren't in the
count. So the full script realistically occupies **35–39 minutes** in the room at
a deliberate pace. That is the right size for a 40-minute slot where questions
come at the end, and slightly too long if questions are expected throughout.

**If you need to fill more time**, don't slow down — tell another war story.
The challenge bank near the end of this document has ten, of which only three
are placed in the script. Each one is about 90 seconds spoken, and they land far
better than padding an explanation.

**Rehearse once with a timer.** Your real rate is the only number that matters,
and you will discover it is not the one you assumed.

### Timing

| # | Slide | Starts | Runs |
|---|---|---|---|
| 1 | Title | 0:00 | 1:15 |
| 2 | Business objective | 1:15 | 4:15 |
| 3 | The core idea | 5:30 | 5:00 |
| 4 | Architecture | 10:30 | 4:30 |
| 5 | Technology | 15:00 | 6:00 |
| 6 | Product 1 · Welcome | 21:00 | 1:00 |
| 7 | Product 2 · Clarification | 22:00 | 1:30 |
| 8 | Product 3 · Standards gate | 23:30 | 1:45 |
| 9 | Product 4 · Generated code | 25:15 | 1:30 |
| 10 | Product 5 · Live connection | 26:45 | 1:45 |
| 11 | Product 6 · Artifact | 28:30 | 1:15 |
| 12 | Conclusion | 29:45 | 2:15 |
| | **Script ends** | **32:00** | |

---

## Pre-flight checklist

Run through this the morning of, not five minutes before.

1. **Decide your demo mode now.** The Anthropic key on this machine currently
   returns `400 — credit balance too low`, so live extraction will fail in front
   of the room. Two options:
   - **Top up the account** and run the full flow end to end at least once
     beforehand. Don't assume — test it.
   - **Present on the scripted client.** `build_llm_client()` falls back to
     `ScriptedClient` when no provider key is found, so the app runs with no
     network at all. Note that `bin/lib.sh` sources `.env` on every start, so
     `unset ANTHROPIC_API_KEY` in your shell will *not* work — comment the key
     line out in `.env` instead, and restart.

   If you go scripted, say so in one sentence and move on: *"I'm running the
   deterministic client so the demo doesn't depend on a network call — the
   pipeline is identical either way."* Nobody minds this if you say it first.
   They mind a great deal if they discover it.
2. **Have the deck's screenshots as your fallback.** Slides 6–11 are real
   screenshots of the running app. If the live demo dies, you have already shown
   the product. Do not apologise and do not try to fix it live.
3. **Run `python -m pytest` once.** Expect `289 passed, 5 skipped`. The 5 skips
   are the live-PostgreSQL integration tests; they skip unless the database is
   up. Know this before someone asks why five tests are skipped.
4. **If you want all 294 green**, run `npm run up`, source `.env`, then rerun.
5. **Know your three numbers cold**: 13 checks, 294 tests, 4 source types.
6. **Open the artifact zip once** so you can talk about what is inside it without
   guessing.

---

# Slide 1 — Title

**Data Source Onboarding Agent**
*Plain English in. A validated, standards-compliant, versioned Python connector out.*

**Time: 1:15 · Ends 1:15**

### Open (plain)

> Every company that works with data has the same recurring job. Somebody needs
> data out of a system — a database, a vendor's API — and an engineer writes a
> piece of code called a connector to go and get it.
>
> It is not hard work. That is the problem. It is not hard, so it gets done
> forty times, by six different people, over three years. And every one of those
> forty is a little bit different from the others.
>
> This project takes a description of a data source written in ordinary English,
> and produces a finished, checked, working Python connector on the other side.

### Go deeper (technical)

> The claim I want to be precise about, because it is the whole argument, is the
> subtitle. *Validated* means machine-checked against a fixed standard before it
> is allowed out. *Standards-compliant* means thirteen specific checks, not a
> code reviewer's opinion. *Versioned* means every artifact can tell you which
> template made it and from which request.
>
> And one thing that is not on this slide, which I will come back to repeatedly:
> the language model does not write the code.

### Land it

> Let me start with why this problem is worth automating at all.

### Follow-ups

**Q: Is this a wrapper around ChatGPT?**
No. The model is used for exactly one thing — reading a human sentence and
filling in a structured form. Every line of Python that ships is produced by a
template. I'll show the separation on slide 3.

**Q: How long did this take to build?**
[Answer honestly with your real figure.] The thing that took the time was not
the generation — it was the validation layer and the test suite around it. The
generation is the easy half.

---

# Slide 2 — Business objective

*The repetition is where the risk lives*

**Time: 4:15 · Ends 5:30**

### Open (plain)

> This table has three columns. What has to happen, how it happens today, and
> what changes.
>
> Read the middle column as a story. Somebody files a ticket. An engineer picks
> it up and realises the ticket doesn't say which host, or what the credentials
> are, so they ask. That thread takes two days because both people have other
> jobs. Then the engineer writes the connector — well, mostly they copy the last
> one and edit it. Then it goes to code review, where a colleague checks it
> against standards they are holding in their head at four in the afternoon.
> Then it gets tested, which usually means running it locally and hoping the
> production database is configured the same way. And then it ships.
>
> Nothing there is wrong. Every step is reasonable. But look at the last row.
> Six months later somebody asks "why is this connector in production, and who
> approved it?" And the honest answer is: ask whoever wrote it, if they still
> work here.

### Go deeper (technical)

> The line underneath the table is the actual thesis. *The cost is not writing
> one connector. It is writing the fortieth.*
>
> Here is why that distinction matters. Writing one connector is a two-hour job
> and automation saves you two hours — that is not a project worth doing. But by
> the fortieth, you have five methods that every connector needs — connect, test,
> fetch schema, read, close — that have each been re-derived forty times,
> slightly differently. One of them retries three times, one retries five. One
> logs the connection string, which is a security incident waiting to be found.
>
> The variance is the cost, not the hours. And variance is exactly what a
> template removes.
>
> **[EXPAND]** Look at the four stakeholders on the bottom line, because they
> want genuinely different things and this is the slide where you can show that
> one design satisfies all four. The requesting team wants self-service — they
> want to describe what they need without booking engineering time. Engineering
> wants to stop writing the same file; they would much rather review a diff than
> start from blank. Security wants a structural guarantee, not a promise —
> they want it to be *impossible* to hardcode a password, not merely discouraged.
> And audit wants a chain: this request produced this spec, which selected this
> template, which produced this file with this checksum.
>
> Those are four different requirements, and they are usually in tension.
> Self-service normally means less control. Here it doesn't, because the control
> moved into the pipeline rather than into a review meeting.

### Land it

> So the goal is not "generate code faster". The goal is: make the fortieth
> connector identical to the first, and make it explain itself.

### Follow-ups

**Q: How do you actually quantify the saving?**
Two ways, and the second is the real one. The first is time — hours per
connector, which is easy to measure and the least interesting. The second is
defect rate and review load: how many connectors reach production with a
standards violation, and how much senior engineering time goes into catching
them. Because the checks run before acceptance rather than after, that number
moves to zero for the thirteen things we check. I'd measure that, not hours.

**Q: Doesn't a shared library solve this? Just write a good base class.**
Partly, and we use one — there is a `BaseConnector` and a `SQLBaseConnector` in
this project. But a library is opt-in. Nothing stops somebody bypassing it,
and nothing checks that they didn't. The library gives you the shape; the
generator plus the checker gives you the guarantee. You want both.

**Q: What if the requester describes the source wrongly?**
Then you get a connector to the wrong database, and it fails at the connection
test rather than in production. That's slide 10. The system doesn't verify that
you asked for the right thing — it verifies that what it built matches what you
asked for, and that it genuinely connects.

**Q: Who is the user here — an engineer or an analyst?**
Designed for both, but honestly the sweet spot is a data engineer who is tired
of writing the same file. An analyst can drive it, but somebody with context
still reviews the artifact before it ships. We didn't design a system that
removes the reviewer. We designed one that gives the reviewer something better
than a blank file to look at.

---

# Slide 3 — The core idea

*Reliability comes from constraint, not from prompting*

**Time: 5:00 · Ends 10:30**

This is the most important slide in the deck. If you only land one slide, land
this one.

### Open (plain)

> Here is the problem with using an AI model to write production code. The model
> is very good, most of the time. And "most of the time" is a disaster for
> something that has to be right every time.
>
> The usual response is to write a better prompt. Tell it more firmly. Add
> "IMPORTANT: do not hardcode passwords" in capital letters. That is hoping.
> It works until the day it doesn't, and you find out in production.
>
> This project takes a different position. Instead of asking the model to be
> careful, we structurally prevent it from being able to make the mistake.

### Go deeper (technical)

> Four mechanisms, and they stack.
>
> **First — the model never writes the code.** It fills in a form. A structured
> spec, with a schema attached. So when it has to say what kind of database this
> is, it isn't producing free text — it is picking from a closed set of four
> values. It cannot invent a fifth. The output isn't prose that we then parse
> and hope about; it's a validated object.
>
> Then a Jinja2 template takes that spec and renders the connector. Templates are
> deterministic — the same spec produces byte-identical output, every single
> time. That word *deterministic* is doing enormous work here. It is why I can
> promise you what the fortieth connector will look like.
>
> **Second — thirteen machine checks decide what ships.** They're listed on the
> slide: no hardcoded credentials, no dynamic SQL, secrets must come from the
> environment, no dangerous calls like `eval` or `subprocess`, type hints
> required, docstrings required, and seven more.
>
> The technical detail worth pausing on is *how* they run. We parse the code into
> a syntax tree and inspect the tree. We never import it. That distinction is not
> pedantry — in Python, importing a module executes it. If you check generated
> code by importing it, you have run untrusted code as the first step of deciding
> whether it's safe to run. We read the structure without ever executing it.
>
> **Third — repair is bounded and cannot regress.** Sometimes something fails.
> The system asks the model to fix it. But there are two hard limits. It gets at
> most three attempts. And a fix is only accepted if it strictly reduces the
> number of errors.
>
> That second rule came out of an actual failure I'll describe in a moment.
>
> **Fourth — secrets cannot reach the artifact.** Three layers. Credentials are
> stripped from your request before the model ever sees it. Two of the thirteen
> checks make a literal credential in the code an automatic rejection. And the
> manifest records environment variables by name only, never by value.

### The war story — the oscillating repair loop

**[CUT FIRST if running behind, but it's the best story in the deck]**

> The regression guard exists because of a specific failure.
>
> The first version of the repair loop was the obvious one: validate, if it
> fails ask the model to fix it, repeat up to three times, ship whatever comes
> out last.
>
> What actually happened is that the model would fix the one error you pointed
> at — and introduce two new ones somewhere else. Next iteration it fixes those
> two and breaks the first one again. It oscillates. And because the loop shipped
> whatever the last attempt produced, the artifact you got was determined by
> where the iteration counter happened to stop. That is not a property you want
> in a code generator.
>
> The fix is four lines. Count the errors before, count them after, and only
> adopt the new version if the number went strictly down. Otherwise throw it
> away, keep the previous one, and stop.
>
> What I like about this is that it is not an AI technique. It's the same idea
> as a ratchet. The loop can only ever move one direction, so the output is never
> worse than the input — regardless of what the model does. You get a guarantee
> that doesn't depend on the model's behaviour at all.

### Land it

> The line at the bottom of the slide: *a checker that has only ever seen good
> input has demonstrated nothing*. So the test suite deliberately feeds it broken
> code — a connector with a password in it, a connector with SQL built by string
> concatenation — and asserts that each one is caught. Testing that the good case
> passes tells you almost nothing. Testing that the bad case is *rejected* is
> the test that matters.

### Follow-ups

**Q: Why not just let the model write the connector? Models are good at code now.**
They are. And if I needed one connector, I'd do exactly that. The problem is
the fortieth. A model writing forty connectors gives me forty *slightly*
different files, and I have no mechanism that tells me how they differ or
guarantees any property across all of them. A template gives me one shape, and
a diff on the template tells me exactly what changed for every connector at
once. I traded flexibility for a guarantee, on purpose, because in this domain
the guarantee is worth more.

**Q: Then what is the model actually adding? Couldn't this be a form?**
It could, and for a user who knows the answers a form would be fine. What the
model adds is the ability to accept an ambiguous sentence and work out which
fields it maps onto — including noticing which fields are *missing*, which is
the harder half. That's slide 7. The value isn't code generation; it's turning
unstructured intent into structured intent.

**Q: What happens when someone asks for something the template doesn't cover?**
Two answers. Today, the honest one: the template covers a defined set, and
outside it we say so rather than improvising. The designed path for bespoke
logic is a custom block that the model writes, which then goes through the
same thirteen checks and the same repair loop as everything else — model-written
code is allowed, but it is never trusted, it's checked.

**Q: How do you know these are the right thirteen checks?**
They came from two sources: things that are security-critical and mechanically
detectable, and things you would actually be asked to fix in code review. And
importantly the list is data, not architecture — `ALL_CHECKS` is a tuple, adding
a fourteenth is one function and one entry. I would fully expect a real
deployment to add its own. Thirteen is where we are, not a claim that thirteen
is correct.

**Q: The AST checks sound like a linter. Why not just run one?**
We do run one — ruff, black and bandit all run as part of validation. But a
linter enforces general Python hygiene. It has no idea that *this* project
requires every connector to subclass `BaseConnector`, or declare its source
type, or take secrets from the environment. The thirteen checks are the
project's own rules, which no off-the-shelf tool knows about. It's both, not
either.

**Q: What if the repair loop can't fix it?**
Then the artifact is returned rejected, with the findings attached and shown in
the UI. It is deliberately not silent and it is deliberately not hidden — you
see what failed and how many attempts were made. Failing loudly with a readable
reason is the correct behaviour; failing silently would be the bug.

---

# Slide 4 — Architecture

*One request, five stages*

**Time: 4:30 · Ends 15:00**

### Open (plain)

> This is the whole system on one page. Five stages, left to right. A request
> comes in at the top and a downloadable file comes out at the end.
>
> Walk it with me. **Extract** — read the English, produce a draft spec plus any
> questions. **Refine** — take the answers to those questions. **Generate** —
> render the connector and check it. **Test** — actually run it against the real
> database. **Deliver** — package it up.

### Go deeper (technical)

> Three things on this diagram are worth more than a glance.
>
> **The right-hand column is where the model is used.** Look at how little of it
> is coloured. Extract is one model call. Generate calls the model only if
> validation fails, or to write the explanation document. Test calls it only if
> the connection fails. Refine and Deliver never call it at all.
>
> That's the architecture reflecting the argument from the last slide. The
> expensive, non-deterministic, occasionally-wrong component is used at exactly
> two points, and everything downstream of it is deterministic.
>
> **The Refine stage never calls the model.** This is the footnote at the bottom
> and it is a real design decision. When you answer a clarifying question, the
> obvious implementation is to append your answer to the original prompt and
> re-run extraction. We deliberately don't. The answers map directly onto the
> named fields that were asked about.
>
> Why does that matter? Because re-extracting means the model reads the whole
> thing again, and it can *change its mind about something you already settled*.
> You answer a question about the port and it quietly revises the hostname.
> Mapping answers onto fields makes that impossible. Once a field is settled,
> it's settled.
>
> **[EXPAND]** **Each stage is an ordinary function call with an ordinary
> return type.** `SpecExtractor.extract`. `ConnectorGenerator.generate`.
> `ConnectionSandbox.run`. There is no agent framework, no orchestration engine,
> no graph library. Five stages, called in order, by a FastAPI route handler.
>
> I want to defend that, because "we didn't use a framework" can sound like
> naivety. The pipeline is linear and known in advance. Every branch in it is a
> branch we chose. A framework buys you dynamic routing between steps — which
> costs you the ability to read the control flow by reading the code, and costs a
> new engineer a week learning the framework's model before they can debug
> anything. For a five-stage linear pipeline, that trade is bad. If the workflow
> becomes genuinely dynamic — if the system has to decide the order at runtime —
> that calculation changes and I'd revisit it.

### The data, stage by stage — what actually flows through

Roughly 4 minutes. This is the section that answers "but what is actually being
passed between these boxes?" Do not read the field names as a list — group them
and say what each group is *for*.

> Let me take one request all the way through, and be specific about what exists
> at each point. Because "a spec goes in and code comes out" is true but it
> hides the interesting part.
>
> **Stage one, Extract.** Before the model sees anything, the prompt is scrubbed
> for credentials, and the scrubbed version is kept — so there's a record of
> exactly what was sent to the provider, not just what you typed.
>
> What comes back is an `ExtractionResult`, and it holds five things worth
> naming. The **draft** itself. A **confidence** score. A list of **clarifying
> questions**. Any **security findings** — if you pasted a password or the text
> looked like a prompt injection, that's flagged here. And an
> **unsupported-request** flag, for when someone asks for a source type this
> system genuinely doesn't handle. That last one matters: the failure mode you
> want to avoid is quietly mapping "onboard our Snowflake warehouse" onto
> PostgreSQL because it's the closest thing available.
>
> The **draft** has around nineteen fields and every one of them is optional —
> source type, connector name, host, port, database, schema, base URL,
> pagination, auth method, environment prefix, and so on. Optional is the whole
> point. A draft with holes in it is the normal case, not an error.
>
> And one field on it is the honesty mechanism: **`assumed_fields`**. Anything
> the model filled in from convention rather than from your text is named there,
> which is what the review screen displays back to you.
>
> **[EXPAND]** Each **question** carries six things, and I'd point at two of
> them. There's the field it maps to, the question itself — and then a **`why`**,
> and an **`example`**. Those two exist because the person answering may not be
> an engineer. "What is the port?" and "What is the port? Postgres usually runs
> on 5432, and we need it to build the connection string" have very different
> answer rates.
>
> **Stage two, Refine**, takes those answers and writes them onto the named
> fields. No model call, as I said.
>
> **Then a shape change, and this is my favourite part of the design.** The draft
> gets promoted into a `SourceSpec`, and a `SourceSpec` is not a validated draft
> — it's a genuinely different object.
>
> The draft is flat and permissive: nineteen loose optional fields sitting next
> to each other. The spec is nested and strict. There's a **target**, and it is
> *either* a SQL target — host, port, database, schema — *or* a REST target —
> base URL, path, pagination, page size, rate limit. Never both, never neither.
> There's an **auth** block: method, environment prefix, header name, token URL,
> scopes. And there's an **options** block, which is the interesting one, because
> it holds seven operational settings the user never mentioned and never had to:
> read-only, connect timeout, query timeout, pool size, max retries, SSL mode,
> TLS verification.
>
> So the spec carries operational policy that the requester was never asked
> about, with sane defaults, applied uniformly. That's the fortieth-connector
> argument again, expressed as a data structure.
>
> And because the target is one-or-the-other rather than a bag of optional
> fields, it is structurally impossible to hand a REST base URL to the SQL
> template. That's not a check that runs — it's a shape that can't be built.
>
> **Stage three, Generate**, is really four steps. The spec's source type and
> auth method are joined into a **template key** — `postgresql:username_password`
> — which the registry resolves to a specific template at a specific version.
> Render. Then validate, which produces a **report**: how many checks ran, how
> many passed, which external tools ran, which were skipped, and every individual
> finding.
>
> **[EXPAND]** Each finding carries a check name, a severity, a message, a line
> number, which tool raised it — and a **remedy**. That remedy field is not for
> you; it's what gets fed to the repair loop, so the model is told what to do
> rather than left to infer it.
>
> If it failed, repair runs — and every attempt is recorded: iteration number,
> errors before, errors after, and whether it was accepted. Those records ship
> with the artifact, so nobody has to take the repair loop's word for it.
>
> What comes out is a **`GeneratedConnector`**: the code, the spec it came from,
> the validation report, the template key and version, a checksum of the spec, a
> checksum of the code, and the repair history. From those it computes three
> things — whether it's **accepted**, the **code checksum**, and the **version
> number**, whose patch component is the repair count.
>
> Then documentation is generated: a README, a pinned requirements file, and a
> prose explanation — and the explanation records **where it came from**, model
> or deterministic fallback. Provenance on the prose as well as on the code.
>
> **Stage four, Test**, returns a `SandboxResult`, and the field I'd point at is
> **`stage`**. It's one of import, resolve, construct, connect, or schema. So a
> failure doesn't just say it failed — it says how far it got. Failing at
> "connect" is a wrong password. Failing at "import" is a missing driver. Those
> are completely different problems and you can tell them apart without reading a
> traceback.

### Stage five — what is actually in the artifact

> **Five files.** The connector module. A README. A `requirements.txt` with
> pinned versions. An `EXPLANATION.md` — prose, labelled with whether a model or
> the fallback wrote it. And a `manifest.json`.
>
> The manifest is the one that matters in six months, and it has five sections.
>
> **Source** — what this connects to. Type, class name, whether it's read-only,
> and the target as host, port and database. No credentials, by construction.
>
> **Provenance** — the chain. Template key, template version, spec checksum, code
> checksum, when it was generated, and how many repair iterations it took.
>
> **Validation** — passed or not, checks run, checks passed, conformance
> percentage, which tools ran, which were skipped, and every error and warning in
> full. Note *tools skipped* is recorded: if bandit wasn't installed, the
> manifest says the security scan didn't run rather than implying it passed.
>
> **Connectivity** — and this one has two states. If it was never tested, the
> manifest says `tested: false`, explicitly. If it was, you get success, the
> stage it reached, how many tables were discovered, and how long it took.
>
> That distinction is deliberate. An untested connector and a connector that
> passed its test must never look the same to somebody reading the manifest
> later. Silence is not a pass.
>
> **Required env** — the environment variables this connector needs, by **name
> only**. Never values. There's a test whose entire job is to serialise the
> manifest and assert no secret appears in it.
>
> And the packaging is byte-reproducible: the zip's internal timestamps are
> fixed rather than read from the clock, so building the same artifact twice
> gives you an identical file. Which is what makes the checksum an identity
> rather than a record of when you happened to press the button.

### Land it

> One property that holds across all five stages: failure is a return value, not
> an exception. A rejected connector still comes back, with its report. A failed
> connection still comes back, with the driver's real error message and the stage
> it died at. The UI always has something to show — because the failures are the
> interesting cases, and a pipeline that throws them away is a pipeline you
> cannot debug.

### Follow-ups

**Q: Where does state live? What happens if the process restarts?**
Today it's an in-memory store, and the docstring says so explicitly. That's
honest and it's a real limitation — restart the server and in-flight requests
are gone. It's the right call for a single-user demo and the wrong one for a
deployment. The fix is small and well-understood: the store has four methods —
create, get, delete, list — so swapping it for Postgres is a class, not a
refactor. I'd do that before anything else on a production path.

**Q: Is this synchronous? What about a slow database?**
Yes, synchronous, and the sandbox has a hard 30-second wall-clock timeout, so
the worst case is bounded. For a single user that's correct behaviour. For
concurrent users the generate and test stages should move to a background queue
with the UI polling — again a known change, not a redesign, because each stage
is already a self-contained function with a serialisable result.

**Q: Why five stages rather than one endpoint that does everything?**
Because the human needs to intervene between them. You review the spec before
code is generated. You review the code before it's tested against a real
database. Collapsing this into one call would remove the review points, which
are the reason anybody would trust the output.

**Q: What if extraction gets it wrong?**
You see the extracted spec before anything is generated — that's slide 8. The
whole design assumes extraction is fallible; that's why review comes before
generation rather than after.

**Q: Why two spec models? Why not one model with optional fields?**
Because "a description of what the user said" and "a thing you may generate code
from" are different objects with different rules, and collapsing them means
every downstream function has to re-check completeness. With two, the check
happens once at promotion, and after that the type is the proof. A function
taking a `SourceSpec` cannot be handed an incomplete one — not by convention,
but because the object couldn't be constructed.

**Q: Where do the connector options come from if the user never states them?**
Defaults on the spec model — timeouts, pool size, retries, SSL mode. That's
deliberate: they're operational policy, they should be uniform across every
connector, and asking a requester to choose a pool size would be a worse
product. Changing the default changes it everywhere at once, which is the same
argument as the template.

**Q: Is the manifest signed?**
No, and I'd flag that as the honest gap in the provenance story. Everything is
checksummed, so tampering is *detectable* if you have a trusted copy of the
checksum — but nothing cryptographically binds the manifest to a producer.
Signing the artifact at packaging time is the obvious extension and it doesn't
change any of the surrounding design.

**Q: If I never run the connection test, what does the manifest say?**
`connectivity: {tested: false}` — explicitly. That's a design decision rather
than an accident: an untested connector and a passing one must never be
indistinguishable to somebody reading the record later. Absence of evidence gets
written down as absence of evidence.

**Q: Why record where the explanation came from?**
Because one path is a model and the other is a deterministic fallback used when
no provider is configured, and the reader deserves to know which they're
reading. It's the same instinct as `assumed_fields` — anywhere the system's
confidence differs from its output, say so in the artifact rather than in the
docs.

---

# Slide 5 — Technology

*The stack, and why each piece is there*

**Time: 6:00 · Ends 21:00**

This is the slide with the most marks available. Do not just read the table.
For each row give **what it is, why it, and how it's used** — the third part is
what separates you from someone who listed technologies.

### Open (plain)

> Eight rows. I'm going to go through these properly, because the interesting
> thing about a stack isn't what you picked — it's what you rejected and why.

### Go deeper (technical)

> **FastAPI and Pydantic, for the API.** FastAPI is a Python web framework;
> Pydantic is a data validation library, and they're built to work together.
>
> Why: because validation happens at the boundary rather than inside the
> handlers. When a request arrives, it is either a valid shape or it is rejected
> before my code runs. That means no handler in this project starts with ten
> lines of "is this field present, is it a string, is it the right length."
>
> How: request bodies are declared as Pydantic models, and FastAPI enforces them.
> Every 400 response you get from this API was generated by the schema, not by
> me writing an if-statement.
>
> **Pydantic again, for the spec — and this is the subtle one.** There are two
> models, not one. A permissive `SpecDraft` where everything can be missing, and
> a strict `SourceSpec` where nothing can.
>
> Why two: because those are genuinely two different objects. A draft is what the
> model produced from a sentence and it is allowed to have holes — that's the
> normal case, not an error. A spec is a thing you're permitted to generate code
> from, and it must be complete.
>
> How: the draft is promoted to a spec by a `finalize()` call that fails if
> anything required is missing. So the type system enforces the workflow.
> You physically cannot pass an incomplete draft to the generator, because the
> generator's signature demands a `SourceSpec`. The rule isn't documented and
> hoped for; it's structural.
>
> **Jinja2, for code generation.** Jinja2 is a templating engine — best known
> for generating HTML. Here it generates Python.
>
> Why: one word, determinism. Same input, same bytes out, every time. This is the
> single most important choice in the project, because it's what makes the
> standards guarantee possible. A model that writes code can produce anything.
> A template can only produce what's in the template.
>
> How: two template files. One for SQL databases, one for REST APIs. Those two
> files serve four registered source types — PostgreSQL, MySQL, SQL Server and
> REST — because the SQL dialects differ in small, parameterised ways: the driver
> name, the version query, the connection arguments. Adding a fifth SQL dialect
> is a registry entry, not a new template.
>
> **The validation layer — `ast`, plus ruff, black and bandit.** Four tools, two
> categories.
>
> `ast` is Python's own parser, in the standard library. That's where the
> thirteen project-specific checks live. Why the standard library: because
> parsing Python correctly is a solved problem I have no business re-solving,
> and using the same parser Python itself uses means I can't disagree with it.
>
> How: parse to a tree, walk the tree, emit findings. Never import. I said this
> on slide 3 but it's worth repeating on the technology slide because it drove
> the tool choice: importing a module executes it, so any validation strategy
> based on importing has already lost.
>
> Then ruff for linting, black for formatting, bandit for security patterns.
> Why those three: they're what a Python team would run in CI anyway. The
> generated code is held to the same bar as hand-written code, using the same
> tools, which is the whole point — nobody should be able to tell from the code
> whether a person or a template wrote it.
>
> How, with one detail worth mentioning: they run as subprocesses, and if a tool
> isn't installed the report says which checks were skipped rather than silently
> passing. A validation report that quietly means "I didn't check" is worse than
> no report.
>
> **SQLAlchemy 2.0, for database access.** Why: one connector shape across three
> SQL dialects. Without it, PostgreSQL, MySQL and SQL Server need three different
> drivers with three different APIs, and the template would need three code
> paths. With it, they differ by a connection string and a couple of parameters.
> How: the generated connector builds a SQLAlchemy URL and uses `text()` with
> bound parameters — which is also what makes the no-dynamic-SQL check
> enforceable, because there's a correct idiom to enforce.
>
> **The sandbox — subprocess with resource limits.** Why not Docker: because
> requiring a container runtime to test a connection puts a dependency on every
> developer machine, and the boundary I need is process-level, which the
> operating system already provides.
>
> How: a separate process, a 30-second wall-clock timeout, a memory cap, no
> shell, its own process group so a timeout kills anything the driver spawned,
> and — the part I'd point at — an **allowlisted** environment. The child gets
> `PATH`, a couple of locale variables, and the environment variables belonging
> to this specific connector. Nothing else. Not the API key, not the app's own
> database password.
>
> Allowlist rather than denylist, and that's a deliberate security posture. A
> denylist means every new secret added to the parent environment is exposed
> until somebody remembers to add it to the list. Nobody remembers.
>
> And I'll be straight about the limit, because the module docstring is: this is
> process isolation, not kernel isolation. It stops runaway memory and hung
> processes and it stops environment leakage. It does not stop a determined
> payload from opening a network socket. For production this same runner goes
> inside a container with egress allowlisting — the interface doesn't change,
> only the strength of the box. Being clear about that boundary is worth more
> than claiming it's airtight.
>
> **React 18, TypeScript and Vite, for the front end.** Why TypeScript: the API
> has a precise shape and the front end should fail at compile time when that
> shape changes, not at runtime in front of a user. How: the API types are
> mirrored in one file with type guards, and exactly one module in the front end
> is allowed to call `fetch` — so there is one place where the network exists,
> and everything else is pure.
>
> Why Vite: it builds to static files that the Python process serves directly.
> One process in production, two in development, and no CORS configuration
> because the dev server proxies the API.
>
> **pytest — 294 tests.** How, and this is the part I care about: a large
> fraction of them are fault injection. We hand the checker a connector with a
> hardcoded password and assert it's rejected. We hand the repair loop a model
> that makes things worse and assert the guard catches it. Tests that only prove
> the happy path works are the easy tests and they demonstrate very little.

### Land it

> The note at the bottom: no orchestration framework. Six modules and a function
> call chain. I covered the reasoning on the last slide — for a linear pipeline,
> a framework costs readability and buys flexibility I don't need yet.

### Follow-ups

**Q: Why not LangChain or LangGraph?**
Because I have two model calls in a fixed order, and a bounded loop with a
deterministic acceptance test. LangGraph is genuinely good at dynamic,
multi-step agent workflows where the path isn't known in advance. Mine is known
in advance. I'd have paid a dependency and a learning curve for abstraction I
don't use, and I'd have made the control flow harder to read. If the workflow
becomes dynamic, that answer changes.

**Q: Why Jinja2 and not a proper code-generation library, or the `ast` module for generation?**
Building code via the `ast` module and unparsing it is more rigorous — you
cannot generate syntactically invalid output. But it's dramatically harder to
read and to modify. The template is a Python file with holes in it; a data
engineer can read it and see exactly what will be produced. Since a human has to
review and maintain these templates, readability won. And the syntax-validity
argument is weaker than it sounds, because we parse the output anyway — a
template that produced invalid Python would fail validation immediately.

**Q: Why Anthropic, and what happens if the provider is down?**
There's an `LLMClient` protocol and three implementations behind it — Anthropic,
Gemini and DeepSeek — plus a scripted client that returns fixed responses. The
scripted one is not a toy; it's what the tests run against, which is why 294
tests execute in twelve seconds with no network. Being able to swap the provider
was a design requirement, not a convenience.

**Q: Why Pydantic v2 rather than dataclasses?**
Dataclasses give you structure but not validation. Pydantic validates on
construction, which is exactly what I need at a boundary where the input came
from a language model. Internally, where the data is already trusted, I *do*
use frozen dataclasses — `GeneratedConnector` and `SandboxResult` are both
dataclasses. Pydantic at the edges, dataclasses in the middle.

**Q: How does the front end stay in sync with the API?**
Manually, via a single types file with type guards — and I'll be honest that
this is the weakest link in the stack. FastAPI publishes an OpenAPI schema, and
the correct answer is to generate the TypeScript types from it in CI so drift is
impossible. Today it's a convention enforced by discipline, which is exactly the
kind of thing this project argues against everywhere else.

**Q: 294 tests — what's the coverage?**
[Give the real number if you've measured it; if you haven't, say so.] The number
I'd point at instead is the fault-injection tests, because coverage measures
which lines ran, not whether the checks actually catch anything. A validator can
have 100% coverage and reject nothing.

---

# Slides 6–11 — The working product

Six screenshots. **Total 8:45.** Keep moving — the temptation is to linger, and
these are the slides where you lose time you need for the conclusion.

A framing line before slide 6:

> Everything from here is the real system running. These are screenshots, not
> mockups, and every number on them was produced by the pipeline I've described.

---

## Slide 6 — Product 1 of 6 · Describe the source in plain English

**Time: 1:00 · Ends 22:00**

### Open (plain)

> This is the whole interface. A text box.
>
> No connection wizard, no dropdown of thirty database types, no form with
> nineteen fields where you don't know what half of them mean. You describe what
> you want the way you'd describe it to a colleague.

### Go deeper (technical)

> The three examples on the right are there for a specific reason. A blank text
> box is a genuinely hard interface — people don't know how much to write or what
> detail matters. The examples solve the cold start, and they're worked examples
> rather than placeholder text: one complete request, one deliberately vague one,
> and one REST API.

### Follow-ups

**Q: How does a user know what to write?**
The examples, and then the system tells them — if something's missing it asks,
which is the next slide. The design assumes the first message is incomplete,
because it usually is.

---

## Slide 7 — Product 2 of 6 · When the request is incomplete, the agent asks

**Time: 1:30 · Ends 23:30**

This is the slide that demonstrates the system is honest. Give it its time.

### Open (plain)

> This request didn't mention a hostname. Watch what did *not* happen: it didn't
> guess one. It didn't put in `localhost` because that's usually right.
>
> It says: I need the host, here's an example of what one looks like, please tell
> me.

### Go deeper (technical)

> Three things on screen are each doing work.
>
> The **confidence dropped to 55%**. That's not decoration — the golden test set
> has upper bounds on confidence for deliberately vague prompts. A system that
> reports high confidence on a vague request is worse than useless, because it
> teaches you to trust it when you shouldn't. So being *appropriately unsure* is
> a tested property.
>
> The **missing field is named**, not described. Not "some details are missing" —
> the specific field, so the answer maps back onto it deterministically. That's
> the Refine stage from the architecture slide.
>
> And the **question carries an example**, because "what is the host?" and "what
> is the host? for example `db.internal.company.com`" have very different answer
> rates from a non-expert.
>
> Underneath this is the metric I'd defend hardest in the whole project. The
> evaluation set has thirty cases, and each one lists not only the fields that
> must be extracted correctly, but the fields that must stay **null**. Inventing
> a plausible hostname is a worse failure than extracting nothing, because a
> missing field stops the pipeline and a wrong field ships. So hallucination is
> measured as its own metric, separately from accuracy, and the target is under
> five percent.

### Follow-ups

**Q: How is the confidence score computed — is it the model's own number?**
It's produced as part of the structured extraction, so yes, it originates from
the model. Which means on its own I wouldn't trust it. What makes it meaningful
is that it's *bounded by tests*: the golden set asserts both floors and
ceilings, so a vague prompt returning 0.9 fails the suite. It's a calibrated
number rather than a self-reported one.

**Q: What stops it inventing a value anyway?**
Three things. The prompt instructs it to leave unknowns null. Fields it filled
by assumption rather than from the text are recorded in `assumed_fields` and
shown to you. And the golden set tests it — that's the `expect_null` list.
The third is the one that makes the first two credible.

**Q: What if the user's answer is wrong?**
Then the connection test fails, which is much better than it succeeding against
the wrong database. The system verifies that it built what you described, not
that you described the right thing.

---

## Slide 8 — Product 3 of 6 · Extraction, generation, and the standards gate

**Time: 1:45 · Ends 25:15**

### Open (plain)

> This is the review screen — everything the system understood, before any code
> is trusted.
>
> The important detail is that it shows what it **assumed**, not just what it
> knows. If it filled in a default port because you didn't say one, that's
> labelled. You're not asked to trust a summary; you're shown the working.

### Go deeper (technical)

> Then the gate. Thirteen of thirteen checks pass, so this artifact is accepted.
>
> "Accepted" is a computed verdict, not a label. It's derived from the validation
> report, it's written into the manifest inside the artifact, and it's what the
> request's status is set from — so the decision travels with the artifact rather
> than living in a screenshot.
>
> I'll be straight about one thing here, because it's the obvious next question:
> the verdict is recorded and surfaced everywhere, but the download endpoint
> doesn't currently refuse a rejected artifact. Rejection is loud — the UI marks
> it, the manifest records it — but it isn't yet a hard block. That's a
> deliberate development-time choice, because seeing the rejected code is how you
> debug a template, and it's a one-line change to enforce on a production path.
>
> **[EXPAND]** And note the direction of the check. Traditional code review is
> *detective* — the code exists, then somebody looks for problems. This is
> *preventive*: the artifact does not become publishable until it conforms. It's
> the difference between "we found three violations in review" and "a
> non-conforming artifact cannot exist in a shippable state."
>
> That's what lets me say 100% conformance on accepted artifacts, and I should be
> precise about what that number means, because it's easy to over-claim: it does
> not mean the code is perfect. It means every artifact that made it through
> passed all thirteen. The percentage is a tautology by construction — and that
> is the point. Conformance is not a statistic we measure afterwards, it's an
> entry condition.

### Follow-ups

**Q: 100% conformance sounds like marketing.**
It would be if it were a measurement. It isn't — it's a gate. The honest
statement is: an artifact that fails any check cannot be accepted, therefore
every accepted artifact passes all of them. The interesting number isn't 100%,
it's how many artifacts get rejected and why, which is visible in the repair
attempt count.

**Q: So can I download a rejected artifact?**
Today, yes — and I'd rather tell you that than have you find it. The verdict is
computed, recorded in the manifest and shown in the UI, but the download
endpoint only checks that an artifact exists. That's the right behaviour while
you're developing templates, because inspecting the rejected output is how you
work out what the template did wrong. On a production path it becomes a
conditional on `accepted` in one endpoint. The gate is real; what's missing is
the enforcement point, and I know exactly where it goes.

**Q: Should there be an override for when you genuinely need to ship?**
I'd resist adding one casually. An override becomes the normal path within a
month. If a check is wrong, the right fix is to change the check — it's one
function in a tuple — so the exception is recorded in the standard itself rather
than in somebody's judgement on a Friday afternoon.

**Q: What does "assumed" mean — is that different from a default?**
It's a default that the system is telling you about. Port 5432 for PostgreSQL is
correct nearly always, so refusing to proceed would be obstructive. Applying it
silently would be dishonest. Applying it and labelling it is the middle path.

---

## Slide 9 — Product 4 of 6 · The generated connector

**Time: 1:30 · Ends 26:45**

### Open (plain)

> This is the output. It's ordinary Python. If I hadn't told you it was
> generated, I don't think you'd know.
>
> That's the target. Not clever code — unremarkable code.

### Go deeper (technical)

> Look above the code at the provenance block. Four things: which template and
> which version, a checksum of the spec, a checksum of the code, and how many
> repair passes it took.
>
> Those four fields answer a question that is normally very hard. Six months from
> now, someone asks why this file is in production. Today that's an
> archaeological dig through commit history and Slack. Here it's a lookup: this
> request produced this spec with this checksum, which selected template version
> 1.0.0, which produced this file with this checksum, with zero repairs.
>
> And the version number itself carries information — the patch component is the
> repair count. So a connector that needed fixing is visibly different from one
> that rendered clean, at a glance, without opening anything.

### Follow-ups

**Q: What if I need to edit the generated code?**
Then you own it, and that's a legitimate choice — it's your code, it's readable,
you can edit it. What you lose is regeneration; the next template bump won't pick
up your edit. The design intent is that a change you'd want on every connector
belongs in the template, and a change that's genuinely unique to one source is a
reason to fork it deliberately.

**Q: How do you handle a template version bump for connectors already deployed?**
Today you'd regenerate and diff. The mechanism is there — every artifact records
its template version, so finding out which deployed connectors are on an old
template is a query, not an investigation. Acting on that automatically is the
obvious next phase and I haven't built it.

**Q: Is the checksum of the code or of the whole artifact?**
Code checksum is of the module. The manifest covers the whole bundle, and the
packaging is byte-reproducible, so packaging the same artifact twice gives an
identical zip.

---

## Slide 10 — Product 5 of 6 · Proven against a real database, not just compiled

**Time: 1:45 · Ends 28:30**

The strongest slide for a sceptical evaluator. This is where "it generates code"
becomes "it works."

### Open (plain)

> Everything so far proved the code is well-formed. This proves it works.
>
> The connector ran against a real PostgreSQL database, connected, and came back
> with three tables and their columns and primary keys. That's discovered
> information — it wasn't in the request and it wasn't in the template. It came
> out of the database.

### Go deeper (technical)

> How it runs matters as much as that it ran. Separate process. Thirty-second
> wall-clock timeout. Memory cap. No shell. Its own process group. And an
> environment containing only the variables this connector is supposed to see.
>
> Credentials are sent once, for this call, and are never stored, never logged,
> and never written into the artifact. The generated connector reads them from
> environment variables — which is one of the thirteen checks, so a connector
> that did it any other way could not have got this far.
>
> **[EXPAND]** And I'll flag the limitation honestly, because it's in the module
> docstring: this is process isolation, not kernel isolation. It reliably stops
> the failure modes I'm defending against — runaway memory, a hung process, a
> connector reading a secret it shouldn't see. It does not stop deliberately
> malicious code from opening a socket. For production this runner goes inside a
> container with egress allowlisted to the target host, and the interface doesn't
> change at all.

### The war story — the sandbox that couldn't report failures

**[Good story, use it if you have the time]**

> A bug worth mentioning, because it was invisible and it mattered.
>
> Every failed connection reported the same thing: "Connection failed." Wrong
> password, unreachable host, no such database — all identical.
>
> The cause was one line. The code read a field called `error` from the result
> object; the field is actually called `error_message`. So the fallback string
> fired every time.
>
> Nothing crashed. No test failed, because the tests asserted that failure was
> *reported*, not that it was *informative*. What broke was everything
> downstream: the user learned nothing, and the repair loop — which tries to fix
> runtime errors — was being handed a generic string with no information in it,
> so it couldn't do anything useful.
>
> The lesson I took: the tests were checking the shape of the failure path, not
> its content. Error paths need assertions on what they actually say, because a
> useless error message is a silent failure and silent failures survive test
> suites.

### Follow-ups

**Q: Is the sandbox actually secure?**
For the threat model I designed against — generated code that might be wrong,
might loop forever, might try to read an environment variable it shouldn't —
yes. Against deliberately hostile code, no, and I wouldn't claim otherwise.
It's a process boundary, not a kernel boundary. The production answer is the
same runner inside a locked-down container, and nothing about the interface
changes.

**Q: Where does the test database come from?**
A local PostgreSQL with a seeded schema. There's a script that brings it up
without Docker, using an embedded Postgres, so a developer can run the full
integration suite with one command.

**Q: What if the connection fails — does it retry?**
There's a repair path for runtime errors: the failure and traceback go back to
the model, which proposes a fix, and the fix goes through the same validation.
But retrying a bad password won't help, and the system doesn't pretend it will —
it shows you the driver's actual message so you can fix the input.

**Q: Do the credentials touch disk anywhere?**
No. They're passed as environment variables to the child process for the
duration of that call. The artifact records variable *names*, never values.

---

## Slide 11 — Product 6 of 6 · The handover artifact

**Time: 1:15 · Ends 29:45**

### Open (plain)

> And this is what you get: a zip file. The connector, a README, a requirements
> file, a written explanation of what it does, and a manifest.
>
> The explanation matters more than it sounds. It's the document that lets the
> next person understand this connector without reading the code first.

### Go deeper (technical)

> The manifest is the audit record — the request, the spec checksum, the template
> and version, the code checksum, the environment variables by name, and the
> validation result.
>
> And the packaging is byte-reproducible: build the same artifact twice and you
> get an identical file. Which means the checksum is a real identity, not a
> timestamp.

### Land it

> One line, and it's the whole project: **the model reads intent, the template
> writes the code, the checker decides what ships.**

### Follow-ups

**Q: Why a zip and not a PR or a package?**
Because a zip has no infrastructure requirements and works for any consumer. In
a real deployment I'd expect this to open a pull request instead — the artifact
contents are the same, only the delivery changes.

**Q: Are the credentials in the manifest?**
Names only, never values. That's deliberate and it's tested.

---

# Slide 12 — Conclusion

*Standards you can prove, not standards you hope for*

**Time: 2:15 · Ends 32:00**

Slow down. Do not rush the last slide because you're relieved.

### Open (plain)

> Four things to take away.
>
> **It works, end to end, today.** Plain English to a spec, spec to a connector,
> thirteen checks, a live connection to a real database, a packaged artifact.
> Every screenshot you've seen is that pipeline running. None of it is a mockup.

### Go deeper (technical)

> **The guarantee is structural, not aspirational.** The model fills a form, a
> template writes the code, a checker decides what ships. That separation is the
> reason I can tell you what the fortieth connector will look like — not because
> the model is reliable, but because the model isn't in that part of the path.
>
> **Every artifact can account for itself.** Template version, spec checksum,
> code checksum, repair count in the version number, packaged reproducibly. Six
> months on, "why is this in production?" is a lookup rather than an argument.
>
> **And it runs where the team runs.** macOS, Linux and Windows — with the
> cross-platform behaviour asserted in the test suite rather than assumed. So a
> change that would only break Windows fails on all three.

### Land it

> Bottom line: 294 tests, 13 checks, 4 source types, and 100% conformance on
> everything accepted — which, as I said, is true by construction, and that is
> exactly why it's worth having.
>
> Happy to take questions.

### Follow-ups

**Q: What would you do next?**
Three things in order. Durable state, because the in-memory store is the clearest
production gap. Then a background queue for generate and test, so it handles
concurrent users. Then the thing I actually find most interesting: a drift
watcher that re-runs the connection test on a schedule, compares the observed
schema against the spec that generated the connector, and opens a pull request
when they diverge. Every piece needed for that already exists — the sandbox
returns real schema, and every artifact records the spec it came from.

**Q: What's the biggest weakness?**
The template coverage. Four source types is enough to prove the architecture and
not enough to be broadly useful. The good news is that adding a SQL dialect is a
registry entry rather than a new template — but a genuinely new *shape* of
source, say GraphQL or a file-based source, is real work. I'd rather say that
than imply it generalises for free.

**Q: What would you do differently if you started again?**
Generate the TypeScript types from the OpenAPI schema from day one. It's the one
place in the project where correctness depends on discipline rather than on a
mechanism, and that's inconsistent with everything else I've argued for.

---

# Challenges faced — the consolidated bank

Six of these are placed in the script above. Keep the rest in reserve for
"tell us about a problem you hit." Each has the same shape: what happened, why
it was hard, what changed. That shape is what evaluators are listening for.

### 1. The repair loop that oscillated

*(Told on slide 3.)* Fixes introduced new errors; the loop shipped whatever came
last. **Fix:** accept a candidate only if the error count strictly decreases;
otherwise revert and stop. **Lesson:** an unbounded loop with a model in it needs
an acceptance test, not just an iteration cap.

### 2. You cannot validate code by importing it

Checking generated Python by importing it means executing untrusted code as step
one of deciding whether it's safe. **Fix:** all thirteen checks read the abstract
syntax tree; the code is never imported. **Lesson:** in Python, "load" and "run"
are the same verb, and security analysis has to happen before it.

### 3. The sandbox that reported every failure identically

*(Told on slide 10.)* Read `error`, field was `error_message`. Every failure said
"Connection failed." **Lesson:** tests asserted the failure path *existed*, not
that it carried information. Assert on error content.

### 4. Two copies of the same module

An import written as `from src.dsoa.validation.repair import ...` in one place
and `from ..validation.repair import ...` in another loaded the module twice
under two names. Python then had two distinct `ConfigurationError` classes, so
`except ConfigurationError` did not catch the exception that was raised — the
names matched, the objects didn't. **Fix:** relative imports throughout.
**Lesson:** in Python, identity of a class is identity of the module object that
defines it. Exception handling silently depends on that.

### 5. `.gitignore` excluded a source directory

A rule matching `artifacts/` was intended for build output. It also matched
`src/dsoa/artifacts/`, a real source package. Everything worked locally, because
the file was on disk. **How it was found:** cloning the repository into a
temporary directory and trying to import the app — it failed immediately.
**Lesson:** "it works on my machine" is not a joke, it's a specific class of bug,
and cloning your own repo is a ten-second test that catches it.

### 6. Three bugs stacked in the database launcher

`npm run up` reported success and started nothing. Three independent faults:
the package was ESM, so `require()` returned a wrapper object and constructing
it threw; the daemon was spawned detached with output discarded, so the
exception vanished with no trace; and the readiness check tested whether the
*port* answered — and a leftover Docker container was answering on it.
**Fix:** handle the module interop, log uncaught exceptions to a file, and wait
for our own daemon to claim its PID file rather than trusting the port.
**Lesson:** a port answering is not proof that *your* process answered. Health
checks must be specific to your process, or they will confidently confirm the
wrong thing.

### 7. Cross-platform: three separate incompatibilities

Making it run on Windows was not one change. Python's `resource` module doesn't
exist there, so the import had to be guarded. `preexec_fn` doesn't exist either,
so process isolation had to be expressed differently — `CREATE_NEW_PROCESS_GROUP`
instead. And the default text encoding on Windows is cp1252, so any non-ASCII
character in a database driver's error message raised a `UnicodeDecodeError`
instead of showing you the error. **Fix:** guarded imports, platform-specific
isolation arguments, explicit UTF-8 everywhere. Plus fourteen new tests that
assert the platform behaviour structurally, so a regression fails on every OS
rather than only on the one nobody's testing on.

### 8. macOS memory limits don't mean what they say

`RLIMIT_AS` caps *reserved address space*, not memory actually in use. On macOS,
importing a normal database driver reserves enough to trip a 512MB cap
immediately. **Fix:** skip that specific limit on macOS rather than inflating it
to a number chosen to make the error go away. **Lesson:** if you can't state what
a limit means, it's not a control — it's a number that will produce a confusing
failure later.

### 9. A validator that only ever saw valid input

Early tests generated a connector and asserted it passed. All green, and
proving almost nothing — a checker that returns "pass" unconditionally also
passes that suite. **Fix:** deliberate fault injection. Connectors with hardcoded
passwords, string-concatenated SQL, bare excepts, missing type hints — each
asserted to be *caught*. **Lesson:** for a checker, the negative tests are the
real tests.

### 10. The model provider being unavailable

Development ran into a provider returning a hard error on every call, which
would have stopped work entirely if the system depended on it. **Fix:** an
`LLMClient` protocol with three real providers and a scripted client behind the
same interface. **Result:** 294 tests run in twelve seconds with no network, and
switching providers is one environment variable. **Lesson:** the dependency you
can't control is the one to put behind an interface first.

---

# The general question bank

Questions that aren't tied to one slide. Skim these the night before.

**Q: Is this actually an AI project, or is it a template engine with a chatbot in front?**
The best version of this question, and I'd answer it directly: the AI does one
job — turning an ambiguous human sentence into structured data, including
knowing what's missing. That's a genuinely hard problem and nothing else solves
it. Everything after that is deliberately not AI, because determinism is more
valuable there. If the criticism is that I used AI narrowly, I'd agree and say
it was the point.

**Q: What happens if the model gets better? Does this design become obsolete?**
Parts of it. Better models mean better extraction and fewer clarifying
questions, and both improve for free. But the reason the template writes the code
isn't that models are bad at code — it's that I want the same output every time
and I want to reason about all forty connectors at once. A better model doesn't
give me that.

**Q: How does this scale to a hundred data sources?**
Two axes. Source *types* scale by template, and that's real work per new shape,
though SQL dialects are cheap. Source *instances* scale trivially — a hundred
PostgreSQL databases are a hundred specs against one template. Most real backlogs
are the second kind, which is where this pays off.

**Q: What does one connector cost to produce?**
One model call for extraction, plus calls for the explanation document, plus
repair calls only when validation fails. So a clean run is a small number of
calls, and the expensive part — validation — is free because it's local
computation.

**Q: How do you know the generated connectors are correct, not just conformant?**
Conformance and correctness are different, and I wouldn't conflate them.
Conformance is the thirteen checks. Correctness is slide 10 — it connected to a
real database and returned a real schema. The combination is the argument: the
static checks prove it meets the standard, the sandbox proves it works.

**Q: Isn't there a risk people stop understanding their own connectors?**
It's a real risk with generated code generally. Two mitigations here: the output
is deliberately ordinary Python that a person can read, and every artifact ships
with a written explanation of what it does. But I wouldn't claim the risk is
zero — it's a reason to keep a human review step, which is why the pipeline has
review points rather than one button.

**Q: What was the hardest part?**
Not the generation. It was building a validation layer I actually trusted —
specifically, realising that a test suite full of passing cases proved nothing
about a checker, and rewriting the tests to inject faults on purpose. That
changed how I thought about the whole project.

**Q: If you had another month?**
Durable state, a background queue, and the drift watcher. In that order, because
the first two are what stop it being a demo and the third is what makes it worth
running continuously.

---

## Delivery notes

- **The one sentence to repeat.** *The model fills a form, a template writes the
  code, a checker decides what ships.* Say it on slide 3, slide 9, and slide 12.
  Repetition is how a room remembers an argument.
- **Say what doesn't work.** The in-memory store, the process-level sandbox, the
  four source types, the hand-maintained front-end types. Volunteering a limit
  before you're asked reads as command of the material; being caught out by one
  reads as the opposite.
- **When you don't know, say so and say what you'd do.** "I haven't measured
  that — here's how I would" is a strong answer. Improvising a number is not,
  and evaluators can tell.
- **Watch the clock at slide 5.** You should be finishing Technology at the
  21-minute mark. If you're past 24, drop the EXPAND blocks on slides 8 and 10
  and go straight through the screenshots.
- **Don't read the slides.** The bullets are there so the room can follow while
  you say something more than what's written.
