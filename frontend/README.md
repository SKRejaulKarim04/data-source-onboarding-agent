# Front end

React 18 + TypeScript + Vite. Built to `dist/`, which the FastAPI app serves at
`/` — one origin for the UI and the API, so there is no CORS configuration
anywhere in this project.

```bash
npm run dev         # from the repo root: Vite on :5173 + uvicorn on :8001
npm run ui:build    # from the repo root: build dist/
npm run ui:typecheck
```

Run from this directory, `npm run dev` expects an API on `http://127.0.0.1:8001`
(override with `DSOA_API_URL`). The repo-root `npm run dev` starts that for you.

## How it is put together

```
src/
├── api/
│   ├── types.ts        mirrors src/dsoa/api/main.py field for field
│   └── client.ts       the only module that calls fetch()
├── hooks/
│   ├── useOnboarding.ts   every action the app can take, in one place
│   ├── useResizer.ts      drag-to-resize a column, persisted per user
│   ├── useHealth.ts       live model vs scripted fallback
│   └── useViewportWidth.ts
├── types/chat.ts       the discriminated union the thread is made of
├── components/
│   ├── Header, Sidebar, Resizer, Icons
│   ├── chat/           thread, bubbles, extraction card, questions, input bar
│   └── output/         one file per tab + the Python highlighter
└── styles/             tokens.css → base.css → primitives.css
```

Three ideas carry most of the weight:

**The server owns state; the thread is a log.** Every action replaces one
`OnboardingRequest` object with whatever the API returned, then appends the
bubbles that describe it. Reopening a request from the sidebar replays a thread
from the stored payload rather than restoring a saved transcript — the backend
stores state, not conversation, and pretending otherwise would drift.

**Stages that have not run come back as `{}`.** The API sends an empty object for
`extraction`, `connector`, `sandbox` and `artifact` until each stage produces
something. `api/types.ts` turns that into four type guards, so a component either
has a whole `Connector` or renders an empty state — never a half-populated one.

**Credentials never outlive the test.** The connection form is keyed by request
id, so switching requests unmounts it and drops what you typed. Nothing about
credentials reaches `localStorage`, the artifact, or the manifest, which records
variable *names* only.
