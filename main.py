"""Example: find a MiP, blink its chest LED, and read its status."""

import asyncio

from wowpy import MiP


async def main():
    mip = await MiP.discover()
    async with mip:
        print("connected")

        print("chest LED red")
        await mip.set_chest_led(255, 0, 0)
        await asyncio.sleep(1.0)

        print("chest LED blue")
        await mip.set_chest_led(0, 0, 255)
        await asyncio.sleep(1.0)

        battery, position = await mip.get_status()
        print(f"battery {battery}%, position code {position}")

    print("disconnected")


if __name__ == '__main__':
    asyncio.run(main())
