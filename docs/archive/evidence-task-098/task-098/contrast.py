"""TASK-098 对比度自检：WCAG 2.x 相对亮度与对比度比。"""


def srgb_to_lin(c):
    c = c / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def lum(hexstr):
    h = hexstr.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * srgb_to_lin(r) + 0.7152 * srgb_to_lin(g) + 0.0722 * srgb_to_lin(b)


def ratio(fg, bg):
    a, b = lum(fg), lum(bg)
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


PAPER = "#f3e4c7"
PAPER_RAISED = "#f7ecd8"
CARD = "#ffffff"
INK = "#2a2419"
INK_MUTED = "#6b5d48"
SEAL = "#8c3a2b"
LINE = "#d9c9a8"

CASES = [
    ("ink.primary #2a2419 on paper.base #f3e4c7", INK, PAPER),
    ("ink.primary #2a2419 on paper.raised #f7ecd8", INK, PAPER_RAISED),
    ("ink.primary #2a2419 on paper.card #ffffff", INK, CARD),
    ("ink.muted #6b5d48 on paper.base #f3e4c7", INK_MUTED, PAPER),
    ("ink.muted #6b5d48 on paper.raised #f7ecd8", INK_MUTED, PAPER_RAISED),
    ("ink.muted #6b5d48 on paper.card #ffffff", INK_MUTED, CARD),
    ("white #ffffff on accent.seal #8c3a2b", "#ffffff", SEAL),
    ("accent.seal #8c3a2b on paper.base #f3e4c7", SEAL, PAPER),
    # 迁移前页面里直接落在老纸底上的 slate 文本
    ("[old] slate-500 #64748b on paper.base", "#64748b", PAPER),
    ("[old] slate-600 #475569 on paper.base", "#475569", PAPER),
    ("[old] slate-400 #94a3b8 on paper.base", "#94a3b8", PAPER),
    # 非文字：边框/线条
    ("ink.line #d9c9a8 on paper.base (非文字)", LINE, PAPER),
]

print(f"{'配对':<52} {'对比度':>8}  AA(4.5) AA-large(3.0)")
for name, fg, bg in CASES:
    r = ratio(fg, bg)
    print(f"{name:<52} {r:>7.2f}:1  {'PASS' if r >= 4.5 else 'FAIL':<7} {'PASS' if r >= 3.0 else 'FAIL'}")
