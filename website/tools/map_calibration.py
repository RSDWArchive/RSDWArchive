"""Shared Dragonwilds world-map calibration for website data compilers."""

from __future__ import annotations

MAP_WORLD_SIZE = 420000.0
MAP_TILE_PIXELS = 6144.0
MAP_NATIVE_ZOOM = 4
# Match the RuneScape wiki map gadget's 2026-06-25 inset offsets.
MAP_OFFSET_X = 11075.0
MAP_OFFSET_Y = 100800.0 + 16885.0

MAP_X_MIN = -MAP_OFFSET_X
MAP_X_MAX = MAP_WORLD_SIZE - MAP_OFFSET_X
MAP_Y_MIN = -MAP_OFFSET_Y
MAP_Y_MAX = MAP_WORLD_SIZE - MAP_OFFSET_Y

# Sanity window; tune if legitimate cave/surface spawns are being clipped.
MAP_Z_MIN = -20000.0
MAP_Z_MAX = 40000.0


def map_filter_meta() -> dict:
    return {
        "worldSize": MAP_WORLD_SIZE,
        "tilePixels": MAP_TILE_PIXELS,
        "nativeZoom": MAP_NATIVE_ZOOM,
        "offsetX": MAP_OFFSET_X,
        "offsetY": MAP_OFFSET_Y,
        "x": [MAP_X_MIN, MAP_X_MAX],
        "y": [MAP_Y_MIN, MAP_Y_MAX],
        "z": [MAP_Z_MIN, MAP_Z_MAX],
    }
