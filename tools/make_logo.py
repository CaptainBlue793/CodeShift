"""Generate the CodeShift logo as PNG and SVG from one geometry definition.

The mark is two chevrons pointing right — a pink one for the source language
and a cyan one for the target — reading as both code brackets and forward
motion, which is what the name says the tool does.

The palette is sampled from the Memex logo so the two projects read as a set:
the same vivid flat-icon language, heavy black keylines, transparent
background. The heavy keyline is what makes it survive on GitHub's dark theme,
where a thin mark would disappear.

An earlier draft put an outlined arrow between an opposed `<` and `>`. It was
dropped: the arrow had to live in the narrow lens the two brackets leave, and
at that size a centred stroke ate most of the interior and the round join
blunted the tip. Two chevrons say the same thing with one shape fewer.

Run:  python tools/make_logo.py   (needs Pillow; a dev tool, not a runtime
dependency, so it is deliberately absent from requirements.txt)
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

# --- palette (sampled from Memex's brain.png, so the marks are a set) ---
PINK = (0xFF, 0x76, 0xB4, 0xFF)
CYAN = (0x66, 0xF1, 0xFF, 0xFF)
BLACK = (0x00, 0x00, 0x00, 0xFF)

SIZE = 512          # final PNG edge, matching Memex's 512x512
SS = 4              # supersample factor; downsampled at the end for clean edges

STROKE = 56         # chevron thickness
OUTLINE = 14        # black keyline
HALF = 138          # half-height of a chevron
APEX = 106          # how far its point reaches past its back

#: Where each chevron's back sits. The gap is the whole design decision: closer
#: and the pink one is swallowed by the cyan one's keyline, wider and they stop
#: reading as a single mark.
BACKS = ((122, PINK), (284, CYAN))
CY = 256


def _chevron_points(x: int) -> list[tuple[int, int]]:
    return [(x, CY - HALF), (x + APEX, CY), (x, CY + HALF)]


def _stroke(draw: ImageDraw.ImageDraw, pts, color, width: int) -> None:
    """A polyline with round joins and caps, at supersampled scale."""
    scaled = [(x * SS, y * SS) for x, y in pts]
    draw.line(scaled, fill=color, width=width * SS, joint="curve")
    r = width * SS / 2
    for x, y in scaled:                       # PIL has no round cap of its own
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)


def render_png(path: Path) -> None:
    img = Image.new("RGBA", (SIZE * SS, SIZE * SS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for x, color in BACKS:
        pts = _chevron_points(x)
        _stroke(draw, pts, BLACK, STROKE + 2 * OUTLINE)   # keyline first...
        _stroke(draw, pts, color, STROKE)                 # ...colour inset on top
    img.resize((SIZE, SIZE), Image.LANCZOS).save(path)


def render_svg(path: Path) -> None:
    def hex_of(c) -> str:
        return "#%02X%02X%02X" % c[:3]

    common = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    body = ""
    for x, color in BACKS:
        pts = " ".join(f"{px},{py}" for px, py in _chevron_points(x))
        body += (
            f'  <polyline points="{pts}" {common} '
            f'stroke="{hex_of(BLACK)}" stroke-width="{STROKE + 2 * OUTLINE}"/>\n'
            f'  <polyline points="{pts}" {common} '
            f'stroke="{hex_of(color)}" stroke-width="{STROKE}"/>\n'
        )

    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SIZE} {SIZE}" '
        f'width="{SIZE}" height="{SIZE}" role="img" aria-label="CodeShift logo">\n'
        f"  <title>CodeShift</title>\n{body}</svg>\n",
        encoding="utf-8",
    )


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "images"
    out.mkdir(exist_ok=True)
    render_png(out / "codeshift.png")
    render_svg(out / "codeshift.svg")
    print(f"wrote {out / 'codeshift.png'}")
    print(f"wrote {out / 'codeshift.svg'}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    main()
