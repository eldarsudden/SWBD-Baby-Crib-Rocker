"""Known wire vectors and compatibility with upstream C arithmetic."""

import ctypes
import random
import subprocess

import pytest

from custom_components.swbd.protocol import RockerState, checksum


def frame(a=0x83, b=0x82, timer=125, reserved=0x47):
    data = bytearray([a, b, timer >> 8, timer & 255, reserved, 0])
    data[5] = checksum(data)
    return bytes(data)


def test_decode():
    state = RockerState.parse(frame())
    assert (state.enabled, state.speed, state.sensitivity, state.motion_enabled) == (
        True,
        3,
        2,
        True,
    )
    assert (state.timer, state.hours, state.minutes) == (125, 2, 5)


def test_zero_state():
    state = RockerState.parse(bytes(6))
    assert not state.enabled
    assert state.timer == state.speed == state.sensitivity == 0


def test_checksum_matches_original_c(tmp_path):
    # Independently compile the exact arithmetic/types used by main/swbd.c.
    source = tmp_path / "checksum.c"
    source.write_text("""#include <stdint.h>
uint8_t chsum(uint8_t array[6]) {
    uint8_t i;
    uint16_t sum=0;
    for (i=0; i<5; i++) {
        sum = sum + array[i]*211;
        sum = (sum ^ (sum >> 8));
    }
    return sum & 0xFF;
}
""")
    library = tmp_path / "checksum.so"
    subprocess.run(["cc", "-shared", "-fPIC", str(source), "-o", str(library)], check=True)
    function = ctypes.CDLL(str(library)).chsum
    function.argtypes = [ctypes.POINTER(ctypes.c_uint8)]
    function.restype = ctypes.c_uint8
    rng = random.Random(42)
    vectors = [bytes(6), bytes([255] * 6)] + [rng.randbytes(6) for _ in range(1000)]
    for data in vectors:
        assert checksum(data) == function((ctypes.c_uint8 * 6)(*data))


@pytest.mark.parametrize(
    ("field", "value", "prefix"),
    [
        ("enabled", False, b"\x03\x82\xff\xff\x47"),
        ("speed", 6, b"\x86\x82\xff\xff\x47"),
        ("sensitivity", 0, b"\x83\x80\xff\xff\x47"),
        ("motion_enabled", False, b"\x83\x02\xff\xff\x47"),
        ("hours", 23, b"\x83\x82\x05\x69\x47"),
        ("minutes", 59, b"\x83\x82\x00\xb3\x47"),
    ],
)
def test_commands(field, value, prefix):
    state = RockerState.parse(frame())
    result = state.command(field, value)
    assert result == prefix + bytes([checksum(prefix)])
    assert state.raw == frame()


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("speed", 0),
        ("speed", 7),
        ("sensitivity", 6),
        ("hours", 24),
        ("minutes", 60),
        ("minutes", -1),
        ("minutes", 1.5),
        ("speed", True),
        ("enabled", 2),
        ("unknown", 1),
    ],
)
def test_invalid_commands(field, value):
    with pytest.raises(ValueError):
        RockerState.parse(frame()).command(field, value)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        bytes(5),
        bytes(7),
        b"\x83\x82\x00\x7d\x47\x00",
        frame(a=7),
        frame(b=6),
        frame(timer=65535),
    ],
)
def test_invalid_packets(data):
    with pytest.raises(ValueError):
        RockerState.parse(data)


def test_reserved_bits_follow_upstream_masks():
    state = RockerState.parse(frame(a=0xFB, b=0xFA))
    assert state.command("enabled", False)[0] == 0x7B
    assert state.command("motion_enabled", False)[1] == 0x7A
    assert state.command("speed", 1)[0] == 0x81
    assert state.command("sensitivity", 1)[1] == 0x81
