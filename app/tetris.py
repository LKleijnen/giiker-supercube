"""Tetris mode: cube-bestuurde tetris met 7-bag piece-spawn."""
import random
import time

from app.core import Mode, set_mode
from app.render import ANSI_RESET, EXIT_HINT


# ===========================================================================
# Piece definitions
# ===========================================================================
# Coords per rotatie zijn (col, row) binnen een 4x4 (I/O) of 3x3 bounding box.
TETROMINOES = {
    'I': {
        'color': 'C',
        'rotations': [
            [(0, 1), (1, 1), (2, 1), (3, 1)],
            [(2, 0), (2, 1), (2, 2), (2, 3)],
            [(0, 2), (1, 2), (2, 2), (3, 2)],
            [(1, 0), (1, 1), (1, 2), (1, 3)],
        ],
    },
    'O': {
        'color': 'Y',
        'rotations': [
            [(1, 0), (2, 0), (1, 1), (2, 1)],
        ] * 4,
    },
    'T': {
        'color': 'P',
        'rotations': [
            [(1, 0), (0, 1), (1, 1), (2, 1)],
            [(1, 0), (1, 1), (2, 1), (1, 2)],
            [(0, 1), (1, 1), (2, 1), (1, 2)],
            [(1, 0), (0, 1), (1, 1), (1, 2)],
        ],
    },
    'S': {
        'color': 'G',
        'rotations': [
            [(1, 0), (2, 0), (0, 1), (1, 1)],
            [(1, 0), (1, 1), (2, 1), (2, 2)],
            [(1, 1), (2, 1), (0, 2), (1, 2)],
            [(0, 0), (0, 1), (1, 1), (1, 2)],
        ],
    },
    'Z': {
        'color': 'R',
        'rotations': [
            [(0, 0), (1, 0), (1, 1), (2, 1)],
            [(2, 0), (1, 1), (2, 1), (1, 2)],
            [(0, 1), (1, 1), (1, 2), (2, 2)],
            [(1, 0), (0, 1), (1, 1), (0, 2)],
        ],
    },
    'J': {
        'color': 'B',
        'rotations': [
            [(0, 0), (0, 1), (1, 1), (2, 1)],
            [(1, 0), (2, 0), (1, 1), (1, 2)],
            [(0, 1), (1, 1), (2, 1), (2, 2)],
            [(1, 0), (1, 1), (0, 2), (1, 2)],
        ],
    },
    'L': {
        'color': 'O',
        'rotations': [
            [(2, 0), (0, 1), (1, 1), (2, 1)],
            [(1, 0), (1, 1), (1, 2), (2, 2)],
            [(0, 1), (1, 1), (2, 1), (0, 2)],
            [(0, 0), (1, 0), (1, 1), (1, 2)],
        ],
    },
}

# ANSI achtergrondkleur per kleurcode (los van cube-stickers — eigen palette).
PIECE_BG = {
    'C': '\033[106;30m',         # cyan       (I)
    'Y': '\033[103;30m',         # geel       (O)
    'P': '\033[105;30m',         # paars      (T)
    'G': '\033[102;30m',         # groen      (S)
    'R': '\033[101;30m',         # rood       (Z)
    'B': '\033[104;97m',         # blauw      (J)
    'O': '\033[48;5;208;30m',    # oranje     (L)
}


# ===========================================================================
# Helpers
# ===========================================================================
BOARD_W = 10
BOARD_H = 20


class Piece:
    __slots__ = ('kind', 'x', 'y', 'rotation')

    def __init__(self, kind, x, y, rotation=0):
        self.kind = kind
        self.x = x
        self.y = y
        self.rotation = rotation

    def cells(self, rotation=None, dx=0, dy=0):
        rot = self.rotation if rotation is None else rotation
        shape = TETROMINOES[self.kind]['rotations'][rot]
        return [(self.x + cx + dx, self.y + cy + dy) for cx, cy in shape]

    @property
    def color(self):
        return TETROMINOES[self.kind]['color']


def _collides(board, cells):
    for x, y in cells:
        if x < 0 or x >= BOARD_W or y >= BOARD_H:
            return True
        if y >= 0 and board[y][x]:
            return True
    return False


# Standaard NES Tetris score per #lines cleared, vermenigvuldigd met level.
LINE_SCORES = {1: 40, 2: 100, 3: 300, 4: 1200}


def _drop_interval(level):
    return max(0.05, 0.8 * (0.85 ** (level - 1)))


# ===========================================================================
# Tetris
# ===========================================================================
class TetrisMode(Mode):
    needs_tick = True

    DONE_OPTIONS = [
        ("Opnieuw", "again"),
        ("Terug naar menu", "back"),
    ]

    def __init__(self):
        self.board = [[None] * BOARD_W for _ in range(BOARD_H)]
        self.bag = []
        self.next_kind = self._draw_kind()
        self.piece = None
        self.score = 0
        self.lines = 0
        self.level = 1
        self.game_over = False
        self.done_cursor = 0
        self.last_drop = time.monotonic()
        self._spawn()

    # ---- piece-bag --------------------------------------------------------
    def _draw_kind(self):
        if not self.bag:
            self.bag = list(TETROMINOES.keys())
            random.shuffle(self.bag)
        return self.bag.pop()

    def _spawn(self):
        kind = self.next_kind
        self.next_kind = self._draw_kind()
        spawn_x = 3
        spawn_y = -1 if kind == 'I' else 0
        self.piece = Piece(kind, spawn_x, spawn_y)
        if _collides(self.board, self.piece.cells()):
            self.game_over = True

    # ---- input ------------------------------------------------------------
    def process(self, state, facelets, faces, move):
        if not move:
            return
        if self.game_over:
            if move[0] == 'U':
                direction = -1 if "'" in move else 1
                self.done_cursor = (self.done_cursor + direction) % len(self.DONE_OPTIONS)
            elif move[0] == 'F':
                choice = self.DONE_OPTIONS[self.done_cursor][1]
                if choice == 'again':
                    set_mode(TetrisMode())
                else:
                    from app.games import GamesMenu
                    set_mode(GamesMenu())
            return

        face = move[0]
        if face == 'L':
            self._try_move(-1, 0)
        elif face == 'R':
            self._try_move(1, 0)
        elif face == 'D':
            # soft drop: één rij omlaag, en kleine score-bonus
            if self._try_move(0, 1):
                self.score += 1
        elif face == 'B':
            self._hard_drop()
        elif face == 'U':
            direction = -1 if "'" in move else 1
            self._try_rotate(direction)

    def _try_move(self, dx, dy):
        if _collides(self.board, self.piece.cells(dx=dx, dy=dy)):
            return False
        self.piece.x += dx
        self.piece.y += dy
        return True

    def _try_rotate(self, direction):
        new_rot = (self.piece.rotation + direction) % 4
        # Eenvoudige wall-kicks: probeer offset 0, ±1, ±2 in x-richting.
        for kick in (0, -1, 1, -2, 2):
            if not _collides(self.board, self.piece.cells(rotation=new_rot, dx=kick)):
                self.piece.rotation = new_rot
                self.piece.x += kick
                return True
        return False

    def _hard_drop(self):
        dropped = 0
        while self._try_move(0, 1):
            dropped += 1
        self.score += 2 * dropped
        self._lock_piece()

    # ---- tick / gravity ---------------------------------------------------
    def tick(self, facelets):
        if self.game_over:
            return
        now = time.monotonic()
        if now - self.last_drop < _drop_interval(self.level):
            return
        self.last_drop = now
        if not self._try_move(0, 1):
            self._lock_piece()

    def _lock_piece(self):
        color = self.piece.color
        for x, y in self.piece.cells():
            if 0 <= y < BOARD_H and 0 <= x < BOARD_W:
                self.board[y][x] = color
        self._clear_lines()
        self.last_drop = time.monotonic()
        self._spawn()

    def _clear_lines(self):
        new_board = [row for row in self.board if any(c is None for c in row)]
        cleared = BOARD_H - len(new_board)
        if cleared == 0:
            return
        for _ in range(cleared):
            new_board.insert(0, [None] * BOARD_W)
        self.board = new_board
        self.lines += cleared
        self.score += LINE_SCORES.get(cleared, 0) * self.level
        self.level = 1 + self.lines // 10

    # ---- render -----------------------------------------------------------
    def _ghost_y(self):
        dy = 0
        while not _collides(self.board, self.piece.cells(dy=dy + 1)):
            dy += 1
        return dy

    def render(self, facelets):
        lines = []
        title = f"TETRIS  —  score: \033[1;92m{self.score}\033[0m"
        if self.game_over:
            title += "    \033[1;31m[ GAME OVER ]\033[0m"
        lines.append(title)
        lines.append("  L=links  R=rechts  U=rot  D=soft  B=hard")
        lines.append("")

        piece_cells = set() if self.game_over else set(self.piece.cells())
        ghost_cells = set()
        if not self.game_over:
            ghost_dy = self._ghost_y()
            if ghost_dy > 0:
                ghost_cells = set(self.piece.cells(dy=ghost_dy)) - piece_cells

        piece_color = self.piece.color if not self.game_over else None

        top = "  ┌" + "─" * (BOARD_W * 2) + "┐"
        bot = "  └" + "─" * (BOARD_W * 2) + "┘"
        lines.append(top)
        for y in range(BOARD_H):
            row = "  │"
            for x in range(BOARD_W):
                cell = (x, y)
                board_color = self.board[y][x]
                if board_color:
                    bg = PIECE_BG.get(board_color, '')
                    row += f"{bg}  {ANSI_RESET}"
                elif cell in piece_cells:
                    bg = PIECE_BG.get(piece_color, '')
                    row += f"{bg}  {ANSI_RESET}"
                elif cell in ghost_cells:
                    row += "\033[2;37m░░\033[0m"
                else:
                    bg = "\033[48;5;236m" if (x + y) % 2 == 0 else "\033[48;5;238m"
                    row += f"{bg}  {ANSI_RESET}"
            row += "│"
            lines.append(row)
        lines.append(bot)
        lines.append("")
        lines.append(f"  Level: {self.level}    Lines: {self.lines}")
        lines.append("")
        lines += self._next_preview()
        lines.append("")
        if self.game_over:
            for i, (label, _) in enumerate(self.DONE_OPTIONS):
                marker = "  > " if i == self.done_cursor else "    "
                highlight = "\033[1;36m" if i == self.done_cursor else ""
                reset = ANSI_RESET if i == self.done_cursor else ""
                lines.append(f"{marker}{highlight}{label}{reset}")
            lines.append("")
            lines.append("  [wit = scroll]  [groen = kies]")
        lines.append(EXIT_HINT)
        return "\n".join(lines)

    def _next_preview(self):
        kind = self.next_kind
        color = TETROMINOES[kind]['color']
        bg = PIECE_BG.get(color, '')
        cells = set(TETROMINOES[kind]['rotations'][0])
        rows = ["  Next:"]
        for cy in range(2):
            row = "    "
            for cx in range(4):
                if (cx, cy) in cells:
                    row += f"{bg}  {ANSI_RESET}"
                else:
                    row += "  "
            rows.append(row)
        return rows
