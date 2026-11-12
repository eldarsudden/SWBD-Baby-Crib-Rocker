"""Use actual HA config entries, config flows, coordinator, and entity classes."""

from types import MappingProxyType, SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from bleak.exc import BleakError
from homeassistant.config_entries import ConfigEntries, ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import AbortFlow, FlowResultType
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from custom_components.swbd import async_setup_entry, async_unload_entry
from custom_components.swbd import config_flow as flow_module
from custom_components.swbd.config_flow import SwbdConfigFlow
from custom_components.swbd.coordinator import SwbdCoordinator
from custom_components.swbd.number import async_setup_entry as setup_numbers
from custom_components.swbd.protocol import RockerState
from custom_components.swbd.switch import async_setup_entry as setup_switches

from .test_protocol import frame

ADDRESS = "AA:BB:CC:DD:EE:FF"


@pytest.fixture
async def hass(tmp_path):
    instance = HomeAssistant(str(tmp_path))
    instance.config_entries = ConfigEntries(instance, {})
    dr.async_setup(instance)
    await dr.async_load(instance, load_empty=True)
    await er.async_load(instance, load_empty=True)
    yield instance
    await instance.async_stop(force=True)


@pytest.fixture
def entry(request):
    return ConfigEntry(
        domain="swbd",
        title="Test rocker",
        data={"address": ADDRESS, "local_name": getattr(request, "param", "SWBDdrv_mc5")},
        source="user",
        unique_id=ADDRESS,
        version=1,
        minor_version=1,
        options={},
        discovery_keys=MappingProxyType({}),
        subentries_data=[],
        state=ConfigEntryState.SETUP_IN_PROGRESS,
    )


@pytest.fixture
def info():
    return SimpleNamespace(address=ADDRESS, name="SWBDdrv_mc5")


@pytest.fixture
def flow(hass):
    handler = SwbdConfigFlow()
    handler.hass = hass
    handler.handler = "swbd"
    handler.context = {"source": "user"}
    return handler


async def test_user_flow_validates_and_creates_entry(flow, info, monkeypatch):
    monkeypatch.setattr(
        flow_module.bluetooth, "async_discovered_service_info", lambda *a, **kw: [info]
    )
    validate = AsyncMock(return_value=True)
    monkeypatch.setattr(flow, "_validate", validate)
    result = await flow.async_step_user()
    assert result["type"] is FlowResultType.FORM
    assert result["data_schema"]({"address": ADDRESS}) == {"address": ADDRESS}
    result = await flow.async_step_user({"address": ADDRESS})
    validate.assert_awaited_once_with(ADDRESS)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {"address": ADDRESS, "local_name": "SWBDdrv_mc5"}


async def test_discovery_requires_confirmation(flow, info, monkeypatch):
    validate = AsyncMock(return_value=True)
    monkeypatch.setattr(flow, "_validate", validate)
    result = await flow.async_step_bluetooth(info)
    assert result["step_id"] == "confirm"
    validate.assert_not_awaited()
    result = await flow.async_step_confirm({})
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_flow_connect_error_can_retry(flow, info, monkeypatch):
    monkeypatch.setattr(flow, "_validate", AsyncMock(side_effect=[False, True]))
    await flow.async_step_bluetooth(info)
    result = await flow.async_step_confirm({})
    assert result["errors"] == {"base": "cannot_connect"}
    assert (await flow.async_step_confirm({}))["type"] is FlowResultType.CREATE_ENTRY


async def test_flow_no_devices(flow, monkeypatch):
    monkeypatch.setattr(flow_module.bluetooth, "async_discovered_service_info", lambda *a, **kw: [])
    assert (await flow.async_step_user())["reason"] == "no_devices_found"


async def test_unsupported_name(flow):
    result = await flow.async_step_bluetooth(SimpleNamespace(name="Other", address=ADDRESS))
    assert result["reason"] == "not_supported"


async def test_non_remote_malutka_is_not_offered(flow, monkeypatch):
    info = SimpleNamespace(name="SWBDdrv_mc0", address=ADDRESS)
    monkeypatch.setattr(
        flow_module.bluetooth, "async_discovered_service_info", lambda *a, **kw: [info]
    )
    assert (await flow.async_step_user())["reason"] == "no_devices_found"
    assert (await flow.async_step_bluetooth(info))["reason"] == "not_supported"


async def test_duplicate_discovery_aborts(flow, hass, entry, info):
    hass.config_entries._entries[entry.entry_id] = entry
    with pytest.raises(AbortFlow, match="already_configured"):
        await flow.async_step_bluetooth(info)


async def test_validation_always_closes_client(flow, monkeypatch):
    transport = SimpleNamespace(
        async_update=AsyncMock(side_effect=BleakError("offline")), async_stop=AsyncMock()
    )
    monkeypatch.setattr(flow_module, "SwbdClient", lambda *a: transport)
    assert await flow._validate(ADDRESS) is False
    transport.async_stop.assert_awaited_once()


async def test_coordinator_availability_and_command_errors(hass, entry):
    coordinator = SwbdCoordinator(hass, entry)
    state = RockerState.parse(frame())
    coordinator.client.async_update = AsyncMock(return_value=state)
    await coordinator.async_config_entry_first_refresh()
    assert coordinator.last_update_success
    coordinator._disconnected()
    assert not coordinator.last_update_success
    coordinator._state_received(state)
    assert coordinator.last_update_success
    coordinator.client.async_set_field = AsyncMock(side_effect=BleakError("offline"))
    with pytest.raises(HomeAssistantError):
        await coordinator.async_set_field("enabled", True)
    assert not coordinator.last_update_success
    await coordinator.async_shutdown()


async def test_six_entities_have_distinct_ids_and_use_coordinator(hass, entry):
    coordinator = SwbdCoordinator(hass, entry)
    coordinator.async_set_updated_data(RockerState.parse(frame()))
    coordinator.async_set_field = AsyncMock()
    entry.runtime_data = coordinator
    entities = []
    await setup_switches(hass, entry, lambda new: entities.extend(new))
    await setup_numbers(hass, entry, lambda new: entities.extend(new))
    assert len(entities) == len({entity.unique_id for entity in entities}) == 6
    assert all(entity.available for entity in entities)
    assert entities[0].is_on
    assert entities[2].native_value == 3
    await entities[0].async_turn_off()
    await entities[2].async_set_native_value(6)
    assert coordinator.async_set_field.await_args_list[0].args == ("enabled", False)
    assert coordinator.async_set_field.await_args_list[1].args == ("speed", 6)
    with pytest.raises(HomeAssistantError):
        await entities[2].async_set_native_value(2.5)
    coordinator._disconnected()
    assert all(not entity.available for entity in entities)
    await coordinator.async_shutdown()


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        ("SWBDdrv_mc1", {"enabled", "speed", "hours", "minutes"}),
        ("SWBDdrv_mc2", {"enabled", "speed", "hours", "minutes", "sensitivity", "motion_enabled"}),
        ("SWBDdrv_mc3", {"enabled", "speed", "hours", "minutes", "sensitivity", "motion_enabled"}),
        ("SWBDdrv_mc5", {"enabled", "speed", "hours", "minutes", "sensitivity", "motion_enabled"}),
    ],
    indirect=["entry"],
)
async def test_model_controls(hass, entry, expected):
    coordinator = SwbdCoordinator(hass, entry)
    coordinator.async_set_updated_data(RockerState.parse(frame()))
    entry.runtime_data = coordinator
    entities = []
    await setup_switches(hass, entry, lambda new: entities.extend(new))
    await setup_numbers(hass, entry, lambda new: entities.extend(new))
    assert {entity.entity_description.key for entity in entities} == expected
    assert {entity.unique_id for entity in entities} == {f"{ADDRESS}_{key}" for key in expected}
    await coordinator.async_shutdown()


@pytest.mark.parametrize("entry", ["SWBDdrv_mc1"], indirect=True)
@pytest.mark.parametrize("field", ["sensitivity", "motion_enabled"])
async def test_painka_sensor_command_is_rejected_before_bluetooth(hass, entry, field):
    coordinator = SwbdCoordinator(hass, entry)
    coordinator.client.async_set_field = AsyncMock()
    with pytest.raises(HomeAssistantError, match="does not support"):
        await coordinator.async_set_field(field, 1)
    coordinator.client.async_set_field.assert_not_awaited()
    assert coordinator.last_update_success
    await coordinator.async_shutdown()


@pytest.mark.parametrize("entry", ["SWBDdrv_mc1"], indirect=True)
async def test_painka_upgrade_removes_only_its_unsupported_controls(hass, entry, monkeypatch):
    registry = er.async_get(hass)
    hass.config_entries._entries[entry.entry_id] = entry
    old_entities = {
        field: registry.async_get_or_create(
            "switch" if field in {"enabled", "motion_enabled"} else "number",
            "swbd",
            f"{ADDRESS}_{field}",
            config_entry=entry,
        )
        for field in ("enabled", "speed", "hours", "minutes", "sensitivity", "motion_enabled")
    }
    custom = registry.async_get_or_create("sensor", "swbd", "unrelated", config_entry=entry)
    other_device = registry.async_get_or_create("switch", "swbd", "OTHER_motion_enabled")
    retained = old_entities["enabled"]
    registry.async_update_entity(retained.entity_id, new_entity_id="switch.my_rocker")
    monkeypatch.setattr(
        SwbdCoordinator, "_async_update_data", AsyncMock(return_value=RockerState.parse(frame()))
    )
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", AsyncMock())
    assert await async_setup_entry(hass, entry)
    assert registry.async_get_entity_id("switch", "swbd", f"{ADDRESS}_motion_enabled") is None
    assert registry.async_get_entity_id("number", "swbd", f"{ADDRESS}_sensitivity") is None
    assert registry.async_get("switch.my_rocker") is not None
    for key in ("speed", "hours", "minutes"):
        assert registry.async_get(old_entities[key].entity_id) is not None
    assert registry.async_get(custom.entity_id) is not None
    assert registry.async_get(other_device.entity_id) is not None
    await entry.runtime_data.async_shutdown()


@pytest.mark.parametrize("entry", ["SWBDdrv_mc0", "unknown"], indirect=True)
async def test_unsupported_model_setup_does_not_connect(hass, entry, monkeypatch):
    update = AsyncMock()
    monkeypatch.setattr(SwbdCoordinator, "_async_update_data", update)
    with pytest.raises(ConfigEntryError, match="no confirmed Bluetooth"):
        await async_setup_entry(hass, entry)
    update.assert_not_awaited()


async def test_setup_and_unload_cleanup(hass, entry, monkeypatch):
    monkeypatch.setattr(
        SwbdCoordinator, "_async_update_data", AsyncMock(return_value=RockerState.parse(frame()))
    )
    forward = AsyncMock()
    unload = AsyncMock(return_value=True)
    monkeypatch.setattr(hass.config_entries, "async_forward_entry_setups", forward)
    monkeypatch.setattr(hass.config_entries, "async_unload_platforms", unload)
    assert await async_setup_entry(hass, entry)
    forward.assert_awaited_once()
    stop = AsyncMock()
    monkeypatch.setattr(entry.runtime_data.client, "async_stop", stop)
    assert await async_unload_entry(hass, entry)
    stop.assert_awaited_once()


async def test_setup_failure_closes_connection(hass, entry, monkeypatch):
    monkeypatch.setattr(
        SwbdCoordinator, "_async_update_data", AsyncMock(side_effect=BleakError("offline"))
    )
    stop = AsyncMock()
    monkeypatch.setattr("custom_components.swbd.client.SwbdClient.async_stop", stop)
    with pytest.raises(ConfigEntryNotReady):
        await async_setup_entry(hass, entry)
    stop.assert_awaited_once()
