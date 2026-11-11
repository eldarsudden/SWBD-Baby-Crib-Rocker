"""Six-byte SWBD protocol, ported from Karpesh/swbd-ble2mqtt (MIT)."""

from dataclasses import dataclass

QUERY = bytes(6)
LIMITS = {"speed": (1, 6), "sensitivity": (0, 5), "hours": (0, 23), "minutes": (0, 59)}


def checksum(data: bytes | bytearray) -> int:
    """Match the original uint16_t accumulator, including overflow."""
    result = 0
    for value in data[:5]:
        result = (result + value * 211) & 0xFFFF
        result ^= result >> 8
    return result & 0xFF


@dataclass(frozen=True)
class RockerState:
    """A validated state received from the rocker."""

    raw: bytes

    @classmethod
    def parse(cls, data: bytes | bytearray) -> "RockerState":
        if len(data) != 6 or checksum(data) != data[5]:
            raise ValueError("Invalid SWBD packet length or checksum")
        if data[0] & 7 > 6 or data[1] & 7 > 5:
            raise ValueError("Invalid SWBD speed or sensitivity")
        if int.from_bytes(data[2:4], "big") > 1439:
            raise ValueError("Invalid SWBD timer")
        return cls(bytes(data))

    @property
    def enabled(self) -> bool:
        return bool(self.raw[0] & 0x80)

    @property
    def speed(self) -> int:
        return self.raw[0] & 7

    @property
    def sensitivity(self) -> int:
        return self.raw[1] & 7

    @property
    def motion_enabled(self) -> bool:
        return bool(self.raw[1] & 0x80)

    @property
    def timer(self) -> int:
        return int.from_bytes(self.raw[2:4], "big")

    @property
    def hours(self) -> int:
        return self.timer // 60

    @property
    def minutes(self) -> int:
        return self.timer % 60

    def command(self, field: str, value: int | bool) -> bytes:
        """Change one field, retaining upstream's masks and timer sentinel."""
        packet = bytearray(self.raw)
        if field in ("enabled", "motion_enabled"):
            if value not in (0, 1):
                raise ValueError("Switch value must be 0 or 1")
        elif field in LIMITS:
            low, high = LIMITS[field]
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{field} must be an integer between {low} and {high}")
        else:
            raise ValueError(f"Unknown field: {field}")

        if field == "enabled":
            packet[0] = (packet[0] & 0x7F) | (int(value) << 7)
        elif field == "speed":
            packet[0] = (packet[0] & 0x80) | value
        elif field == "sensitivity":
            packet[1] = (packet[1] & 0x80) | value
        elif field == "motion_enabled":
            packet[1] = (packet[1] & 0x7F) | (int(value) << 7)

        if field in ("hours", "minutes"):
            timer = value * 60 + self.minutes if field == "hours" else self.hours * 60 + value
            packet[2:4] = timer.to_bytes(2, "big")
        else:
            packet[2:4] = b"\xff\xff"
        packet[5] = checksum(packet)
        return bytes(packet)
