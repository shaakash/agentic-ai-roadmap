"""Convert a Markdown doc to a clean, print-optimized standalone HTML file.

Usage:
    python scripts/md_to_html.py docs/10-interview-qa.md

Produces docs/10-interview-qa.html next to the source. Open it in any browser
and use Cmd+P → "Save as PDF" (or print directly). The CSS is tuned for paper:
readable serif body, section page-breaks, and code blocks that wrap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import markdown

_CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
    font-family: -apple-system, "Helvetica Neue", Arial, sans-serif;
    font-size: 11.5px; line-height: 1.55; color: #1a1a2e;
    max-width: 860px; margin: 0 auto; padding: 24px;
}
h1 { font-size: 26px; border-bottom: 3px solid #2d6a4f; padding-bottom: 8px; color: #1b4332; }
h2 {
    font-size: 19px; margin-top: 34px; color: #1b4332;
    border-bottom: 1px solid #cde0d4; padding-bottom: 5px;
    page-break-before: auto; page-break-after: avoid;
}
h3 { font-size: 15px; margin-top: 22px; color: #2d3a4f; page-break-after: avoid; }
h3:has(+ blockquote), h3 { page-break-inside: avoid; }
p, li { orphans: 3; widows: 3; }
code {
    font-family: "SF Mono", Menlo, Consolas, monospace; font-size: 10.5px;
    background: #f0f3f1; padding: 1px 5px; border-radius: 4px; color: #6d2b3d;
}
pre {
    background: #f7f9f8; border: 1px solid #dde8e2; border-left: 4px solid #2d6a4f;
    border-radius: 6px; padding: 12px 14px; overflow-x: auto;
    white-space: pre-wrap; word-wrap: break-word; page-break-inside: avoid;
}
pre code { background: none; color: #1a1a2e; padding: 0; }
blockquote {
    margin: 10px 0; padding: 8px 16px; border-left: 4px solid #b5838d;
    background: #fbf6f7; border-radius: 0 6px 6px 0; page-break-inside: avoid;
}
table {
    border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 10.5px;
    page-break-inside: avoid;
}
th, td { border: 1px solid #cdd8d2; padding: 6px 9px; text-align: left; vertical-align: top; }
th { background: #2d6a4f; color: #fff; }
tr:nth-child(even) td { background: #f5f8f6; }
a { color: #2d6a4f; text-decoration: none; }
hr { border: none; border-top: 1px solid #dde8e2; margin: 26px 0; }
ul, ol { padding-left: 22px; }
strong { color: #1b4332; }
.toc-note {
    background: #eef5f0; border: 1px dashed #2d6a4f; border-radius: 6px;
    padding: 10px 14px; font-size: 10.5px; margin: 16px 0;
}
@media print {
    body { padding: 0; max-width: none; }
    a { color: #1a1a2e; }
}
"""


def convert(src_path: str) -> Path:
    src = Path(src_path)
    if not src.exists():
        raise FileNotFoundError(src)

    text = src.read_text(encoding="utf-8")

    html_body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "toc", "sane_lists", "nl2br"],
    )

    full = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{src.stem}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="toc-note">Tip: open in your browser and press <strong>Cmd+P</strong> →
choose <strong>Save as PDF</strong> (or print). Sections are page-break aware.</div>
{html_body}
</body>
</html>
"""

    out = src.with_suffix(".html")
    out.write_text(full, encoding="utf-8")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/md_to_html.py <file.md>")
        sys.exit(1)
    out_path = convert(sys.argv[1])
    print(f"Wrote {out_path}")
