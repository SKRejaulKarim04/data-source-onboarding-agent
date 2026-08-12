# Deck & assets

**[Data-Source-Onboarding-Agent.pptx](Data-Source-Onboarding-Agent.pptx)** — 12 slides,
16:9: the business case, the design guarantee, the pipeline architecture, the stack,
screenshots of every section of the working app, and how each artifact stays
explicable months later.

Deliberately short. The deeper material lives in [DESIGN_NOTES.md](../DESIGN_NOTES.md)
(decisions, trade-offs, what is not built) and [WORKFLOW.md](../WORKFLOW.md)
(the execution map) rather than in slides nobody reaches.

Rebuild it after a UI change:

```bash
npm run serve                       # or any running instance
# recapture screenshots into docs/screenshots/, then:
.venv/bin/python scripts/build_deck.py
```

`scripts/build_deck.py` generates the file rather than editing it by hand, so the
slides stay in sync with the product instead of drifting from it.

## Screenshots

Captured at 2× from the running application against a live seeded PostgreSQL.

| file | shows |
| --- | --- |
| `01-welcome.png` | empty state with the three worked examples |
| `02-clarification.png` | the agent asking for a field it refused to invent |
| `03-extraction-and-standards.png` | extraction result beside the standards panel |
| `04-standards.png` | 13 of 13 checks passing, artifact accepted |
| `05-code.png` | the generated connector, with provenance |
| `06-connection.png` | a live connection test and the discovered schema |
| `07-artifact.png` | the packaged bundle and its checksum |
| `08-manifest.png` | the provenance manifest |
