#!/usr/bin/env python3
"""Check the site before it is published.

    python scripts/check_site.py

A portfolio is one page that people reach from a CV or a LinkedIn post. There is
no second chance and no server log: a broken anchor, a missing asset or an icon
that does not resolve is just a page that looks unfinished to the one person who
mattered. So the things that can silently break are checked on every push.

What it checks:

  STRUCTURE  the document parses and every element that opens is closed
  ANCHORS    every href="#..." has a matching id
  ICONS      every <use href="#..."> resolves to a <symbol>
  ASSETS     every local file referenced exists on disk
  WIRING     the platform-layer buttons name repository rows that exist
  SOCIAL     the sharing card is declared with an absolute URL and exists
  PRIVACY    no company, client or tenant identifier from the portfolio denylist

Exit: 0 everything holds, 1 any problem.
"""

from __future__ import annotations

import re
import sys
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "index.html"
SITE_URL = "https://narfprox.github.io"

# Elements with no closing tag, HTML and SVG together: the page inlines its
# icons, so the SVG shapes have to be in this set or every one reads as unclosed.
VOID = {
    "area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
    "source", "track", "wbr",
    "path", "circle", "rect", "line", "polyline", "polygon", "ellipse", "use", "stop",
}


class Structure(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, int]] = []
        self.problems: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.problems.append(f"stray </{tag}>")
            return
        opened, line = self.stack.pop()
        if opened != tag:
            self.problems.append(f"<{opened}> opened at line {line} is closed by </{tag}>")


def check(html: str) -> list[str]:
    problems: list[str] = []

    parser = Structure()
    parser.feed(html)
    problems += parser.problems
    problems += [f"<{tag}> opened at line {line} is never closed"
                 for tag, line in parser.stack]

    ids = set(re.findall(r'\sid="([^"]+)"', html))
    problems += [f"href=#{anchor} has no matching id"
                 for anchor in sorted(set(re.findall(r'href="#([^"]+)"', html)))
                 if anchor not in ids]

    symbols = set(re.findall(r'<symbol id="([^"]+)"', html))
    problems += [f"<use #{used}> has no <symbol> to resolve to"
                 for used in sorted(set(re.findall(r'<use href="#([^"]+)"', html)))
                 if used not in symbols]

    local = re.findall(r'(?:src|href)="((?!https?:|#|data:|mailto:)[^"]+)"', html)
    problems += [f"referenced file does not exist: {ref}"
                 for ref in sorted(set(local))
                 if not (ROOT / ref).is_file()]

    rows = set(re.findall(r'data-repo="([^"]+)"', html))
    for group in re.findall(r'data-repos="([^"]+)"', html):
        problems += [f"a platform layer names '{name}', which is not a repository row"
                     for name in group.split() if name not in rows]

    # LinkedIn, Slack and Teams all ignore a relative og:image without saying so,
    # and the result is a share with no picture and no explanation.
    card = re.search(r'<meta property="og:image" content="([^"]+)"', html)
    if not card:
        problems.append("no og:image; a shared link would render as a bare text card")
    elif not card.group(1).startswith("http"):
        problems.append(f"og:image is relative ({card.group(1)}); it must be absolute")
    elif not (ROOT / card.group(1).removeprefix(SITE_URL + "/")).is_file():
        problems.append(f"og:image points at a file that is not in the repository: {card.group(1)}")

    return problems


def check_privacy(html: str) -> list[str]:
    """The company denylist from the portfolio scanner, if it is reachable.

    The full scanner is not used here: it forbids the author's own name and any
    GUID, and this page exists to carry a name. What still has to hold is that
    no company, client or tenant identifier appears.
    """
    scanner = ROOT.parent / "_tools" / "anon_scan.py"
    if not scanner.is_file():
        print("  (denylist scanner not reachable from here; privacy check skipped)")
        return []
    source = scanner.read_text(encoding="utf-8")
    block = source.split("DENY_WORDS = [", 1)[1].split("\n]", 1)[0]
    patterns = [p for p in re.findall(r'r"([^"]+)"', block) if "jean" not in p.lower()]
    problems = []
    for number, line in enumerate(html.splitlines(), start=1):
        problems += [f"line {number} matches the denylist pattern {pattern!r}"
                     for pattern in patterns if re.search(pattern, line, re.I)]
    return problems


def main() -> int:
    html = PAGE.read_text(encoding="utf-8")
    problems = check(html) + check_privacy(html)

    for problem in problems:
        print(f"  {problem}")

    ids = len(set(re.findall(r'\sid="([^"]+)"', html)))
    symbols = len(set(re.findall(r'<symbol id="([^"]+)"', html)))
    rows = len(set(re.findall(r'data-repo="([^"]+)"', html)))
    print(f"{ids} ids · {symbols} icons · {rows} repository rows · "
          f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
