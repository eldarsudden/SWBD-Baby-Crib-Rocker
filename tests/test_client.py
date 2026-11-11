"""Exercise the real transport logic against a controllable BLE peripheral."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from bleak.exc import BleakError

from custom_components.swbd import client as module
from custom_components.swbd.protocol import QUERY, RockerState

from .test_protocol import frame


class Peripheral:
    def __init__(self, *, properties=None):
        self.is_connected = True
        self.char = SimpleNamespace(properties=properties or ["write", "notify"])
        self.services = SimpleNamespace(
            get_service=lambda uuid: SimpleNamespace(get_characteristic=lambda uuid: self.char)
        )
        self.raw = frame()
        self.writes = []
        self.notify = None
        self.silent = False
        self.fail_command = False
        self.disconnect = AsyncMock(side_effect=self._disconnect)
        self.callback = None

    async def _disconnect(self):
        self.is_connected = False
        if self.callback:
            self.callback(self)

    async def start_notify(self, char, notify):
        self.notify = notify

    async def write_gatt_char(self, char, data, response):
        assert response == ("write" in self.char.properties)
        self.writes.append(data)
        if data != QUERY:
            if self.fail_command:
                raise BleakError("ambiguous write")
            result = bytearray(data)
            if result[2:4] == b"\xff\xff":
                result[2:4] = self.raw[2:4]
            from custom_components.swbd.protocol import checksum

            result[5] = checksum(result)
            self.raw = bytes(result)
        if self.notify and not self.silent:
            self.notify(char, bytearray(self.raw))

    async def read_gatt_char(self, char):
        return bytearray(self.raw)


@pytest.fixture
def transport(monkeypatch):
    peripheral = Peripheral()
    on_state, on_disconnect = Mock(), Mock()

    async def establish(*args, **kwargs):
        peripheral.is_connected = True
        peripheral.callback = kwargs["disconnected_callback"]
        return peripheral

    connector = AsyncMock(side_effect=establish)
    monkeypatch.setattr(module, "establish_connection", connector)
    client = module.SwbdClient(lambda: object(), "Test", on_state, on_disconnect)
    return client, peripheral, connector, on_state, on_disconnect


async def test_query_and_notify(transport):
    client, peripheral, connect, changed, _ = transport
    assert await client.async_update() == RockerState.parse(frame())
    assert peripheral.writes == [QUERY]
    peripheral.notify(peripheral.char, bytearray(frame(a=2)))
    assert not client.state.enabled
    assert changed.call_count == 2
    await client.async_stop()
    peripheral.disconnect.assert_awaited_once()


async def test_refresh_before_command_preserves_physical_changes(transport):
    client, peripheral, _, _, _ = transport
    await client.async_update()
    peripheral.raw = frame(a=2, b=3, timer=33)
    state = await client.async_set_field("speed", 6)
    assert not state.enabled
    assert (state.speed, state.sensitivity, state.timer) == (6, 3, 33)
    assert peripheral.writes[-2] == QUERY
    assert peripheral.writes[-1][2:4] == b"\xff\xff"
    await client.async_stop()


async def test_concurrent_commands_are_serialized(transport):
    client, peripheral, connect, _, _ = transport
    await asyncio.gather(client.async_set_field("hours", 4), client.async_set_field("minutes", 50))
    assert client.state.timer == 290
    assert connect.await_count == 1
    assert peripheral.writes[0] == peripheral.writes[2] == QUERY
    await client.async_stop()


async def test_timeout_clears_stale_state(transport, monkeypatch):
    client, peripheral, _, _, _ = transport
    await client.async_update()
    peripheral.silent = True
    monkeypatch.setattr(module, "STATE_TIMEOUT", 0.01)
    with pytest.raises(TimeoutError):
        await client.async_set_field("enabled", True)
    assert client.state is None
    # No command can be built from a state left over before the timeout.
    assert peripheral.writes == [QUERY, QUERY]
    peripheral.disconnect.assert_awaited_once()


async def test_ambiguous_command_not_replayed(transport):
    client, peripheral, connect, _, _ = transport
    peripheral.fail_command = True
    with pytest.raises(BleakError):
        await client.async_set_field("enabled", False)
    assert len(peripheral.writes) == 2
    assert connect.await_count == 1
    assert client.state is None
    peripheral.fail_command = False
    await client.async_update()
    assert peripheral.writes[-1] == QUERY
    assert len(peripheral.writes) == 3
    await client.async_stop()


async def test_disconnect_marks_state_unavailable_and_reconnects(transport):
    client, peripheral, connect, _, lost = transport
    await client.async_update()
    await peripheral._disconnect()
    assert client.state is None
    lost.assert_called_once()
    await client.async_update()
    assert connect.await_count == 2
    await client.async_stop()


async def test_read_and_write_without_response(transport):
    client, peripheral, _, _, _ = transport
    peripheral.char.properties = ["read", "write-without-response"]
    assert await client.async_update() == RockerState.parse(frame())
    assert (await client.async_set_field("enabled", False)).enabled is False
    await client.async_stop()


async def test_missing_characteristic_closes_connection(transport):
    client, peripheral, _, _, _ = transport
    peripheral.services.get_service = lambda uuid: None
    with pytest.raises(BleakError, match="missing"):
        await client.async_update()
    peripheral.disconnect.assert_awaited_once()


async def test_no_visible_device(monkeypatch):
    connector = AsyncMock()
    monkeypatch.setattr(module, "establish_connection", connector)
    client = module.SwbdClient(lambda: None, "Test", Mock(), Mock())
    with pytest.raises(BleakError, match="not visible"):
        await client.async_update()
    connector.assert_not_awaited()


async def test_cancellation_closes_connection(transport):
    client, peripheral, _, _, _ = transport
    peripheral.silent = True
    task = asyncio.create_task(client.async_update())
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    peripheral.disconnect.assert_awaited_once()


async def test_stopped_session_cannot_publish_late_notification(transport):
    client, peripheral, _, changed, _ = transport
    await client.async_update()
    notify = peripheral.notify
    await client.async_stop()
    notify(peripheral.char, bytearray(frame(a=1)))
    assert client.state is None
    assert changed.call_count == 1


async def test_invalid_notification_does_not_replace_state(transport):
    client, peripheral, _, changed, _ = transport
    original = await client.async_update()
    peripheral.notify(peripheral.char, bytearray(b"bad"))
    assert client.state == original
    assert changed.call_count == 1
    await client.async_stop()
