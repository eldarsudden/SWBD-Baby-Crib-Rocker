"""Render the official Material Icons Bedroom baby asset for Home Assistant.

Development dependency: resvg-py==0.5.0 (not needed by the integration).
"""

from pathlib import Path

from resvg_py import svg_to_bytes

BRAND = Path(__file__).resolve().parents[1] / "custom_components" / "swbd" / "brand"


def main() -> None:
    source = (BRAND / "bedroom_baby.svg").read_text()
    # Trim the original two-unit padding to meet HA's square image guidelines.
    source = source.replace('viewBox="0 0 24 24"', 'viewBox="2 2 20 20"')
    for prefix, color in (("", "#03a9f4"), ("dark_", "#80d8ff")):
        svg = source.replace("<svg ", f'<svg fill="{color}" ', 1)
        for suffix, size in (("", 256), ("@2x", 512)):
            png = svg_to_bytes(svg_string=svg, width=size, height=size, skip_system_fonts=True)
            (BRAND / f"{prefix}icon{suffix}.png").write_bytes(png)


if __name__ == "__main__":
    main()
