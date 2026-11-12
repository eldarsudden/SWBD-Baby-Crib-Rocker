"""Constants for SWBD Bluetooth rockers."""

DOMAIN = "swbd"
SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHARACTERISTIC_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
MODELS = {
    "SWBDdrv_mc1": "Паинька",
    "SWBDdrv_mc2": "Соня",
    "SWBDdrv_mc3": "Тихоня",
    "SWBDdrv_mc5": "Совушка",
}

# Capabilities of the BLE models documented by the manufacturer at karpesh.ru.
# The mc0 name in the upstream gateway whitelist is not evidence of BLE support:
# the production model 0 (Малютка) has no remote control.
BASE_CONTROLS = frozenset({"enabled", "speed", "hours", "minutes"})
ALL_CONTROLS = BASE_CONTROLS | {"sensitivity", "motion_enabled"}
MODEL_CONTROLS = {
    "SWBDdrv_mc1": BASE_CONTROLS,
    "SWBDdrv_mc2": ALL_CONTROLS,
    "SWBDdrv_mc3": ALL_CONTROLS,
    "SWBDdrv_mc5": ALL_CONTROLS,
}
