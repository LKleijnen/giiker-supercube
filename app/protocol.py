"""BLE-protocol voor de Giiker cube: decryptie, state-parsing en facelet-bouw."""

# ===========================================================================
# Cube configuratie
# ===========================================================================
CUBE_MAC = "EA:E6:DE:1E:DD:B3"
STATE_CHAR_UUID = "0000aadc-0000-1000-8000-00805f9b34fb"

GIIKER_KEY = [
    176,  81, 104, 224,  86, 137, 237, 119,  38,  26, 193, 161,
    210, 126, 150,  81,  93,  13, 236, 249,  89, 235,  88,  24,
    113,  81, 214, 131, 130, 199,   2, 169,  39, 165, 171,  41,
]

B, D, L, U, R, F = 0, 1, 2, 3, 4, 5
FACE_NAMES = ['B', 'D', 'L', 'U', 'R', 'F']
TURNS = {0: 1, 1: 2, 2: -1, 8: -2}

CORNER_COLORS = [
    [D, R, F], [R, U, F], [U, L, F], [L, D, F],
    [R, D, B], [U, R, B], [L, U, B], [D, L, B],
]

EDGE_COLORS = [
    [F, D], [F, R], [F, U], [F, L],
    [D, R], [U, R], [U, L], [D, L],
    [B, D], [B, R], [B, U], [B, L],
]

CORNER_FACE_INDICES = [
    [29, 15, 26], [ 9,  8, 20], [ 6, 38, 18], [44, 27, 24],
    [17, 35, 51], [ 2, 11, 45], [36,  0, 47], [33, 42, 53],
]

EDGE_FACE_INDICES = [
    [25, 28], [23, 12], [19,  7], [21, 41],
    [32, 16], [ 5, 10], [ 3, 37], [30, 43],
    [52, 34], [48, 14], [46,  1], [50, 39],
]

CENTER_INDICES = {0: 'U', 9: 'R', 18: 'F', 27: 'D', 36: 'L', 45: 'B'}
FACE_TO_COLOR = {'U': 'W', 'R': 'R', 'F': 'G', 'D': 'Y', 'L': 'O', 'B': 'B'}


# ===========================================================================
# Decryptie + parsing
# ===========================================================================
def decrypt(data: bytes) -> bytes:
    if len(data) < 20 or data[18] != 0xA7:
        return data
    k1 = (data[19] >> 4) & 0xF
    k2 = data[19] & 0xF
    out = bytearray(len(data))
    for i in range(len(data)):
        out[i] = (data[i] + GIIKER_KEY[i + k1] + GIIKER_KEY[i + k2]) & 0xFF
    return bytes(out)


def parse_state(data: bytes) -> dict:
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
    return (sorted(state['cp']) == list(range(1, 9))
            and sorted(state['ep']) == list(range(1, 13)))


def _map_corner_colors(piece_colors, orientation, slot):
    o = orientation
    if o != 3 and slot in (0, 2, 5, 7):
        o = 3 - o
    if o == 1:
        return [piece_colors[1], piece_colors[2], piece_colors[0]]
    if o == 2:
        return [piece_colors[2], piece_colors[0], piece_colors[1]]
    return list(piece_colors)


def _map_edge_colors(piece_colors, orientation):
    return list(piece_colors[::-1]) if orientation else list(piece_colors)


def build_facelets(state: dict) -> list:
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


def faces_2d(facelets):
    out = {}
    for face_letter, offset in [('U', 0), ('R', 9), ('F', 18), ('D', 27), ('L', 36), ('B', 45)]:
        flat = facelets[offset:offset + 9]
        out[face_letter] = [flat[0:3], flat[3:6], flat[6:9]]
    return out
