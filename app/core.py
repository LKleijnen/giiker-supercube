"""Mode-framework, globale state, gestures, solves-history en hoofdmenu."""
import json
from collections import deque
from pathlib import Path

from app.render import (
    ANSI_RESET, CLEAR_EOS, HOME,
    render_cube_lines, side_by_side, title_bar,
)

# ===========================================================================
# Module-level state (door cube.py geüpdatet vanuit BLE handler)
# ===========================================================================
current_mode = None
last_facelets = ['?'] * 54
pending_beep = False
move_history = deque(maxlen=64)


# ===========================================================================
# Solves history
# ===========================================================================
SOLVES_FILE = Path(__file__).resolve().parent.parent / 'solves.json'


def load_solves():
    if SOLVES_FILE.exists():
        try:
            return json.loads(SOLVES_FILE.read_text(encoding='utf-8'))
        except Exception:
            return []
    return []


def save_solve(record):
    solves = load_solves()
    solves.append(record)
    SOLVES_FILE.write_text(json.dumps(solves, indent=2), encoding='utf-8')


# ===========================================================================
# Move history + gestures
# ===========================================================================
def reset_history():
    move_history.clear()


def detect_exit_gesture():
    if len(move_history) < 16:
        return False
    last16 = list(move_history)[-16:]
    return (all(m[0] == 'U' for m in last16[:8]) and
            all(m[0] == 'F' for m in last16[8:]))


def detect_n_face(face, n):
    if len(move_history) < n:
        return False
    return all(m[0] == face for m in list(move_history)[-n:])


# ===========================================================================
# Mode framework
# ===========================================================================
def beep():
    global pending_beep
    pending_beep = True


def set_mode(mode):
    global current_mode
    current_mode = mode
    reset_history()
    if hasattr(mode, 'enter'):
        mode.enter()
    render_now()


def render_now():
    if current_mode is None:
        return
    try:
        frame = current_mode.render(last_facelets)
    except Exception as e:
        frame = f"Render error: {e}"
    # Clear-to-end-of-line per regel zodat smallere frames residu wissen
    frame = frame.replace('\n', '\033[K\n') + '\033[K'
    # Top-margin van 2 regels zodat het frame niet tegen de bovenrand drukt
    print(HOME + '\033[K\n\033[K\n' + frame + CLEAR_EOS, end='', flush=True)
    global pending_beep
    if pending_beep:
        print('\a', end='', flush=True)
        pending_beep = False


class Mode:
    needs_tick = False
    def process(self, state, facelets, faces, move): pass
    def tick(self, facelets): pass
    def render(self, facelets): return ""


# ===========================================================================
# Hoofdmenu
# ===========================================================================
class MainMenu(Mode):
    options = [
        ("Timer mode", "timer"),
        ("Games mode", "games"),
    ]

    def __init__(self):
        self.cursor = 0

    def process(self, state, facelets, faces, move):
        if not move:
            return
        if move[0] == 'U':
            direction = -1 if "'" in move else 1
            self.cursor = (self.cursor + direction) % len(self.options)
        elif move[0] == 'F':
            choice = self.options[self.cursor][1]
            if choice == 'timer':
                from app.timer import TimerTypeMenu
                set_mode(TimerTypeMenu())
            elif choice == 'games':
                from app.games import GamesMenu
                set_mode(GamesMenu())

    def render(self, facelets):
        lines = title_bar("HOOFDMENU") + [""]
        for i, (label, _) in enumerate(self.options):
            marker = "  > " if i == self.cursor else "    "
            highlight = "\033[1;36m" if i == self.cursor else ""
            reset = ANSI_RESET if i == self.cursor else ""
            lines.append(f"{marker}{highlight}{label}{reset}")
        lines.append("")
        lines.append("  [witte face = scroll]")
        lines.append("  [groene face = bevestig]")
        return side_by_side(lines, render_cube_lines(facelets))
