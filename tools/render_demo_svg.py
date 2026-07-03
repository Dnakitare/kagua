#!/usr/bin/env python3
"""Regenerate docs/demo.svg, the README's lead image, from the live demo.

Runs `kagua check fixtures/workorder/ --color always` and converts the ANSI
output to a terminal-styled SVG. Deterministic: same verdict, same bytes.
Run after any change that alters the demo output.
"""
import os
import re
import subprocess
import sys
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "demo.svg")

BG = "#161b22"
CHROME = "#21262d"
FG = "#e6edf3"
COLORS = {
    "31": "#f85149",  # red
    "32": "#3fb950",  # green
    "33": "#d29922",  # yellow
    "2": "#8b949e",   # dim
}
FONT = "SFMono-Regular, Menlo, Consolas, 'Liberation Mono', monospace"
FONT_SIZE = 13
CHAR_W = 7.8
LINE_H = 20
PAD_X = 20
PAD_TOP = 56
PAD_BOTTOM = 20

ANSI = re.compile(r"\033\[([0-9;]*)m")


def runs_for_line(line):
    """Split one line of ANSI text into (text, color, bold) runs."""
    runs = []
    pos = 0
    color, bold = FG, False
    for m in ANSI.finditer(line):
        if m.start() > pos:
            runs.append((line[pos : m.start()], color, bold))
        codes = m.group(1).split(";") if m.group(1) else ["0"]
        for c in codes:
            if c in ("0", ""):
                color, bold = FG, False
            elif c == "1":
                bold = True
            elif c in COLORS:
                color = COLORS[c]
        pos = m.end()
    if pos < len(line):
        runs.append((line[pos:], color, bold))
    return runs


def main():
    proc = subprocess.run(
        [sys.executable, "-m", "kagua.cli", "check",
         os.path.join(ROOT, "fixtures", "workorder") + os.sep,
         "--color", "always"],
        capture_output=True, text=True, cwd=ROOT,
    )
    if proc.returncode != 1:
        raise SystemExit(f"demo no longer fails with exit 1 (got {proc.returncode}); fix that first")
    raw = proc.stdout.replace(ROOT + os.sep, "")
    lines = ["$ kagua check fixtures/workorder/", ""] + raw.rstrip("\n").split("\n")

    plain = [ANSI.sub("", l) for l in lines]
    width = int(max(len(l) for l in plain) * CHAR_W) + 2 * PAD_X
    height = PAD_TOP + LINE_H * len(lines) + PAD_BOTTOM

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}"'
        f' viewBox="0 0 {width} {height}" role="img"'
        ' aria-label="kagua check failing the work-order demo on a Composition violation">',
        f'<rect width="{width}" height="{height}" rx="10" fill="{BG}"/>',
        f'<rect width="{width}" height="36" rx="10" fill="{CHROME}"/>',
        f'<rect y="26" width="{width}" height="10" fill="{CHROME}"/>',
        '<circle cx="20" cy="18" r="6" fill="#ff5f57"/>',
        '<circle cx="40" cy="18" r="6" fill="#febc2e"/>',
        '<circle cx="60" cy="18" r="6" fill="#28c840"/>',
        f'<text x="{width / 2:.0f}" y="22" text-anchor="middle" fill="#8b949e"'
        f' font-family="{FONT}" font-size="12">kagua check</text>',
    ]
    y = PAD_TOP
    for line in lines:
        spans = []
        for text, color, bold in runs_for_line(line):
            if not text:
                continue
            weight = ' font-weight="bold"' if bold else ""
            spans.append(f'<tspan fill="{color}"{weight}>{escape(text)}</tspan>')
        if line.startswith("$ "):
            spans = [f'<tspan fill="#3fb950">$</tspan><tspan fill="{FG}">{escape(line[1:])}</tspan>']
        if spans:
            parts.append(
                f'<text x="{PAD_X}" y="{y}" xml:space="preserve"'
                f' font-family="{FONT}" font-size="{FONT_SIZE}">{"".join(spans)}</text>'
            )
        y += LINE_H
    parts.append("</svg>")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts) + "\n")
    print(f"wrote {OUT} ({len(lines)} lines, {width}x{height})")


if __name__ == "__main__":
    main()
