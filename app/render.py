"""Rendering: ANSI codes, sticker-kleuren, cube flat-view, layout helpers."""
import re

from app.protocol import FACE_TO_COLOR

# ===========================================================================
# ANSI codes
# ===========================================================================
ANSI_BG = {
    'W': '\033[107;30m',
    'Y': '\033[103;30m',
    'R': '\033[101;30m',
    'O': '\033[48;5;208;30m',
    'G': '\033[102;30m',
    'B': '\033[104;97m',
    '?': '\033[100;97m',
}
ANSI_RESET = '\033[0m'
CLEAR_HOME = '\033[2J\033[H'
HOME = '\033[H'
CLEAR_EOL = '\033[K'
CLEAR_EOS = '\033[J'
HIDE_CURSOR = '\033[?25l'
SHOW_CURSOR = '\033[?25h'
ANSI_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

EXIT_HINT = "  [exit modus: 8x U + 8x F]"


# ===========================================================================
# Helpers
# ===========================================================================
def visible_len(s):
    return len(ANSI_RE.sub('', s))


def _sticker(letter):
    return f"{ANSI_BG.get(letter, '')} {letter} {ANSI_RESET}"


def render_cube_lines(facelets):
    Uf = facelets[0:9]; Rf = facelets[9:18]; Ff = facelets[18:27]
    Df = facelets[27:36]; Lf = facelets[36:45]; Bf = facelets[45:54]

    def row(face, r):
        return "".join(_sticker(face[r * 3 + i]) for i in range(3))

    pad = " " * 9
    lines = []
    for r in range(3):
        lines.append(pad + row(Uf, r))
    lines.append("")
    for r in range(3):
        lines.append(row(Lf, r) + row(Ff, r) + row(Rf, r) + row(Bf, r))
    lines.append("")
    for r in range(3):
        lines.append(pad + row(Df, r))
    return lines


def side_by_side(left_lines, right_lines, gap=4, left_width=38):
    out = []
    n = max(len(left_lines), len(right_lines))
    for i in range(n):
        l = left_lines[i] if i < len(left_lines) else ""
        r = right_lines[i] if i < len(right_lines) else ""
        pad_count = max(0, left_width - visible_len(l))
        out.append(l + " " * pad_count + " " * gap + r)
    return "\n".join(out)


def title_bar(text):
    line = "═" * 38
    return [line, f"  {text}", line]


def format_time(seconds):
    if seconds is None:
        return "—"
    m = int(seconds // 60)
    s = seconds - m * 60
    if m:
        return f"{m}:{s:05.2f}"
    return f"{s:.2f}"


def colored_move(move, state='pending'):
    """Toon move met bg-kleur van de face. state: 'pending', 'done', 'next', 'error'."""
    face = move[0]
    color_letter = FACE_TO_COLOR[face]
    bg = ANSI_BG.get(color_letter, '')
    text = f"{move:<3}"
    if state == 'done':
        return f"\033[2m{bg} {text}{ANSI_RESET}"
    if state == 'next':
        return f"\033[1;4m{bg} {text}{ANSI_RESET}"
    if state == 'error':
        return f"\033[1;5m{bg} {text}{ANSI_RESET}"
    return f"{bg} {text}{ANSI_RESET}"
