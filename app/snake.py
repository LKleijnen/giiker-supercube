"""Snake mode: cube-bestuurde snake met instelbare grootte en items."""
import random
import time
from collections import deque

from app.core import Mode, set_mode
from app.render import (
    ANSI_RESET, EXIT_HINT,
    render_cube_lines, side_by_side, title_bar,
)


class SnakeSizeMenu(Mode):
    options = [
        ("Klein   (15 x 10)", (15, 10)),
        ("Normaal (25 x 15)", (25, 15)),
        ("Groot   (40 x 20)", (40, 20)),
    ]

    def __init__(self):
        self.cursor = 1

    def process(self, state, facelets, faces, move):
        if not move:
            return
        if move[0] == 'U':
            direction = -1 if "'" in move else 1
            self.cursor = (self.cursor + direction) % len(self.options)
        elif move[0] == 'F':
            set_mode(SnakeItemMenu(self.options[self.cursor][1]))
        elif move[0] == 'B':
            from app.games import GamesMenu
            set_mode(GamesMenu())

    def render(self, facelets):
        lines = title_bar("SNAKE → SPEELVELD") + [""]
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


class SnakeItemMenu(Mode):
    options = [
        ("1 item", 1),
        ("2 items", 2),
        ("5 items", 5),
    ]

    def __init__(self, size):
        self.size = size
        self.cursor = 0

    def process(self, state, facelets, faces, move):
        if not move:
            return
        if move[0] == 'U':
            direction = -1 if "'" in move else 1
            self.cursor = (self.cursor + direction) % len(self.options)
        elif move[0] == 'F':
            set_mode(SnakeMode(self.size, self.options[self.cursor][1]))
        elif move[0] == 'B':
            set_mode(SnakeSizeMenu())

    def render(self, facelets):
        lines = title_bar(f"SNAKE → ITEMS  ({self.size[0]}x{self.size[1]})") + [""]
        for i, (label, _) in enumerate(self.options):
            marker = "  > " if i == self.cursor else "    "
            highlight = "\033[1;36m" if i == self.cursor else ""
            reset = ANSI_RESET if i == self.cursor else ""
            lines.append(f"{marker}{highlight}{label}{reset}")
        lines.append("")
        lines.append("  [wit = scroll]  [groen = start]  [blauw = terug]")
        lines.append("")
        lines.append(EXIT_HINT)
        return side_by_side(lines, render_cube_lines(facelets))


class SnakeMode(Mode):
    needs_tick = True
    TICK_RATE = 0.15

    DIR_MAP = {
        'U': (0, -1),  # wit  = omhoog
        'D': (0,  1),  # geel = omlaag
        'L': (-1, 0),  # oranje = links
        'R': ( 1, 0),  # rood = rechts
    }

    DONE_OPTIONS = [
        ("Opnieuw", "again"),
        ("Terug naar menu", "back"),
    ]

    def __init__(self, size, n_items):
        self.width, self.height = size
        self.n_items = n_items
        self.snake = deque()
        cx, cy = self.width // 2, self.height // 2
        for i in range(4):
            self.snake.append((cx - i, cy))
        self.direction = (1, 0)
        self.pending_direction = (1, 0)
        self.items = set()
        self._spawn_items()
        self.score = 0
        self.last_tick = time.monotonic()
        self.game_over = False
        self.done_cursor = 0

    def _spawn_items(self):
        tries = 0
        while len(self.items) < self.n_items and tries < 500:
            x = random.randint(0, self.width - 1)
            y = random.randint(0, self.height - 1)
            tries += 1
            if (x, y) in self.snake or (x, y) in self.items:
                continue
            self.items.add((x, y))

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
                    set_mode(SnakeMode((self.width, self.height), self.n_items))
                else:
                    from app.games import GamesMenu
                    set_mode(GamesMenu())
            return
        face = move[0]
        if face in self.DIR_MAP:
            new_dir = self.DIR_MAP[face]
            if (new_dir[0] + self.direction[0], new_dir[1] + self.direction[1]) != (0, 0):
                self.pending_direction = new_dir

    def tick(self, facelets):
        if self.game_over:
            return
        now = time.monotonic()
        if now - self.last_tick < self.TICK_RATE:
            return
        self.last_tick = now
        self.direction = self.pending_direction
        head = self.snake[0]
        nh = (head[0] + self.direction[0], head[1] + self.direction[1])
        if not (0 <= nh[0] < self.width and 0 <= nh[1] < self.height):
            self.game_over = True
            return
        if nh in self.snake and nh != self.snake[-1]:
            self.game_over = True
            return
        self.snake.appendleft(nh)
        if nh in self.items:
            self.items.remove(nh)
            self.score += 1
            self._spawn_items()
        else:
            self.snake.pop()

    def render(self, facelets):
        lines = []
        title = f"SNAKE  —  score: \033[1;92m{self.score}\033[0m"
        if self.game_over:
            title += "    \033[1;31m[ GAME OVER ]\033[0m"
        lines.append(title)
        lines.append("  Wit=op  Geel=neer  Oranje=links  Rood=rechts")
        lines.append("")
        snake_set = set(self.snake)
        head = self.snake[0] if self.snake else None
        top = "  ┌" + "─" * (self.width * 2) + "┐"
        bot = "  └" + "─" * (self.width * 2) + "┘"
        lines.append(top)
        for y in range(self.height):
            row = "  │"
            for x in range(self.width):
                cell = (x, y)
                bg = "\033[48;5;236m" if (x + y) % 2 == 0 else "\033[48;5;238m"
                if cell == head:
                    row += f"{bg}\033[1;92m▣ \033[0m"
                elif cell in snake_set:
                    row += f"{bg}\033[1;32m■ \033[0m"
                elif cell in self.items:
                    row += f"{bg}\033[1;91m◆ \033[0m"
                else:
                    row += f"{bg}  \033[0m"
            row += "│"
            lines.append(row)
        lines.append(bot)
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
