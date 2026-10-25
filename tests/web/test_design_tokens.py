import re
from pathlib import Path

CSS = Path(__file__).resolve().parents[2] / "src" / "piscinow" / "static" / "css" / "app-ui.css"


def _tokens(block: str) -> dict:
    return dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", block))


def _light_and_dark():
    css = CSS.read_text(encoding="utf-8")
    dark_start = css.index("prefers-color-scheme: dark")
    dark_block = css[dark_start : css.index("}", css.index("}", dark_start) + 1) + 1]
    root_block = css[: dark_start]
    light = _tokens(root_block)
    dark = {**light, **_tokens(dark_block)}
    return light, dark


def _luminance(hex_color: str) -> float:
    channels = [int(hex_color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
    lin = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _ratio(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


# (foreground token, background token): every text/background pair the interface uses.
PAIRS = [
    ("ink", "bg"), ("ink", "surface"), ("muted", "surface"), ("muted", "bg"),
    ("link", "surface"), ("on-primary", "primary"),
    ("badge-text", "badge-bg"), ("badge-green-text", "badge-green-bg"), ("badge-amber-text", "badge-amber-bg"),
    ("nav-active-text", "nav-active-bg"), ("nav-text", "surface"),
    ("danger", "surface"),
]


def test_all_text_color_pairs_meet_wcag_aa_in_light_theme():
    light, _ = _light_and_dark()

    failing = {p: round(_ratio(light[p[0]], light[p[1]]), 2) for p in PAIRS if _ratio(light[p[0]], light[p[1]]) < 4.5}

    assert failing == {}


def test_all_text_color_pairs_meet_wcag_aa_in_dark_theme():
    _, dark = _light_and_dark()

    failing = {p: round(_ratio(dark[p[0]], dark[p[1]]), 2) for p in PAIRS if _ratio(dark[p[0]], dark[p[1]]) < 4.5}

    assert failing == {}


def test_manual_dark_theme_uses_exactly_the_same_values_as_the_system_dark_theme():
    css = CSS.read_text(encoding="utf-8")
    manual = _tokens(css[css.index(':root[data-theme="dark"]') :])
    _, dark = _light_and_dark()
    system_dark_only = {k: v for k, v in dark.items() if k in manual or k in _tokens(css[css.index("prefers-color-scheme: dark") : css.index(':root[data-theme="dark"]')])}

    assert manual, "no manual dark theme declared"
    for token, value in manual.items():
        assert dark[token] == value, token
