"""
Giiker Hi-G smart cube — connect, decrypt, en 2D flat-view tonen.

Werking is geverifieerd via handmatige decodering van capture.log:
  - Service 0000aadb, characteristic 0000aadc (read+notify, 20 bytes per packet)
  - Encryptie: per-packet XOR-style obfuscation met community-known key
    (byte[18] == 0xA7 is de marker, byte[19] bevat 2 keyshift-nibbles)
  - Laatste zet zit in byte 16 (NIET byte 18, dat is de encryptie-marker)
  - Corner/edge encoding volgt het originele Giiker JS-protocol

Voeg eigen acties toe in `on_state(state)` onderaan (bv. lampen aan/uit).
"""

import asyncio
import os
from bleak import BleakClient

# ---------------------------------------------------------------------------
# Cube configuratie
# ---------------------------------------------------------------------------
CUBE_MAC = "EA:E6:DE:1E:DD:B3"
STATE_CHAR_UUID = "0000aadc-0000-1000-8000-00805f9b34fb"

# Community-bekende sleutel voor Giiker XOR-obfuscatie
GIIKER_KEY = [
    176,  81, 104, 224,  86, 137, 237, 119,  38,  26, 193, 161,
    210, 126, 150,  81,  93,  13, 236, 249,  89, 235,  88,  24,
    113,  81, 214, 131, 130, 199,   2, 169,  39, 165, 171,  41,
]

# Face indices (uit Giiker JS-protocol)
B, D, L, U, R, F = 0, 1, 2, 3, 4, 5
FACE_NAMES = ['B', 'D', 'L', 'U', 'R', 'F']
TURNS = {0: 1, 1: 2, 2: -1, 8: -2}

# ---------------------------------------------------------------------------
# Cube geometrie — corner/edge piece colors + slot locations
# ---------------------------------------------------------------------------
# CORNER_COLORS[piece] = de drie face-kleuren van die fysieke piece
CORNER_COLORS = [
    [D, R, F], [R, U, F], [U, L, F], [L, D, F],
    [R, D, B], [U, R, B], [L, U, B], [D, L, B],
]

EDGE_COLORS = [
    [F, D], [F, R], [F, U], [F, L],
    [D, R], [U, R], [U, L], [D, L],
    [B, D], [B, R], [B, U], [B, L],
]

# Facelet-indices per slot, in URFDLB ordening (9 facelets per face).
# Layout: U[0-8] R[9-17] F[18-26] D[27-35] L[36-44] B[45-53]
# Bron: stateString() uit originele Giiker JS-library
CORNER_FACE_INDICES = [
    [29, 15, 26],
    [ 9,  8, 20],
    [ 6, 38, 18],
    [44, 27, 24],
    [17, 35, 51],
    [ 2, 11, 45],
    [36,  0, 47],
    [33, 42, 53],
]

EDGE_FACE_INDICES = [
    [25, 28], [23, 12], [19,  7], [21, 41],
    [32, 16], [ 5, 10], [ 3, 37], [30, 43],
    [52, 34], [48, 14], [46,  1], [50, 39],
]

# Centers (per face) — index 4 binnen elk face-blok van 9
CENTER_INDICES = {0: 'U', 9: 'R', 18: 'F', 27: 'D', 36: 'L', 45: 'B'}

# Mapping face-letter -> kleur-letter voor display
FACE_TO_COLOR = {'U': 'W', 'R': 'R', 'F': 'G', 'D': 'Y', 'L': 'O', 'B': 'B'}


# ---------------------------------------------------------------------------
# Decryptie + parsing
# ---------------------------------------------------------------------------
def decrypt(data: bytes) -> bytes:
    """Maak Giiker BLE-packet leesbaar. Gebruikt XOR-style key met 2 shifts."""
    if len(data) < 20 or data[18] != 0xA7:
        return data  # oudere firmware: niet versleuteld
    k1 = (data[19] >> 4) & 0xF
    k2 = data[19] & 0xF
    out = bytearray(len(data))
    for i in range(len(data)):
        out[i] = (data[i] + GIIKER_KEY[i + k1] + GIIKER_KEY[i + k2]) & 0xFF
    return bytes(out)


def parse_state(data: bytes) -> dict:
    """Decodeer bytes naar cube state: corner/edge positions + orientations + laatste zet."""
    cp, co, ep, eo = [], [], [], []
    for i in range(16):
        b = data[i]
        hi, lo = (b >> 4), (b & 0xF)
        if i < 4:
            cp.extend([hi, lo])
        elif i < 8:
            co.extend([hi, lo])
        elif i < 14:
            ep.extend([hi, lo])
        elif i < 16:
            for bit in (0x80, 0x40, 0x20, 0x10):
                eo.append(1 if (b & bit) else 0)
            if i == 14:
                for bit in (0x08, 0x04, 0x02, 0x01):
                    eo.append(1 if (b & bit) else 0)

    # Laatste zet zit in byte 16 (empirisch geverifieerd op deze cube)
    last_move = None
    move_byte = data[16]
    face_idx = (move_byte >> 4) - 1
    turn_idx = (move_byte & 0xF) - 1
    if 0 <= face_idx < 6 and turn_idx in TURNS:
        face = FACE_NAMES[face_idx]
        amt = TURNS[turn_idx]
        last_move = {1: face, 2: f"{face}2", -1: f"{face}'", -2: f"{face}2'"}[amt]

    return {'cp': cp, 'co': co, 'ep': ep, 'eo': eo, 'last_move': last_move}


def is_valid_state(state: dict) -> bool:
    """Sanity-check: zijn cp en ep geldige permutaties van 1..8 en 1..12?"""
    return (sorted(state['cp']) == list(range(1, 9))
            and sorted(state['ep']) == list(range(1, 13)))


# ---------------------------------------------------------------------------
# Cube state -> 54 facelets
# ---------------------------------------------------------------------------
def _map_corner_colors(piece_colors, orientation, slot):
    """Pas Giiker's orientation+mirror logic toe op corner stickers."""
    o = orientation
    if o != 3 and slot in (0, 2, 5, 7):
        o = 3 - o
    if o == 1:
        return [piece_colors[1], piece_colors[2], piece_colors[0]]
    if o == 2:
        return [piece_colors[2], piece_colors[0], piece_colors[1]]
    return list(piece_colors)  # o == 3 (solved)


def _map_edge_colors(piece_colors, orientation):
    return list(piece_colors[::-1]) if orientation else list(piece_colors)


def build_facelets(state: dict) -> list[str]:
    """Bouw lijst van 54 facelets (kleur-letter), URFDLB ordening."""
    facelets = ['?'] * 54

    for idx, face in CENTER_INDICES.items():
        facelets[idx + 4] = FACE_TO_COLOR[face]

    for slot in range(8):
        piece = state['cp'][slot] - 1
        if not (0 <= piece < 8):
            continue
        piece_face_colors = [FACE_NAMES[f] for f in CORNER_COLORS[piece]]
        mapped = _map_corner_colors(piece_face_colors, state['co'][slot], slot)
        for k in range(3):
            facelets[CORNER_FACE_INDICES[slot][k]] = FACE_TO_COLOR[mapped[k]]

    for slot in range(12):
        piece = state['ep'][slot] - 1
        if not (0 <= piece < 12):
            continue
        piece_face_colors = [FACE_NAMES[f] for f in EDGE_COLORS[piece]]
        mapped = _map_edge_colors(piece_face_colors, state['eo'][slot])
        for k in range(2):
            facelets[EDGE_FACE_INDICES[slot][k]] = FACE_TO_COLOR[mapped[k]]

    return facelets


# ---------------------------------------------------------------------------
# Weergave: 2D flat-view (kruis-net)
# ---------------------------------------------------------------------------
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


def _sticker(letter: str) -> str:
    return f"{ANSI_BG.get(letter, '')} {letter} {ANSI_RESET}"


def faces_2d(facelets: list[str]) -> dict[str, list[list[str]]]:
    """Splits 54-array op in dict{face_letter: 3x3 matrix}. Voor logica/triggers."""
    out = {}
    for face_letter, offset in [('U', 0), ('R', 9), ('F', 18), ('D', 27), ('L', 36), ('B', 45)]:
        flat = facelets[offset:offset + 9]
        out[face_letter] = [flat[0:3], flat[3:6], flat[6:9]]
    return out


def print_flat_view(facelets: list[str], last_move: str | None) -> None:
    U = facelets[0:9]; R = facelets[9:18]; F = facelets[18:27]
    Dn = facelets[27:36]; Ln = facelets[36:45]; Bn = facelets[45:54]

    def row(face, r):
        return "".join(_sticker(face[r * 3 + i]) for i in range(3))

    pad = " " * 10  # 9 chars L-face + 1 separator -> aligned met F
    print(f"\n  Laatste zet: {last_move or '-'}\n")
    for r in range(3):
        print(pad + row(U, r))
    print()
    for r in range(3):
        print(row(Ln, r) + " " + row(F, r) + " " + row(R, r) + " " + row(Bn, r))
    print()
    for r in range(3):
        print(pad + row(Dn, r))
    print()


# ---------------------------------------------------------------------------
# Trigger-hook: jouw eigen code voor lampen, etc.
# ---------------------------------------------------------------------------
def on_state(state: dict, facelets: list[str], faces: dict) -> None:
    """
    Wordt aangeroepen na elke zet, met de complete cube state.

    Voorbeeld-triggers:
      - faces['U'][0][0] == 'R'  -> rode sticker linksboven op U-face
      - all(c == 'W' for c in faces['U'][0] + faces['U'][1] + faces['U'][2])
        -> hele U-face is wit (opgelost van boven)
      - state['last_move'] == "R" -> roep iets aan na R-move

    Voeg hieronder je smart-home code toe (bv. via requests/aiohttp naar Hue, MQTT, etc).
    """
    # Voorbeeld 1: doe iets als hele U-face wit is
    # if all(c == 'W' for row in faces['U'] for c in row):
    #     print(">> U-face helemaal wit -> lamp aan!")

    # Voorbeeld 2: reageer op specifieke zet
    # if state['last_move'] == "R'":
    #     print(">> R prime -> doe iets")
    pass


def is_fully_solved(facelets: list[str]) -> bool:
    """Check of alle 6 vlakken één kleur hebben."""
    for offset in (0, 9, 18, 27, 36, 45):
        face = facelets[offset:offset + 9]
        if any(c != face[0] for c in face):
            return False
    return True


# ---------------------------------------------------------------------------
# BLE loop
# ---------------------------------------------------------------------------
async def main() -> None:
    if os.name == 'nt':
        os.system('')  # activeer ANSI-kleuren in Windows terminal

    print(f"Verbinden met cube {CUBE_MAC}...")
    async with BleakClient(CUBE_MAC) as client:
        print(f"Verbonden: {client.is_connected}\n")

        def handle(_sender, raw: bytearray):
            data = decrypt(bytes(raw))
            state = parse_state(data)
            if not is_valid_state(state):
                print(f"⚠  Ongeldige state na decode. Raw: {bytes(raw).hex()}")
                print(f"    Decoded cp={state['cp']} ep={state['ep']}")
                return
            facelets = build_facelets(state)
            faces = faces_2d(facelets)
            print_flat_view(facelets, state['last_move'])
            if is_fully_solved(facelets):
                print("  🎉 CUBE OPGELOST!")
            on_state(state, facelets, faces)

        # Toon initiële state
        try:
            initial = await client.read_gatt_char(STATE_CHAR_UUID)
            print(f"Initiële state hex: {bytes(initial).hex()}")
            handle(None, initial)
        except Exception as exc:
            print(f"Kon initiële state niet lezen: {exc}")

        await client.start_notify(STATE_CHAR_UUID, handle)
        print("Draai de cube. Ctrl+C om te stoppen.\n")

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print("\nGestopt.")
        finally:
            try:
                await client.stop_notify(STATE_CHAR_UUID)
            except Exception:
                pass


if __name__ == "__main__":
    asyncio.run(main())
