import { useMemo } from "react";
import "./PythonCode.css";

/**
 * A small Python highlighter.
 *
 * Deliberately regex-based and deliberately not a dependency: the panel shows
 * one generated module, and a full tokenizer would be more code than the app it
 * decorates. The one invariant that matters is that the rendered text equals
 * the input exactly — the tokenizer emits the gaps between matches verbatim, so
 * nothing can be silently dropped from code a reviewer is about to trust.
 */

const KEYWORDS = [
  "False", "None", "True", "and", "as", "assert", "async", "await", "break",
  "continue", "del", "elif", "else", "except", "finally", "for", "from",
  "global", "if", "import", "in", "is", "lambda", "nonlocal", "not", "or",
  "pass", "raise", "return", "try", "while", "with", "yield",
];

const BUILTINS = [
  "self", "cls", "print", "len", "str", "int", "float", "bool", "list", "dict",
  "set", "tuple", "range", "enumerate", "zip", "open", "isinstance", "type",
  "super", "getattr", "setattr", "hasattr", "Exception", "ValueError",
  "TypeError", "KeyError", "RuntimeError", "ConnectionError",
];

const PATTERN = new RegExp(
  [
    "(?<comment>#[^\\n]*)",
    // Triple-quoted first, so a docstring is not eaten as three empty strings.
    "(?<string>'''[\\s\\S]*?'''|\"\"\"[\\s\\S]*?\"\"\"|'(?:\\\\.|[^'\\\\\\n])*'|\"(?:\\\\.|[^\"\\\\\\n])*\")",
    "(?<decorator>@[A-Za-z_][\\w.]*)",
    // `def name` / `class Name` as one match so the name can be coloured too.
    "(?<defkw>\\b(?:def|class))(?<defgap>[ \\t]+)(?<defname>[A-Za-z_]\\w*)",
    `(?<keyword>\\b(?:${KEYWORDS.join("|")})\\b)`,
    `(?<builtin>\\b(?:${BUILTINS.join("|")})\\b)`,
    "(?<number>\\b0[xXbBoO][0-9a-fA-F_]+\\b|\\b\\d[\\d_]*(?:\\.[\\d_]+)?(?:[eE][+-]?\\d+)?\\b)",
  ].join("|"),
  "g",
);

interface Token {
  text: string;
  className: string | null;
}

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  let cursor = 0;

  for (const match of source.matchAll(PATTERN)) {
    const start = match.index ?? 0;
    if (start > cursor) {
      tokens.push({ text: source.slice(cursor, start), className: null });
    }

    const groups = match.groups ?? {};
    if (groups.defkw !== undefined) {
      // Three tokens from one match: keyword, whitespace, name.
      tokens.push({ text: groups.defkw, className: "tok-keyword" });
      tokens.push({ text: groups.defgap ?? "", className: null });
      tokens.push({ text: groups.defname ?? "", className: "tok-def" });
    } else {
      tokens.push({ text: match[0], className: classFor(groups) });
    }

    cursor = start + match[0].length;
  }

  if (cursor < source.length) {
    tokens.push({ text: source.slice(cursor), className: null });
  }
  return tokens;
}

function classFor(groups: Record<string, string | undefined>): string | null {
  for (const name of [
    "comment",
    "string",
    "decorator",
    "keyword",
    "builtin",
    "number",
  ]) {
    if (groups[name] !== undefined) return `tok-${name}`;
  }
  return null;
}

/** Regroup a flat token stream into one array per source line. */
function toLines(tokens: Token[]): Token[][] {
  const lines: Token[][] = [[]];

  for (const token of tokens) {
    const parts = token.text.split("\n");
    parts.forEach((part, index) => {
      if (index > 0) lines.push([]);
      if (part) lines[lines.length - 1]!.push({ ...token, text: part });
    });
  }
  return lines;
}

interface PythonCodeProps {
  code: string;
}

export function PythonCode({ code }: PythonCodeProps) {
  const lines = useMemo(() => toLines(tokenize(code)), [code]);

  return (
    <pre className="code code-with-lines">
      <code>
        {lines.map((tokens, lineIndex) => (
          <span className="code-line" key={lineIndex}>
            <span className="ln" aria-hidden="true">
              {lineIndex + 1}
            </span>
            <span className="lc">
              {tokens.map((token, index) =>
                token.className ? (
                  <span className={token.className} key={index}>
                    {token.text}
                  </span>
                ) : (
                  <span key={index}>{token.text}</span>
                ),
              )}
            </span>
          </span>
        ))}
      </code>
    </pre>
  );
}
