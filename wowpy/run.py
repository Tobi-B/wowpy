"""Run a saved block program without the browser.

    python -m wowpy.run programs/red-light.py [--mock] [--name Mip-52059]

Prints every command the program sends, then exits 0 on success, 1 on a
program error.
"""

import argparse
import asyncio
import sys
from pathlib import Path

from . import protocol as p
from .mip import MiP
from .mock import MockClient
from .program import Program, ProgramError


def _hex(data):
    return bytes(data).hex(" ").upper()


async def _main(args):
    if args.mock:
        mip = MiP(None, client=MockClient())
    elif args.address:
        mip = MiP(args.address)
    else:
        mip = await MiP.discover(args.name, timeout=args.timeout)

    code = Path(args.program).read_text(encoding="utf-8")
    program = Program(mip, log=lambda text: print(text, flush=True))

    def on_send(data):
        name = p.NAMES_BY_OPCODE.get(data[0], f"0x{data[0]:02X}")
        print(f"sent {name} [{_hex(data)}]", flush=True)

    mip.on_send = on_send
    async with mip:
        try:
            state = await program.run(code)
        except ProgramError as e:
            print(f"program error: {e}", file=sys.stderr)
            return 1
        finally:
            try:
                await mip.stop()
            except Exception:
                pass
    print(f"program {state}", flush=True)
    return 1 if state == "error" else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("program", help="a generated .py file, e.g. programs/red-light.py")
    ap.add_argument("--mock", action="store_true", help="run against the mock robot instead of hardware")
    ap.add_argument("--name", default=None, help="connect to this MiP by name")
    ap.add_argument("--address", default=None, help="connect to this BLE address")
    ap.add_argument("--timeout", type=float, default=15.0, help="scan timeout in seconds")
    args = ap.parse_args(argv)
    try:
        return asyncio.run(_main(args))
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
