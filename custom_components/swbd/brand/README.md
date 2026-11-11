# SWBD icon

Original asset: Google Material Icons **Bedroom baby**, filled style.

Source: https://github.com/google/material-design-icons/blob/master/src/search/bedroom_baby/materialicons/24px.svg

SVG blob SHA: `36dee717043b47bde2545f56ad5f1d2646c0b201`.
The original SVG is preserved as `bedroom_baby.svg`.
Copyright Google. Licensed under Apache License 2.0; see `LICENSE` in this folder.

PNG variants retain the original geometry, trim the transparent outer padding,
and apply blue `#03a9f4` for light themes or light blue `#80d8ff` for dark themes.
Backgrounds and cutouts remain transparent. Standard icons are 256×256 pixels;
`@2x` icons are 512×512 pixels. Home Assistant uses the square icon as the logo too.

To regenerate from the repository root:

```sh
.venv/bin/python -m pip install resvg-py==0.5.0
.venv/bin/python scripts/render_brand.py
```
