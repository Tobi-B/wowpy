import asyncio
from bleak import BleakScanner, BleakClient

DEVICE_NAME = "Mip-52059"

# MiP BLE protocol: commands are written to the "send" characteristic,
# responses/notifications arrive on the "receive" characteristic.
SEND_CHARACTERISTIC = "0000ffe9-0000-1000-8000-00805f9b34fb"
RECEIVE_CHARACTERISTIC = "0000ffe4-0000-1000-8000-00805f9b34fb"

# Command opcodes
CMD_SET_CHEST_LED = 0x84  # followed by R, G, B


async def set_chest_led(client, r, g, b):
    await client.write_gatt_char(SEND_CHARACTERISTIC, bytes([CMD_SET_CHEST_LED, r, g, b]), response=False)


async def main():
    # The default 5s scan often misses the MiP; give it more time.
    device = await BleakScanner.find_device_by_name(DEVICE_NAME, timeout=15.0)
    if device is None:
        print(f"{DEVICE_NAME} not found")
        return
    print(f"found {DEVICE_NAME} at {device.address}")

    # No pair() here: the MiP does not require pairing and calling it drops the connection.
    async with BleakClient(device, timeout=20.0) as client:
        print(f"connected: {client.is_connected}")

        print("chest LED red")
        await set_chest_led(client, 0xFF, 0x00, 0x00)
        await asyncio.sleep(1.0)

        print("chest LED blue")
        await set_chest_led(client, 0x00, 0x00, 0xFF)
        await asyncio.sleep(1.0)

    print("disconnected")


if __name__ == '__main__':
    asyncio.run(main())
