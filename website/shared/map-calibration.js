(function () {
  "use strict";

  const WORLD_SIZE = 420000;
  const TILE_PIXELS = 6144;
  const NATIVE_ZOOM = 4;
  // Match the RuneScape wiki map gadget's 2026-06-25 inset offsets.
  const OFFSET_X = 11075;
  const OFFSET_Y = 100800 + 16885;

  const X_MIN = -OFFSET_X;
  const X_MAX = WORLD_SIZE - OFFSET_X;
  const Y_MIN = -OFFSET_Y;
  const Y_MAX = WORLD_SIZE - OFFSET_Y;

  function scaleMultiplier() {
    return TILE_PIXELS / WORLD_SIZE / Math.pow(2, NATIVE_ZOOM);
  }

  function leafletBounds() {
    return [
      { lon: X_MIN, lat: Y_MIN },
      { lon: X_MAX, lat: Y_MAX }
    ];
  }

  function createCRS(L) {
    const mult = scaleMultiplier();
    return L.extend({}, L.CRS.Simple, {
      projection: L.Projection.LonLat,
      transformation: new L.Transformation(mult, -mult * X_MIN, mult, -mult * Y_MIN)
    });
  }

  function createLeafletMap(container, options) {
    if (!window.L) {
      throw new Error("Leaflet is required before map calibration can create a map.");
    }

    const bounds = leafletBounds();
    const map = window.L.map(container, {
      crs: createCRS(window.L),
      maxBounds: bounds,
      attributionControl: false,
      ...options
    });

    window.L.tileLayer("https://maps.runescape.wiki/dw/tiles/{z}/{x}_{y}.png").addTo(map);
    map.fitBounds(bounds);
    return map;
  }

  window.RSDW_MAP_CALIBRATION = Object.freeze({
    worldSize: WORLD_SIZE,
    tilePixels: TILE_PIXELS,
    nativeZoom: NATIVE_ZOOM,
    offsetX: OFFSET_X,
    offsetY: OFFSET_Y,
    xMin: X_MIN,
    xMax: X_MAX,
    yMin: Y_MIN,
    yMax: Y_MAX,
    scaleMultiplier,
    leafletBounds,
    createCRS,
    createLeafletMap
  });
})();
