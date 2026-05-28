"""Timer mode: fixed/free scramble + CFOP-detectie + solves-history."""
import random
import time
from datetime import datetime

from app import core
from app.core import (
    Mode, beep, detect_n_face, load_solves, save_solve, set_mode,
)
from app.render import (
    ANSI_RESET, EXIT_HINT,
    colored_move, format_time, render_cube_lines, side_by_side, title_bar,
)


# ===========================================================================
# Scramble generation
# ===========================================================================
SCRAMBLE_FACES = ['U', 'R', 'F', 'D', 'L', 'B']
SCRAMBLE_AXES = {'U': 'UD', 'D': 'UD', 'R': 'RL', 'L': 'RL', 'F': 'FB', 'B': 'FB'}
SCRAMBLE_SUFFIX = ['', "'", '2']


def generate_scramble(length=20):
    out = []
    while len(out) < length:
        f = random.choice(SCRAMBLE_FACES)
        if out and out[-1][0] == f:
            continue
        if len(out) >= 2 and SCRAMBLE_AXES[out[-1][0]] == SCRAMBLE_AXES[f] and SCRAMBLE_AXES[out[-2][0]] == SCRAMBLE_AXES[f]:
            continue
        out.append(f + random.choice(SCRAMBLE_SUFFIX))
    return out


def invert_move(move):
    face = move[0]
    rest = move[1:]
    if rest == '':
        return face + "'"
    if rest == "'":
        return face
    if rest == '2' or rest == "2'":
        return face + '2'
    return face


# ===========================================================================
# CFOP detectie (cross op witte (U) face)
# ===========================================================================
def is_cross_done(facelets):
    return (facelets[1] == 'W' and facelets[46] == 'B' and
            facelets[3] == 'W' and facelets[37] == 'O' and
            facelets[5] == 'W' and facelets[10] == 'R' and
            facelets[7] == 'W' and facelets[19] == 'G')


def is_f2l_done(facelets):
    if not all(facelets[i] == 'W' for i in range(9)):
        return False
    for offset, expected in [(9, 'R'), (18, 'G'), (36, 'O'), (45, 'B')]:
        for i in range(6):
            if facelets[offset + i] != expected:
                return False
    return True


def is_oll_done(facelets):
    return is_f2l_done(facelets) and all(facelets[i] == 'Y' for i in range(27, 36))


def is_solved(facelets):
    for offset in (0, 9, 18, 27, 36, 45):
        face = facelets[offset:offset + 9]
        if any(c != face[0] for c in face):
            return False
    return True


# ===========================================================================
# Timer submenu
# ===========================================================================
class TimerTypeMenu(Mode):
    options = [
        ("Fixed scramble (volg algoritme)", "fixed"),
        ("Free scramble (eindig met 4x U)", "free"),
        ("Solves bekijken",                 "browse"),
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
            if choice == 'browse':
                set_mode(SolvesListMode())
            else:
                set_mode(TimerMode(choice))
        elif move[0] == 'B':
            from app.core import MainMenu
            set_mode(MainMenu())

    def render(self, facelets):
        lines = title_bar("TIMER → SCRAMBLE TYPE") + [""]
        for i, (label, _) in enumerate(self.options):
            marker = "  > " if i == self.cursor else "    "
            highlight = "\033[1;36m" if i == self.cursor else ""
            reset = ANSI_RESET if i == self.cursor else ""
            lines.append(f"{marker}{highlight}{label}{reset}")
        lines.append("")
        lines.append("  [wit = scroll]  [groen = kies]  [blauw = terug]")
        lines.append("")
        lines.append(EXIT_HINT)
        return side_by_side(lines, render_cube_lines(facelets))


# ===========================================================================
# Timer mode
# ===========================================================================
class TimerMode(Mode):
    needs_tick = True

    DONE_OPTIONS = [
        ("Opnieuw", "again"),
        ("Details bekijken", "details"),
        ("Terug naar menu", "back"),
    ]

    def __init__(self, scramble_type):
        self.scramble_type = scramble_type
        if scramble_type == 'fixed':
            self.phase = 'await_solved'
            self.scramble = generate_scramble(20)
        else:
            self.phase = 'await_scramble'
            self.scramble = None
        self.scramble_idx = 0
        self.correction_stack = []
        self.partial_qt = 0
        self.correction_partial_qt = 0
        self.start_time = None
        self.move_count = 0
        self.milestones = {'cross': None, 'f2l': None, 'oll': None, 'pll': None}
        self.milestone_moves = {'cross': None, 'f2l': None, 'oll': None, 'pll': None}
        self.solved_at = None
        self.scrambled_facelets = None
        self.done_cursor = 0

    def enter(self):
        # Als cube al opgelost is bij entry, skip await_solved
        if self.phase == 'await_solved' and is_solved(core.last_facelets):
            self.phase = 'await_scramble'

    def process(self, state, facelets, faces, move):
        if self.phase == 'await_solved':
            if is_solved(facelets):
                self.phase = 'await_scramble'
        elif self.phase == 'await_scramble':
            if self.scramble_type == 'fixed':
                self._handle_fixed_scramble_move(move)
            else:
                if move and detect_n_face('U', 4):
                    self.phase = 'await_start'
            if self.phase == 'await_start':
                # Scramble net afgerond — snapshot van de scrambled state.
                self.scrambled_facelets = list(facelets)
        elif self.phase == 'await_start':
            if move:
                self.phase = 'solving'
                self.start_time = time.monotonic()
                self.move_count = 1
                self._check_milestones(facelets)
        elif self.phase == 'solving':
            if move:
                self.move_count += 1
                self._check_milestones(facelets)
                if is_solved(facelets):
                    elapsed = time.monotonic() - self.start_time
                    self.milestones['pll'] = elapsed
                    self.milestone_moves['pll'] = self.move_count
                    self.solved_at = elapsed
                    self.phase = 'done'
                    self._save_result()
        elif self.phase == 'done':
            if not move:
                return
            if move[0] == 'U':
                direction = -1 if "'" in move else 1
                self.done_cursor = (self.done_cursor + direction) % len(self.DONE_OPTIONS)
            elif move[0] == 'F':
                choice = self.DONE_OPTIONS[self.done_cursor][1]
                if choice == 'again':
                    set_mode(TimerMode(self.scramble_type))
                elif choice == 'details':
                    set_mode(SolveDetailMode(len(load_solves()) - 1))
                else:
                    from app.core import MainMenu
                    set_mode(MainMenu())

    @staticmethod
    def _qt(move):
        """Kwartslagen voor een move (mod 4)."""
        rest = move[1:]
        if rest == '':
            return 1
        if rest == "'":
            return 3  # = -1 mod 4
        if rest == '2' or rest == "2'":
            return 2
        return 0

    def _handle_fixed_scramble_move(self, move):
        if not move:
            return
        if self.correction_stack:
            expected = self.correction_stack[-1]
            if move[0] != expected[0]:
                self.correction_stack.append(invert_move(move))
                self.correction_partial_qt = 0
                beep()
                return
            self.correction_partial_qt = (self.correction_partial_qt + self._qt(move)) % 4
            if self.correction_partial_qt == self._qt(expected):
                self.correction_stack.pop()
                self.correction_partial_qt = 0
            return

        if self.scramble_idx >= len(self.scramble):
            self.phase = 'await_start'
            return
        expected = self.scramble[self.scramble_idx]
        if move[0] != expected[0]:
            self.correction_stack.append(invert_move(move))
            self.partial_qt = 0
            beep()
            return
        self.partial_qt = (self.partial_qt + self._qt(move)) % 4
        if self.partial_qt == self._qt(expected):
            self.scramble_idx += 1
            self.partial_qt = 0
            if self.scramble_idx >= len(self.scramble):
                self.phase = 'await_start'

    def _check_milestones(self, facelets):
        if self.start_time is None:
            return
        elapsed = time.monotonic() - self.start_time
        if self.milestones['cross'] is None and is_cross_done(facelets):
            self.milestones['cross'] = elapsed
            self.milestone_moves['cross'] = self.move_count
        if self.milestones['f2l'] is None and is_f2l_done(facelets):
            self.milestones['f2l'] = elapsed
            self.milestone_moves['f2l'] = self.move_count
        if self.milestones['oll'] is None and is_oll_done(facelets):
            self.milestones['oll'] = elapsed
            self.milestone_moves['oll'] = self.move_count

    def _save_result(self):
        record = {
            'timestamp': time.time(),
            'total': self.solved_at,
            'moves': self.move_count,
            'cross': self.milestones['cross'],
            'f2l': self.milestones['f2l'],
            'oll': self.milestones['oll'],
            'pll': self.milestones['pll'],
            'milestone_moves': dict(self.milestone_moves),
            'scramble_type': self.scramble_type,
            'scramble': self.scramble,
            'scrambled_facelets': self.scrambled_facelets,
        }
        save_solve(record)

    def render(self, facelets):
        if self.phase == 'await_solved':
            lines = self._render_await_solved()
        elif self.phase == 'await_scramble':
            lines = self._render_scramble()
        elif self.phase == 'await_start':
            lines = self._render_await_start()
        elif self.phase == 'solving':
            lines = self._render_solving()
        else:
            lines = self._render_done()
        return side_by_side(lines, render_cube_lines(facelets))

    def _render_await_solved(self):
        lines = title_bar("TIMER — FIXED SCRAMBLE") + [""]
        lines.append("  \033[1;33mLos eerst je cube op.\033[0m")
        lines.append("")
        lines.append("  De scramble start zodra de")
        lines.append("  cube volledig opgelost is —")
        lines.append("  zo geeft het algoritme elke")
        lines.append("  keer exact dezelfde stand.")
        lines.append("")
        lines.append("  Aankomende scramble:")
        per_line = 6
        moves = [colored_move(m, 'pending') for m in self.scramble]
        for i in range(0, len(moves), per_line):
            lines.append("  " + "".join(moves[i:i + per_line]))
        lines.append("")
        lines.append(EXIT_HINT)
        return lines

    def _render_scramble(self):
        if self.scramble_type == 'free':
            return title_bar("TIMER — FREE SCRAMBLE") + [
                "",
                "  Scramble je cube vrij.",
                "",
                "  Eindig met 4x U (witte zijde)",
                "  om door te gaan.",
                "",
                EXIT_HINT,
            ]
        lines = title_bar("TIMER — FIXED SCRAMBLE") + [""]
        moves = []
        for i, m in enumerate(self.scramble):
            if i < self.scramble_idx:
                state = 'done'
            elif i == self.scramble_idx and not self.correction_stack:
                state = 'next'
            else:
                state = 'pending'
            moves.append(colored_move(m, state))
        per_line = 6
        for i in range(0, len(moves), per_line):
            lines.append("  " + "".join(moves[i:i + per_line]))
        lines.append("")
        if self.correction_stack:
            lines.append("  \033[1;31m✗ FOUT — corrigeer met:\033[0m")
            lines.append("  " + colored_move(self.correction_stack[-1], 'error'))
            if self.correction_partial_qt:
                lines.append(f"  (partial: {self.correction_partial_qt * 90}°)")
        else:
            if self.scramble_idx < len(self.scramble):
                nxt = self.scramble[self.scramble_idx]
                extra = f"   (partial: {self.partial_qt * 90}°)" if self.partial_qt else ""
                lines.append(f"  Volgende: {colored_move(nxt, 'next')}{extra}")
            else:
                lines.append("  Klaar!")
        lines.append("")
        lines.append(f"  Voortgang: {self.scramble_idx}/{len(self.scramble)}")
        lines.append("")
        lines.append(EXIT_HINT)
        return lines

    def _render_await_start(self):
        return title_bar("TIMER — KLAAR") + [
            "",
            "  ✓ Scramble compleet.",
            "",
            "  \033[1;33mEerste zet = START\033[0m",
            "",
            EXIT_HINT,
        ]

    def _render_solving(self):
        elapsed = time.monotonic() - self.start_time
        lines = title_bar("TIMER — SOLVING") + [
            "",
            f"  \033[1;92m⏱  {format_time(elapsed)}\033[0m",
            "",
        ]
        for label, key in [("Cross", 'cross'), ("F2L  ", 'f2l'), ("OLL  ", 'oll'), ("PLL  ", 'pll')]:
            t = self.milestones[key]
            m = self.milestone_moves[key]
            if t is None:
                lines.append(f"  {label}  —")
            else:
                lines.append(f"  {label}  {format_time(t):>7}   {m}m")
        lines.append("")
        tps = self.move_count / elapsed if elapsed > 0 else 0
        lines.append(f"  Moves: {self.move_count}    TPS: {tps:.2f}")
        lines.append("")
        lines.append(EXIT_HINT)
        return lines

    def _render_done(self):
        history = load_solves()
        recent = list(history[-5:])
        all_times = [r['total'] for r in history if r.get('total')]
        pb = min(all_times) if all_times else self.solved_at
        is_pb = self.solved_at <= pb + 0.001

        title = "SOLVE COMPLETE — ⭐ PB!" if is_pb else "SOLVE COMPLETE"
        lines = title_bar(title) + [""]
        lines.append(f"  \033[1;92mTotaal: {format_time(self.solved_at)}\033[0m   {self.move_count} moves")
        lines.append("")
        for label, key in [("Cross", 'cross'), ("F2L  ", 'f2l'), ("OLL  ", 'oll'), ("PLL  ", 'pll')]:
            t = self.milestones[key]
            m = self.milestone_moves[key]
            if t is None:
                lines.append(f"  {label}  —")
            else:
                lines.append(f"  {label}  {format_time(t):>7}   {m}m")
        lines.append("")
        lines.append("  Laatste 5:")
        for r in reversed(recent):
            t = r.get('total')
            mark = " ⭐" if t and t <= pb + 0.001 else ""
            lines.append(f"    {format_time(t)}{mark}")
        if not recent:
            lines.append("    (nog geen)")
        lines.append("")
        for i, (label, _) in enumerate(self.DONE_OPTIONS):
            marker = "  > " if i == self.done_cursor else "    "
            highlight = "\033[1;36m" if i == self.done_cursor else ""
            reset = ANSI_RESET if i == self.done_cursor else ""
            lines.append(f"{marker}{highlight}{label}{reset}")
        lines.append("")
        lines.append("  [wit = scroll]  [groen = kies]")
        lines.append(EXIT_HINT)
        return lines


# ===========================================================================
# Solves browser
# ===========================================================================
PAGE_SIZE = 12


def _scramble_type_short(t):
    if t == 'fixed':
        return 'F'
    if t == 'free':
        return 'V'
    return '?'


def _format_solve_date(ts, fmt="%d-%m %H:%M"):
    if not ts:
        return "—"
    try:
        return datetime.fromtimestamp(ts).strftime(fmt)
    except Exception:
        return "—"


class SolvesListMode(Mode):
    def __init__(self):
        self.solves = load_solves()
        # Cursor = index in display-order (nieuwste eerst).
        self.cursor = 0

    def process(self, state, facelets, faces, move):
        if not move:
            return
        if not self.solves:
            if move[0] == 'B':
                from app.core import MainMenu
                set_mode(MainMenu())
            return
        if move[0] == 'U':
            direction = -1 if "'" in move else 1
            self.cursor = (self.cursor + direction) % len(self.solves)
        elif move[0] == 'F':
            # display-cursor naar originele index
            original_idx = len(self.solves) - 1 - self.cursor
            set_mode(SolveDetailMode(original_idx))
        elif move[0] == 'B':
            from app.core import MainMenu
            set_mode(MainMenu())

    def render(self, facelets):
        total = len(self.solves)
        lines = title_bar(f"SOLVES  ({total} totaal)") + [""]
        if not self.solves:
            lines.append("  (nog geen solves)")
            lines.append("")
            lines.append("  [blauw = terug]")
            lines.append(EXIT_HINT)
            return side_by_side(lines, render_cube_lines(facelets))

        all_times = [r['total'] for r in self.solves if r.get('total')]
        pb = min(all_times) if all_times else None

        page = self.cursor // PAGE_SIZE
        page_start = page * PAGE_SIZE
        page_end = min(page_start + PAGE_SIZE, total)
        pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

        for display_idx in range(page_start, page_end):
            original_idx = total - 1 - display_idx
            r = self.solves[original_idx]
            num = original_idx + 1
            date = _format_solve_date(r.get('timestamp'))
            t = r.get('total')
            t_str = format_time(t)
            typ = _scramble_type_short(r.get('scramble_type'))
            pb_mark = "*" if t and pb and t <= pb + 0.001 else " "
            label = f"#{num:>3}  {date}  {t_str:>7}s {typ} {pb_mark}"
            if display_idx == self.cursor:
                lines.append(f"  > \033[1;36m{label}\033[0m")
            else:
                lines.append(f"    {label}")

        # Vul lege regels zodat layout stabiel blijft
        for _ in range(PAGE_SIZE - (page_end - page_start)):
            lines.append("")

        lines.append("")
        lines.append(f"  [{self.cursor + 1}/{total}]   Pagina {page + 1}/{pages}")
        lines.append("")
        lines.append("  [wit = scroll]  [groen = open]")
        lines.append("  [blauw = hoofdmenu]  (* = PB)")
        lines.append(EXIT_HINT)
        return side_by_side(lines, render_cube_lines(facelets))


class SolveDetailMode(Mode):
    def __init__(self, original_idx):
        self.solves = load_solves()
        self.idx = max(0, min(original_idx, len(self.solves) - 1)) if self.solves else 0

    def process(self, state, facelets, faces, move):
        if not move:
            return
        if not self.solves:
            if move[0] in ('B', 'F'):
                set_mode(SolvesListMode())
            return
        if move[0] == 'U':
            # U = volgende (nieuwer), U' = vorige (ouder)
            direction = -1 if "'" in move else 1
            self.idx = (self.idx + direction) % len(self.solves)
        elif move[0] in ('B', 'F'):
            set_mode(SolvesListMode())

    def render(self, facelets):
        if not self.solves:
            lines = title_bar("SOLVE DETAIL") + [
                "",
                "  Geen solves opgeslagen.",
                "",
                "  [blauw = terug]",
            ]
            return side_by_side(lines, render_cube_lines(facelets))

        r = self.solves[self.idx]
        total = len(self.solves)
        num = self.idx + 1
        # Positie in display-volgorde (nieuwste eerst)
        display_pos = total - self.idx

        all_times = [s['total'] for s in self.solves if s.get('total')]
        pb = min(all_times) if all_times else None
        sorted_times = sorted(all_times)
        t = r.get('total')
        is_pb = bool(t and pb and t <= pb + 0.001)
        rank = sorted_times.index(t) + 1 if t in sorted_times else None

        scramble_type = r.get('scramble_type', '?')
        type_label = {
            'fixed': 'Fixed scramble (algoritme)',
            'free':  'Free scramble',
        }.get(scramble_type, scramble_type)

        moves_total = r.get('moves')
        tps_total = (moves_total / t) if (moves_total and t) else None

        lines = title_bar(f"SOLVE #{num}   ({display_pos}/{total})") + [""]
        lines.append(f"  Datum:  {_format_solve_date(r.get('timestamp'), '%Y-%m-%d %H:%M:%S')}")
        lines.append(f"  Type:   {type_label}")
        lines.append("")
        pb_txt = "  \033[1;33m⭐ PB\033[0m" if is_pb else ""
        lines.append(f"  \033[1;92mTotaal:  {format_time(t)}\033[0m{pb_txt}")
        if moves_total is not None:
            tps_str = f"{tps_total:.2f}" if tps_total else "—"
            lines.append(f"  Moves:   {moves_total}        TPS: {tps_str}")
        if rank is not None:
            lines.append(f"  Rang:    #{rank} van {len(sorted_times)}")
        lines.append("")

        # Splits met delta tijd en delta moves
        lines.append("  Fase    Tijd     Δt      m   Δm   TPS")
        prev_t = 0.0
        prev_m = 0
        for label, key in [("Cross", 'cross'), ("F2L  ", 'f2l'), ("OLL  ", 'oll'), ("PLL  ", 'pll')]:
            phase_t = r.get(key)
            phase_m = (r.get(key + '_moves') if r.get(key + '_moves') is not None
                       else (r.get('_milestone_moves', {}) or {}).get(key))
            # nieuw formaat: 'milestone_moves' niet opgeslagen — pak uit losse velden
            if phase_m is None:
                # fallback voor nieuwe records die per-fase moves apart hebben
                phase_m = _get_phase_moves(r, key)
            if phase_t is None:
                lines.append(f"  {label}   —")
                continue
            delta_t = phase_t - prev_t
            delta_m = (phase_m - prev_m) if phase_m is not None else None
            tps_phase = (delta_m / delta_t) if (delta_m and delta_t > 0) else None
            tps_str = f"{tps_phase:.2f}" if tps_phase else "  — "
            m_str = f"{phase_m:>3}" if phase_m is not None else "  —"
            dm_str = f"{delta_m:>3}" if delta_m is not None else "  —"
            lines.append(f"  {label} {format_time(phase_t):>6} {delta_t:>5.2f} {m_str} {dm_str}  {tps_str}")
            prev_t = phase_t
            if phase_m is not None:
                prev_m = phase_m
        lines.append("")

        scramble = r.get('scramble')
        if scramble:
            lines.append("  Scramble:")
            per_line = 6
            moves = [colored_move(m, 'pending') for m in scramble]
            for i in range(0, len(moves), per_line):
                lines.append("  " + "".join(moves[i:i + per_line]))
        else:
            lines.append("  Scramble: (free)")
        lines.append("")
        lines.append("  [U' = vorige]  [U = volgende]")
        lines.append("  [blauw / groen = terug]")
        lines.append(EXIT_HINT)

        scrambled = r.get('scrambled_facelets')
        if scrambled and len(scrambled) == 54:
            right_lines = ["  \033[1;36mScrambled state:\033[0m", ""] + render_cube_lines(scrambled)
        else:
            right_lines = ["  \033[2m(geen scrambled-snapshot)\033[0m", ""] + render_cube_lines(facelets)
        return side_by_side(lines, right_lines)


def _get_phase_moves(record, key):
    """Robuust ophalen van per-fase move count uit oude/nieuwe record-formaten."""
    # Huidig formaat: top-level keys 'cross_moves', 'f2l_moves', etc. zijn er niet,
    # maar 'milestone_moves' ook niet opgeslagen. We bewaren ze nu separaat.
    direct = record.get(key + '_moves')
    if direct is not None:
        return direct
    mm = record.get('milestone_moves')
    if isinstance(mm, dict):
        return mm.get(key)
    return None
