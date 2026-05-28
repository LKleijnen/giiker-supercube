"""
Diagnose-script voor Giiker / Hi-G smart cube.

Doel:
  1. Volledige BLE-discovery (alle services + characteristics + properties).
  2. Abonneer op ALLE notify-capable characteristics tegelijk.
  3. Log iedere ruwe notification met timestamp + source UUID + hex bytes.
  4. Schrijf ook alles naar capture.log voor offline analyse.

Gebruik:
  - Zet de cube AAN (draai er 1x aan zodat hij wakker is).
  - Draai 1 zet, wacht 1 sec, draai de tegenzet, etc. Doe duidelijke zetten
    zoals R, R', U, U', en daarna 2x dezelfde state om te zien of bytes herhalen.
  - Druk Ctrl+C om te stoppen.

Vereist:
  pip install bleak
"""

import asyncio
import datetime
from bleak import BleakClient, BleakScanner

CUBE_MAC = "EA:E6:DE:1E:DD:B3"
LOG_PATH = "capture.log"


def ts() -> str:
    return datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]


def log_line(line: str) -> None:
    print(line)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(line + "\n")


async def scan_and_show_name() -> None:
    log_line(f"[{ts()}] Scannen naar BLE devices (5 sec)...")
    devices = await BleakScanner.discover(timeout=5.0)
    for d in devices:
        if d.address.upper() == CUBE_MAC.upper():
            log_line(f"[{ts()}] Cube gevonden: name='{d.name}' rssi={d.rssi}")
            return
    log_line(f"[{ts()}] WAARSCHUWING: cube niet gezien in scan. "
             "Verbind toch (cube wordt soms pas gezien bij verbinden).")


async def dump_services(client: BleakClient) -> list[str]:
    """Print alle services + characteristics, return lijst van notify UUIDs."""
    notify_uuids: list[str] = []

    log_line(f"\n[{ts()}] === SERVICES & CHARACTERISTICS ===")
    services = client.services
    for service in services:
        log_line(f"  Service: {service.uuid}  (desc: {service.description})")
        for char in service.characteristics:
            props = ",".join(char.properties)
            log_line(f"    Char: {char.uuid}  props=[{props}]  handle={char.handle}")
            for desc in char.descriptors:
                log_line(f"      Descriptor: {desc.uuid}")
            if "notify" in char.properties or "indicate" in char.properties:
                notify_uuids.append(char.uuid)
            # Probeer leesbare characteristics meteen te lezen
            if "read" in char.properties:
                try:
                    value = await client.read_gatt_char(char.uuid)
                    log_line(f"      READ -> {value.hex()}  "
                             f"(len={len(value)}, ascii='{safe_ascii(value)}')")
                except Exception as exc:
                    log_line(f"      READ failed: {exc}")
    log_line(f"[{ts()}] === EINDE DISCOVERY ===\n")
    return notify_uuids


def safe_ascii(data: bytes) -> str:
    return "".join(chr(b) if 32 <= b < 127 else "." for b in data)


def make_handler(uuid: str):
    """Maakt een notification handler die de bron-UUID inkleurt."""
    last_data = {"hex": None, "count": 0}

    def handler(_sender, data: bytearray):
        h = data.hex()
        if h == last_data["hex"]:
            last_data["count"] += 1
            line = (f"[{ts()}] [{uuid[-12:]}] len={len(data):>2} "
                    f"hex={h}  (HERHALING #{last_data['count']})")
        else:
            last_data["hex"] = h
            last_data["count"] = 1
            line = (f"[{ts()}] [{uuid[-12:]}] len={len(data):>2} "
                    f"hex={h}  ascii='{safe_ascii(bytes(data))}'")
        log_line(line)

    return handler


async def main() -> None:
    open(LOG_PATH, "w", encoding="utf-8").close()
    log_line(f"[{ts()}] Diagnose gestart. Log -> {LOG_PATH}")

    await scan_and_show_name()

    log_line(f"[{ts()}] Verbinden met {CUBE_MAC}...")
    async with BleakClient(CUBE_MAC) as client:
        log_line(f"[{ts()}] Verbonden: {client.is_connected}")

        notify_uuids = await dump_services(client)

        if not notify_uuids:
            log_line(f"[{ts()}] GEEN notify characteristics gevonden. Stop.")
            return

        log_line(f"[{ts()}] Abonneren op {len(notify_uuids)} notify-characteristics:")
        for u in notify_uuids:
            log_line(f"    - {u}")
            try:
                await client.start_notify(u, make_handler(u))
            except Exception as exc:
                log_line(f"      start_notify failed: {exc}")

        log_line(f"\n[{ts()}] ==> LUISTEREN. Draai nu de cube. Ctrl+C om te stoppen.\n"
                 "    Tip: doe 1 zet, wacht, dan tegenzet (R, R', U, U', ...).\n"
                 "    Doe ook 2x exact dezelfde state om te zien of bytes identiek zijn\n"
                 "    (dat onthult of de data versleuteld is).\n")

        try:
            while True:
                await asyncio.sleep(1)
        except (KeyboardInterrupt, asyncio.CancelledError):
            log_line(f"\n[{ts()}] Gestopt door gebruiker.")
        finally:
            for u in notify_uuids:
                try:
                    await client.stop_notify(u)
                except Exception:
                    pass


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
