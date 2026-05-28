"""Entry point: verbindt met de Giiker cube en draait de mode-loop."""
import asyncio
import os
import sys

from bleak import BleakClient

from app import core
from app.core import MainMenu, detect_exit_gesture, move_history, render_now, set_mode
from app.protocol import (
    CUBE_MAC, STATE_CHAR_UUID,
    build_facelets, decrypt, faces_2d, is_valid_state, parse_state,
)
from app.render import CLEAR_HOME, HIDE_CURSOR, SHOW_CURSOR


async def main():
    if os.name == 'nt':
        os.system('')  # activeer ANSI in Windows terminal
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except Exception:
            pass

    print(CLEAR_HOME + HIDE_CURSOR, end='', flush=True)
    set_mode(MainMenu())

    print(f"Verbinden met cube {CUBE_MAC}...", flush=True)
    try:
        async with BleakClient(CUBE_MAC) as client:
            def handle(_sender, raw):
                data = decrypt(bytes(raw))
                state = parse_state(data)
                if not is_valid_state(state):
                    return
                facelets = build_facelets(state)
                core.last_facelets = facelets
                move = state['last_move']
                if move:
                    move_history.append(move)
                # Exit-gesture werkt overal behalve in MainMenu zelf
                if not isinstance(core.current_mode, MainMenu) and detect_exit_gesture():
                    set_mode(MainMenu())
                    return
                core.current_mode.process(state, facelets, faces_2d(facelets), move)
                render_now()

            try:
                initial = await client.read_gatt_char(STATE_CHAR_UUID)
                data = decrypt(bytes(initial))
                state = parse_state(data)
                if is_valid_state(state):
                    core.last_facelets = build_facelets(state)
                    render_now()
            except Exception:
                pass

            await client.start_notify(STATE_CHAR_UUID, handle)

            try:
                while True:
                    await asyncio.sleep(0.05)
                    if core.current_mode and core.current_mode.needs_tick:
                        core.current_mode.tick(core.last_facelets)
                        render_now()
            except (KeyboardInterrupt, asyncio.CancelledError):
                pass
            finally:
                try:
                    await client.stop_notify(STATE_CHAR_UUID)
                except Exception:
                    pass
    finally:
        print(SHOW_CURSOR, end='', flush=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        print(SHOW_CURSOR, end='', flush=True)
