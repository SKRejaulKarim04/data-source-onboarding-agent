"""Build the project deck as a .pptx.

Run:  .venv/bin/python scripts/build_deck.py [--shots DIR] [--out FILE]

The deck is generated rather than hand-made so it can be rebuilt after the UI
changes: recapture the screenshots, re-run this, and the slides stay in sync.
Fonts are deliberately Arial and Courier New — they exist on every machine that
might open the file, which matters more here than typographic preference.
"""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    from pptx import Presentation
except ModuleNotFoundError as exc:  # pragma: no cover - a tooling dependency
    raise SystemExit(
        "python-pptx is not installed. Run:  .venv/bin/pip install python-pptx"
    ) from exc

from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR
from pptx.oxml.ns import qn
from pptx.oxml.xmlchemy import OxmlElement
from pptx.slide import Slide
from pptx.table import _Cell
from pptx.text.text import TextFrame
from pptx.util import Emu, Inches, Length, Pt

Stat = tuple[str, str, RGBColor]
Stage = tuple[str, str, str, RGBColor]
Item = str | tuple[str, str]

# --- Palette, taken from the application's own tokens ------------------------

BG = RGBColor(0x0A, 0x0F, 0x1C)
SURFACE = RGBColor(0x11, 0x18, 0x27)
RULE = RGBColor(0x1F, 0x2A, 0x40)
TEXT = RGBColor(0xE8, 0xED, 0xF5)
DIM = RGBColor(0x88, 0x96, 0xB0)
MUTED = RGBColor(0x4B, 0x59, 0x75)
ACCENT = RGBColor(0x60, 0xA5, 0xFA)
GREEN = RGBColor(0x34, 0xD3, 0x99)
AMBER = RGBColor(0xFB, 0xBF, 0x24)
RED = RGBColor(0xF8, 0x71, 0x71)

SANS = "Arial"
MONO = "Courier New"

W = Inches(13.333)
H = Inches(7.5)
MARGIN = Inches(0.75)


# --- Primitives --------------------------------------------------------------


def blank(prs: Presentation) -> Slide:
    """A slide with no placeholders, painted with the deck background."""
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    bg = slide.shapes.add_shape(1, 0, 0, W, H)  # 1 = rectangle
    bg.fill.solid()
    bg.fill.fore_color.rgb = BG
    bg.line.fill.background()
    bg.shadow.inherit = False
    return slide


def textbox(slide: Slide, left: Length, top: Length, width: Length, height: Length) -> TextFrame:
    box = slide.shapes.add_textbox(left, top, width, height)
    frame = box.text_frame
    frame.word_wrap = True
    frame.margin_left = frame.margin_right = 0
    frame.margin_top = frame.margin_bottom = 0
    return frame


def para(
    frame: TextFrame,
    text: str,
    *,
    size: float,
    color: RGBColor,
    bold: bool = False,
    font: str = SANS,
    space_after: int = 6,
    first: bool = False,
) -> None:
    p = frame.paragraphs[0] if first else frame.add_paragraph()
    p.text = text
    p.space_after = Pt(space_after)
    for run in p.runs:
        run.font.size = Pt(size)
        run.font.color.rgb = color
        run.font.bold = bold
        run.font.name = font


def eyebrow(slide: Slide, text: str, top: Length | None = None) -> None:
    frame = textbox(slide, MARGIN, top or Inches(0.5), Inches(11), Inches(0.3))
    para(frame, text.upper(), size=11, color=MUTED, bold=True, font=MONO, first=True)


def heading(slide: Slide, text: str, top: Length | None = None, size: int = 30) -> None:
    frame = textbox(slide, MARGIN, top or Inches(0.85), Inches(11.8), Inches(1.0))
    para(frame, text, size=size, color=TEXT, bold=True, first=True)


def rule(slide: Slide, top: Length, width: Length | None = None, color: RGBColor = RULE) -> None:
    line = slide.shapes.add_shape(1, MARGIN, top, width or Inches(11.8), Emu(9525))
    line.fill.solid()
    line.fill.fore_color.rgb = color
    line.line.fill.background()
    line.shadow.inherit = False


def _cell_borders(cell: _Cell, colour: RGBColor = RULE, width_pt: float = 1.0) -> None:
    """Set a cell's four borders.

    python-pptx has no API for this, and the default a renderer picks is a white
    hairline — which is loud on a dark deck. Written straight into the cell's
    XML properties instead.
    """
    tc_pr = cell._tc.get_or_add_tcPr()
    for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
        for existing in tc_pr.findall(qn(tag)):
            tc_pr.remove(existing)
        ln = OxmlElement(tag)
        ln.set("w", str(int(width_pt * 12700)))
        ln.set("cap", "flat")
        fill = OxmlElement("a:solidFill")
        clr = OxmlElement("a:srgbClr")
        clr.set("val", f"{colour}")
        fill.append(clr)
        ln.append(fill)
        tc_pr.append(ln)


def card(
    slide: Slide,
    left: Length,
    top: Length,
    width: Length,
    height: Length,
    *,
    accent: RGBColor | None = None,
) -> None:
    box = slide.shapes.add_shape(1, left, top, width, height)
    box.fill.solid()
    box.fill.fore_color.rgb = SURFACE
    box.line.color.rgb = accent or RULE
    box.line.width = Pt(1.25)
    box.shadow.inherit = False


# --- Slide kinds -------------------------------------------------------------


def title_slide(prs: Presentation, title: str, subtitle: str, footer: str) -> None:
    slide = blank(prs)
    bar = slide.shapes.add_shape(1, 0, Inches(2.62), Inches(0.09), Inches(1.5))
    bar.fill.solid()
    bar.fill.fore_color.rgb = ACCENT
    bar.line.fill.background()
    bar.shadow.inherit = False

    frame = textbox(slide, MARGIN, Inches(2.5), Inches(11.5), Inches(2.4))
    para(frame, title, size=46, color=TEXT, bold=True, space_after=14, first=True)
    para(frame, subtitle, size=19, color=DIM, space_after=0)

    foot = textbox(slide, MARGIN, Inches(6.5), Inches(11.5), Inches(0.5))
    para(foot, footer, size=12, color=MUTED, font=MONO, first=True)


def bullets_slide(
    prs: Presentation,
    eyebrow_text: str,
    title: str,
    items: list[Item],
    *,
    note: str | None = None,
) -> None:
    slide = blank(prs)
    eyebrow(slide, eyebrow_text)
    heading(slide, title)
    rule(slide, Inches(1.85))

    frame = textbox(slide, MARGIN, Inches(2.15), Inches(11.8), Inches(4.4))
    first = True
    for item in items:
        if isinstance(item, tuple):
            lead, body = item
            para(frame, lead, size=17, color=TEXT, bold=True, space_after=3, first=first)
            para(frame, body, size=14.5, color=DIM, space_after=16)
        else:
            para(frame, item, size=16, color=DIM, space_after=12, first=first)
        first = False

    if note:
        nf = textbox(slide, MARGIN, Inches(6.55), Inches(11.8), Inches(0.6))
        para(nf, note, size=12.5, color=DIM, font=MONO, first=True)


def image_slide(
    prs: Presentation, eyebrow_text: str, title: str, image_path: Path, caption: str
) -> None:
    """Full-width screenshot with a title above and one line of context below."""
    slide = blank(prs)
    eyebrow(slide, eyebrow_text, top=Inches(0.42))
    frame = textbox(slide, MARGIN, Inches(0.72), Inches(11.8), Inches(0.5))
    para(frame, title, size=24, color=TEXT, bold=True, first=True)

    pic_h = Inches(5.22)
    pic_w = Emu(int(pic_h * 16 / 9))
    left = Emu(int((W - pic_w) / 2))
    slide.shapes.add_picture(str(image_path), left, Inches(1.3), width=pic_w, height=pic_h)

    cap = textbox(slide, MARGIN, Inches(6.68), Inches(11.8), Inches(0.55))
    para(cap, caption, size=13, color=DIM, first=True)


def stat_slide(
    prs: Presentation,
    eyebrow_text: str,
    title: str,
    stats: list[Stat],
    footer: str | None = None,
) -> None:
    slide = blank(prs)
    eyebrow(slide, eyebrow_text)
    heading(slide, title)
    rule(slide, Inches(1.85))

    cols = len(stats)
    gap = Inches(0.3)
    total = Inches(11.8)
    width = Emu(int((total - gap * (cols - 1)) / cols))
    for i, (value, label, colour) in enumerate(stats):
        left = Emu(int(MARGIN + i * (width + gap)))
        card(slide, left, Inches(2.35), width, Inches(2.0))
        vf = textbox(
            slide,
            Emu(int(left + Inches(0.28))),
            Inches(2.7),
            Emu(int(width - Inches(0.56))),
            Inches(1.0),
        )
        para(vf, value, size=40, color=colour, bold=True, first=True)
        lf = textbox(
            slide,
            Emu(int(left + Inches(0.28))),
            Inches(3.55),
            Emu(int(width - Inches(0.56))),
            Inches(0.7),
        )
        para(lf, label, size=12.5, color=DIM, first=True)

    if footer:
        ff = textbox(slide, MARGIN, Inches(5.0), Inches(11.8), Inches(1.2))
        para(ff, footer, size=15, color=DIM, first=True)


def pipeline_slide(
    prs: Presentation, eyebrow_text: str, title: str, stages: list[Stage], footer: str
) -> None:
    slide = blank(prs)
    eyebrow(slide, eyebrow_text)
    heading(slide, title)
    rule(slide, Inches(1.85))

    n = len(stages)
    gap = Inches(0.22)
    total = Inches(11.8)
    width = Emu(int((total - gap * (n - 1)) / n))
    for i, (name, detail, tag, colour) in enumerate(stages):
        left = Emu(int(MARGIN + i * (width + gap)))
        card(slide, left, Inches(2.4), width, Inches(2.25), accent=colour if tag else None)
        inner = Emu(int(width - Inches(0.4)))
        nf = textbox(slide, Emu(int(left + Inches(0.2))), Inches(2.62), inner, Inches(0.5))
        para(nf, f"{i + 1}", size=12, color=colour, bold=True, font=MONO, first=True)
        tf = textbox(slide, Emu(int(left + Inches(0.2))), Inches(3.0), inner, Inches(0.5))
        para(tf, name, size=16, color=TEXT, bold=True, first=True)
        df = textbox(slide, Emu(int(left + Inches(0.2))), Inches(3.45), inner, Inches(1.0))
        para(df, detail, size=11, color=DIM, font=MONO, first=True)
        if tag:
            gf = textbox(slide, Emu(int(left + Inches(0.2))), Inches(4.22), inner, Inches(0.3))
            para(gf, tag, size=9.5, color=colour, bold=True, font=MONO, first=True)

    ff = textbox(slide, MARGIN, Inches(5.15), Inches(11.8), Inches(1.6))
    para(ff, footer, size=15, color=DIM, first=True)


def table_slide(
    prs: Presentation,
    eyebrow_text: str,
    title: str,
    headers: list[str],
    rows: list[list[str]],
    *,
    note: str | None = None,
) -> None:
    slide = blank(prs)
    eyebrow(slide, eyebrow_text)
    heading(slide, title)
    rule(slide, Inches(1.85))

    shape = slide.shapes.add_table(
        len(rows) + 1, len(headers), MARGIN, Inches(2.2), Inches(11.8), Inches(0.4)
    )
    table = shape.table
    for c, text in enumerate(headers):
        cell = table.cell(0, c)
        cell.text = text
        cell.fill.solid()
        cell.fill.fore_color.rgb = SURFACE
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE
        _cell_borders(cell)
        for p in cell.text_frame.paragraphs:
            for run in p.runs:
                run.font.size = Pt(12)
                run.font.bold = True
                run.font.color.rgb = DIM
                run.font.name = MONO
    for r, row in enumerate(rows, start=1):
        for c, text in enumerate(row):
            cell = table.cell(r, c)
            cell.text = text
            cell.fill.solid()
            cell.fill.fore_color.rgb = BG
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            _cell_borders(cell)
            for p in cell.text_frame.paragraphs:
                for run in p.runs:
                    run.font.size = Pt(13)
                    run.font.color.rgb = TEXT if c == 0 else DIM
                    run.font.name = SANS
                    run.font.bold = c == 0

    if note:
        nf = textbox(slide, MARGIN, Inches(6.5), Inches(11.8), Inches(0.6))
        para(nf, note, size=12.5, color=DIM, font=MONO, first=True)


def closing_slide(prs: Presentation, title: str, lines: list[str], footer: str) -> None:
    slide = blank(prs)
    frame = textbox(slide, MARGIN, Inches(2.3), Inches(11.5), Inches(1.0))
    para(frame, title, size=38, color=TEXT, bold=True, first=True)
    body = textbox(slide, MARGIN, Inches(3.4), Inches(10.5), Inches(2.6))
    first = True
    for line in lines:
        para(body, line, size=17, color=DIM, space_after=14, first=first)
        first = False
    foot = textbox(slide, MARGIN, Inches(6.5), Inches(11.5), Inches(0.5))
    para(foot, footer, size=12, color=MUTED, font=MONO, first=True)


# --- The deck ----------------------------------------------------------------


def build(shots: Path, out: Path) -> Path:
    prs = Presentation()
    prs.slide_width = W
    prs.slide_height = H

    title_slide(
        prs,
        "Data Source Onboarding Agent",
        "Plain English in. A validated, standards-compliant, versioned Python connector out.",
        "Natural language → spec → generated code → machine-checked → proven against a live "
        "database",
    )

    bullets_slide(
        prs,
        "Business objective",
        "Onboarding a data source is slow, and the cost is repetition",
        [
            (
                "Every new source is hand-written work",
                "A data engineer writes connection handling, retries, schema introspection and "
                "docs"
                "again — the same five methods, slightly differently each time.",
            ),
            (
                "Consistency decays with headcount",
                "Ten engineers produce ten interpretations of 'read-only' and 'secrets from the "
                "environment'. Review catches some of it, some of the time.",
            ),
            (
                "The standards are real, and unevenly applied",
                "No hardcoded credentials, no dynamic SQL, typed, documented. Everyone agrees; "
                "nothing enforces it until code review, which is a person having a bad afternoon.",
            ),
        ],
    )

    stat_slide(
        prs,
        "Business objective",
        "What this changes",
        [
            ("Minutes", "from request to reviewed connector, instead of days", GREEN),
            ("100%", "of generated connectors meet all 13 standards, or are rejected", ACCENT),
            ("Every artifact", "traceable to the request that produced it", AMBER),
        ],
        footer="The goal is not to remove the engineer. It is to remove the part of the "
        "job that is identical every time, and to make the standards structural rather "
        "than remembered.",
    )

    bullets_slide(
        prs,
        "The core idea",
        "The tension — and how it is resolved",
        [
            (
                "The tension",
                "Free-form English is unpredictable. Production code must be guaranteed. "
                "Letting a language model write the connector puts an unreliable component in "
                "the one place reliability is non-negotiable.",
            ),
            (
                "The resolution: the model never writes the code",
                "It fills in a structured spec — schema-enforced, so it selects from closed sets "
                "rather than inventing strings. A Jinja2 template renders the code, "
                "deterministically. Same spec in, same bytes out.",
            ),
            (
                "Reliability comes from constraint, not from prompting",
                "The model does what models are good at — reading intent from messy language. "
                "The template does what templates are good at — producing exactly the same thing "
                "every time.",
            ),
        ],
        note="This is the single design decision the rest of the project follows from.",
    )

    pipeline_slide(
        prs,
        "Architecture",
        "One request, five stages",
        [
            ("Extract", "SpecExtractor\n.extract()", "1 model call", ACCENT),
            ("Refine", "SpecExtractor\n.refine()", "no model call", GREEN),
            ("Generate", "ConnectorGenerator\n.generate()", "model on repair", AMBER),
            ("Test", "ConnectionSandbox\n.run()", "subprocess", AMBER),
            ("Deliver", "Artifact\n.to_zip()", "deterministic", GREEN),
        ],
        footer="Only three stages can call the model, and two of those only when something has "
        "already failed. Answering a clarifying question is pure arithmetic — the answers map "
        "onto known fields, so a second extraction can never re-misread what you already settled.",
    )

    # --- The working product -------------------------------------------------

    image_slide(
        prs,
        "The product · 1 of 6",
        "Describe the source in plain English",
        shots / "01-welcome.png",
        "No forms, no connection wizard. Three worked examples are built in for a cold start.",
    )
    image_slide(
        prs,
        "The product · 2 of 6",
        "When the request is incomplete, the agent asks",
        shots / "02-clarification.png",
        "Host was never stated, so it is not invented. Confidence drops to 55%, the missing field "
        "is"
        "named, and the question carries an example — a templated question, not model-authored "
        "prose.",
    )
    image_slide(
        prs,
        "The product · 3 of 6",
        "Extraction, generation, and the standards gate",
        shots / "04-standards.png",
        "Everything the agent understood is shown for review — including what it assumed. "
        "13 of 13 checks pass, so the artifact is accepted.",
    )
    image_slide(
        prs,
        "The product · 4 of 6",
        "The generated connector",
        shots / "05-code.png",
        "Provenance above the code: template version, spec checksum, code checksum, repair count. "
        "Written by a template, never by the model.",
    )
    image_slide(
        prs,
        "The product · 5 of 6",
        "Proven against a real database, not just compiled",
        shots / "06-connection.png",
        "Executed in a sandboxed subprocess against live PostgreSQL. Three tables discovered with "
        "their primary keys. Credentials are sent once and never stored, logged, or written to the "
        "artifact.",
    )
    image_slide(
        prs,
        "The product · 6 of 6",
        "The handover artifact",
        shots / "07-artifact.png",
        "Connector, README, requirements, explanation and a manifest — packaged as a versioned zip "
        "with a checksum over the whole bundle.",
    )

    # --- How it is built -----------------------------------------------------

    table_slide(
        prs,
        "Technology",
        "The stack, and why each piece is there",
        ["Layer", "Choice", "Why this one"],
        [
            [
                "API",
                "FastAPI + Pydantic v2",
                "Schema validation at the boundary, not in the handlers",
            ],
            ["Spec", "Pydantic models", "Permissive draft, then promotion to a strict spec"],
            ["Codegen", "Jinja2", "Deterministic. The reason the standards guarantee holds"],
            [
                "Validation",
                "ast + ruff + black + bandit",
                "Parsed, never imported — importing runs it",
            ],
            ["Database", "SQLAlchemy 2.0", "One connector shape across three SQL dialects"],
            ["Sandbox", "subprocess + rlimits", "Timeout, memory cap, allowlisted environment"],
            [
                "Front end",
                "React 18 + TypeScript + Vite",
                "Built to static files, served by the same process",
            ],
            ["Tests", "pytest — 280 of them", "Including deliberate fault injection"],
        ],
        note="No orchestration framework. The pipeline is six modules and a function call chain.",
    )

    bullets_slide(
        prs,
        "Design · quality",
        "What happens when generation goes wrong",
        [
            (
                "13 AST checks, run on parsed source",
                "no-hardcoded-credentials · no-dynamic-sql · env-for-secrets · no-dangerous-calls "
                "·"
                "type-hints · docstrings · and seven more. The code is never imported to be "
                "checked.",
            ),
            (
                "A bounded repair loop with a regression guard",
                "At most three attempts, and a candidate is adopted only if it strictly reduces "
                "the"
                "error count. The returned code is never worse than the input.",
            ),
            (
                "Rejection is a rendered outcome, not a crash",
                "A failing connector still comes back, with its findings, so a reviewer can see "
                "exactly what went wrong.",
            ),
            (
                "The checker is tested against bad input",
                "npm run generate:faults injects a hardcoded password, an eval(), an f-string SQL "
                "query. A checker that has only seen good input has demonstrated nothing.",
            ),
        ],
    )

    bullets_slide(
        prs,
        "Design · security",
        "Secrets never touch the artifact",
        [
            (
                "Scrubbed at input",
                "Credentials are redacted before the prompt reaches the model, and the stored "
                "record holds the scrubbed copy — so a pasted password cannot resurface in a later "
                "response.",
            ),
            (
                "Structurally impossible in the output",
                "Two AST checks make a literal credential a rejection rather than a review "
                "comment.",
            ),
            (
                "Names only in the manifest",
                "The bundle records which environment variables are required, never their values.",
            ),
            (
                "Transient at test time",
                "The sandbox child gets an allowlisted environment — not a denylist, because a "
                "denylist exposes every newly added secret until someone remembers to update it.",
            ),
        ],
    )

    image_slide(
        prs,
        "Design · provenance",
        "Every artifact answers 'where did this come from?'",
        shots / "08-manifest.png",
        "Request → spec checksum → template version → code checksum → artifact version. "
        "Packaging is byte-reproducible: the zip uses a fixed timestamp, not the clock.",
    )

    bullets_slide(
        prs,
        "Design · interface",
        "Why the UI looks like a conversation",
        [
            (
                "The interaction is a dialogue, so the interface is one",
                "The agent asks when it is unsure. A form cannot do that; a thread can.",
            ),
            (
                "Evidence sits beside the conversation, not inside it",
                "Standards, code, connection and artifact live in a persistent right-hand panel, "
                "so a reviewer can check the output without losing the thread.",
            ),
            (
                "The server owns state; the thread is a log of how it was reached",
                "Reopening a request replays it from stored state rather than a saved transcript — "
                "the backend stores state, not conversation, and pretending otherwise would drift.",
            ),
        ],
        note="React 18 + TypeScript · built to static files · served by the API process · no CORS "
        "anywhere",
    )

    table_slide(
        prs,
        "Honest assessment",
        "What is deliberately not built yet",
        ["Gap", "Current state", "What it needs"],
        [
            ["Authentication", "None on the API", "Anyone reaching the port can generate and test"],
            [
                "Persistence",
                "In-memory dict",
                "Object storage keyed by code checksum + Postgres metadata",
            ],
            ["Audit trail", "Per-request activity log", "Who tested which target, durably"],
            ["Egress control", "Unrestricted", "The same sandbox inside a container, allowlisted"],
            ["Auth methods", "2 of 6 have templates", "OAuth2 needs token caching the shape lacks"],
            ["Concurrency", "Single worker", "Falls out of the persistence work"],
        ],
        note="A design note that lists only strengths is a sales sheet.",
    )

    bullets_slide(
        prs,
        "Roadmap",
        "The next phase: generate MCP servers, not just connectors",
        [
            (
                "Same sentence, second output target",
                "Describe a database in English; receive a read-only MCP server that any AI client "
                "can query — gated by the same standards pipeline.",
            ),
            (
                "The architecture already fits",
                "The registry is versioned and pluggable, the checks are a list, and the sandbox "
                "already spawns a subprocess and parses structured JSON from its stdout — which is "
                "most of what speaking MCP over stdio requires.",
            ),
            (
                "It needs checks a connector does not",
                "A tool's docstring is the description the model reads. An unbounded SELECT fills "
                "a"
                "context window rather than crashing. A query(sql) tool hands arbitrary SQL to a "
                "model.",
            ),
        ],
        note="Estimated 8–12 days, starting with a half-day spike that makes the rest refutable.",
    )

    closing_slide(
        prs,
        "The claim, in one line",
        [
            "The model reads intent. The template writes the code. The checker decides what ships.",
            "",
            "That separation is what turns a demo into something you could put in front of a "
            "review board — and it is why the guarantee holds for the next connector, not just "
            "this one.",
        ],
        "280 tests · 13 standards checks · 4 source types · 100% conformance on accepted artifacts",
    )

    out.parent.mkdir(parents=True, exist_ok=True)
    prs.save(str(out))
    return out


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--shots", type=Path, default=root / "docs" / "screenshots")
    ap.add_argument("--out", type=Path, default=root / "docs" / "Data-Source-Onboarding-Agent.pptx")
    args = ap.parse_args()

    missing = [
        name
        for name in (
            "01-welcome.png",
            "02-clarification.png",
            "04-standards.png",
            "05-code.png",
            "06-connection.png",
            "07-artifact.png",
            "08-manifest.png",
        )
        if not (args.shots / name).is_file()
    ]
    if missing:
        raise SystemExit(f"Missing screenshots in {args.shots}: {', '.join(missing)}")

    path = build(args.shots, args.out)
    print(f"Wrote {path} ({path.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
