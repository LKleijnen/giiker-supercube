"""Games-submenu: kies een spel om via de cube te spelen."""
from app.core import Mode, set_mode
from app.render import (
    ANSI_RESET, EXIT_HINT,
    render_cube_lines, side_by_side, title_bar,
)


class GamesMenu(Mode):
    options = [
        ("Snake",  "snake"),
        ("Tetris", "tetris"),
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
            if choice == 'snake':
                from app.snake import SnakeSizeMenu
                set_mode(SnakeSizeMenu())
            elif choice == 'tetris':
                from app.tetris import TetrisMode
                set_mode(TetrisMode())
        elif move[0] == 'B':
            from app.core import MainMenu
            set_mode(MainMenu())

    def render(self, facelets):
        lines = title_bar("GAMES") + [""]
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
