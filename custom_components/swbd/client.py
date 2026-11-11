"""Serialized Bluetooth transport with device-confirmed state."""

import asyncio
import logging
from collections.abc import Callable

from bleak import BleakClient, BleakGATTCharacteristic
from bleak.backends.device import BLEDevice
from bleak.exc import BleakError
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

from .const import CHARACTERISTIC_UUID, SERVICE_UUID
from .protocol import QUERY, RockerState

_LOGGER = logging.getLogger(__name__)
STATE_TIMEOUT = 10


class SwbdClient:
    """Keep one connection; never retry a command after an ambiguous write."""

    def __init__(
        self,
        get_device: Callable[[], BLEDevice | None],
        name: str,
        on_state: Callable[[RockerState], None],
        on_disconnect: Callable[[], None],
    ) -> None:
        self._get_device = get_device
        self._name = name
        self._on_state = on_state
        self._on_disconnect = on_disconnect
        self._client: BleakClient | None = None
        self._characteristic: BleakGATTCharacteristic | None = None
        self._lock = asyncio.Lock()
        self._received = asyncio.Event()
        self.state: RockerState | None = None

    def _disconnected(self, client: BleakClient) -> None:
        if client is self._client:
            self.state = None
            self._received.set()
            self._on_disconnect()

    def _accept(self, data: bytearray) -> None:
        try:
            state = RockerState.parse(data)
        except ValueError:
            _LOGGER.debug("Ignoring invalid SWBD packet: %s", data.hex())
            return
        self.state = state
        self._received.set()
        self._on_state(state)

    async def _connect(self) -> None:
        if self._client and self._client.is_connected:
            return
        self.state = None
        device = self._get_device()
        if device is None:
            raise BleakError("Rocker is not visible to a connectable Bluetooth adapter")
        client = await establish_connection(
            BleakClientWithServiceCache,
            device,
            self._name,
            disconnected_callback=self._disconnected,
            ble_device_callback=self._get_device,
        )
        self._client = client
        service = client.services.get_service(SERVICE_UUID)
        char = service.get_characteristic(CHARACTERISTIC_UUID) if service else None
        if char is None or not {"write", "write-without-response"}.intersection(char.properties):
            raise BleakError("SWBD writable FFE1 characteristic is missing")
        if not {"notify", "indicate", "read"}.intersection(char.properties):
            raise BleakError("SWBD FFE1 characteristic cannot report state")
        self._characteristic = char
        if {"notify", "indicate"}.intersection(char.properties):

            def notified(sender: BleakGATTCharacteristic, data: bytearray) -> None:
                if client is self._client and client.is_connected:
                    self._accept(data)

            await client.start_notify(char, notified)

    async def _write(self, packet: bytes) -> None:
        assert self._client is not None and self._characteristic is not None
        await self._client.write_gatt_char(
            self._characteristic,
            packet,
            response="write" in self._characteristic.properties,
        )

    async def _wait_state(self) -> RockerState:
        assert self._client is not None and self._characteristic is not None
        if "read" in self._characteristic.properties:
            self._accept(await self._client.read_gatt_char(self._characteristic))
        async with asyncio.timeout(STATE_TIMEOUT):
            await self._received.wait()
        if not self._client.is_connected or self.state is None:
            raise BleakError("Rocker disconnected before reporting state")
        return self.state

    async def _query(self) -> RockerState:
        self._received.clear()
        await self._write(QUERY)
        return await self._wait_state()

    async def async_update(self) -> RockerState:
        async with self._lock:
            try:
                await self._connect()
                return await self._query()
            except BaseException:
                await self._close()
                raise

    async def async_set_field(self, field: str, value: int | bool) -> RockerState:
        async with self._lock:
            try:
                await self._connect()
                # Refresh first: a physical button may have changed another field.
                state = await self._query()
                packet = state.command(field, value)
                self._received.clear()
                await self._write(packet)
                return await self._wait_state()
            except BaseException:
                await self._close()
                raise

    async def _close(self) -> None:
        client, self._client = self._client, None
        self._characteristic = None
        self.state = None
        self._received.set()
        if client:
            try:
                await client.disconnect()
            except (BleakError, TimeoutError, OSError):
                _LOGGER.debug("Failed to close SWBD connection", exc_info=True)

    async def async_stop(self) -> None:
        async with self._lock:
            await self._close()
