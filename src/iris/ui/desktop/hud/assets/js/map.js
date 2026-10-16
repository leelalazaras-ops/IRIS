/* ============================================================
   IRIS Command Center — geographic map module (window.IrisMap).

   Lightweight slippy-map implementation over OpenStreetMap raster
   tiles: pan (drag), zoom (wheel / buttons / double-click), standard
   attribution, and explicit loading / error / offline states.
   Created lazily by app.js on first open of the Map view, so tile
   fetching and layout work never happen before then. No external
   libraries.

   Tiles come from https://tile.openstreetmap.org/{z}/{x}/{y}.png
   under the OSMF Tile Usage Policy (fair, light use, attribution,
   no bulk download). This client only requests tiles currently
   visible in the panel and drops off-screen tiles after two renders.
   ============================================================ */
"use strict";

(function () {
  const TILE_SIZE = 256;
  const MIN_ZOOM = 2;
  const MAX_ZOOM = 17;
  const TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

  function lng2px(lng, zoom) {
    return ((lng + 180) / 360) * Math.pow(2, zoom) * TILE_SIZE;
  }
  function px2lng(x, zoom) {
    const tiles = Math.pow(2, zoom);
    return (x / (tiles * TILE_SIZE)) * 360 - 180;
  }
  function lat2py(lat, zoom) {
    const clamped = Math.min(85.05112878, Math.max(-85.05112878, lat));
    const s = Math.sin((clamped * Math.PI) / 180);
    return (0.5 - 0.25 * Math.log((1 + s) / (1 - s)) / Math.PI) * Math.pow(2, zoom) * TILE_SIZE;
  }
  function py2lat(y, zoom) {
    const tiles = Math.pow(2, zoom);
    const n = Math.PI - (2 * Math.PI * y) / (tiles * TILE_SIZE);
    return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)));
  }

  function create(container) {
    if (!container) throw new Error("IrisMap: container element required");
    const state = {
      zoom: 3,
      centerX: 0,   // world px at current zoom
      centerY: 0,
      dragging: false,
      lastX: 0,
      lastY: 0,
      tiles: new Map(),  // key -> {img, keepCount}
      offline: !navigator.onLine,
      loadErr: 0,
      failedOnce: false,
    };
    state.centerX = lng2px(0, state.zoom);
    state.centerY = lat2py(40, state.zoom);

    // ---- DOM scaffolding
    const wrap = document.createElement("div");
    wrap.className = "map-viewport";
    container.appendChild(wrap);

    const layer = document.createElement("div");
    layer.className = "map-layer";
    wrap.appendChild(layer);

    const crosshair = document.createElement("div");
    crosshair.className = "map-crosshair";
    crosshair.setAttribute("aria-hidden", "true");
    wrap.appendChild(crosshair);

    const controls = document.createElement("div");
    controls.className = "map-controls";
    const zIn = document.createElement("button");
    zIn.className = "btn btn-ghost map-btn";
    zIn.textContent = "+";
    zIn.title = "Zoom in (scroll or double-click also zoom)";
    const zOut = document.createElement("button");
    zOut.className = "btn btn-ghost map-btn";
    zOut.textContent = "\u2212";
    zOut.title = "Zoom out";
    controls.appendChild(zIn);
    controls.appendChild(zOut);
    wrap.appendChild(controls);

    const status = document.createElement("div");
    status.className = "map-status hidden";
    wrap.appendChild(status);

    function setStatus(text, kind) {
      if (!text) { status.classList.add("hidden"); return; }
      status.textContent = text;
      status.className = "map-status" + (kind ? " map-" + kind : "");
      status.classList.remove("hidden");
    }

    function updateCoords() {
      const c = document.getElementById("map-coords");
      if (c) {
        c.textContent = "z" + state.zoom + " \u00b7 " +
          py2lat(state.centerY, state.zoom).toFixed(1) + ", " +
          px2lng(state.centerX, state.zoom).toFixed(1);
      }
      // Real hyperlink attribution (required by OSMF policy); filled once.
      const attrib = document.getElementById("map-attrib");
      if (attrib && !attrib.dataset.wired) {
        attrib.dataset.wired = "1";
        attrib.innerHTML =
          " map data &copy; <a href='https://www.openstreetmap.org/copyright' target='_blank' rel='noopener'>" +
          "OpenStreetMap</a> contributors";
      }
    }

    function clearTiles() {
      state.tiles.forEach((e) => e.img.remove());
      state.tiles.clear();
    }

    // ---- rendering: place visible tiles, drop stale ones
    function render() {
      const w = wrap.clientWidth || 600;
      const h = wrap.clientHeight || 400;
      layer.style.width = w + "px";
      layer.style.height = h + "px";

      const seen = new Set();
      let requested = 0;
      const tx0 = Math.floor((state.centerX - w / 2) / TILE_SIZE);
      const tx1 = Math.floor((state.centerX + w / 2) / TILE_SIZE);
      const ty0 = Math.floor((state.centerY - h / 2) / TILE_SIZE);
      const ty1 = Math.floor((state.centerY + h / 2) / TILE_SIZE);
      const n = Math.pow(2, state.zoom);
      for (let tx = tx0; tx <= tx1; tx++) {
        for (let ty = ty0; ty <= ty1; ty++) {
          const key = state.zoom + "/" + tx + "/" + ty;
          seen.add(key);
          if (state.tiles.has(key)) continue;
          if (ty < 0 || ty >= n) continue; // outside the world vertically

          const img = new Image();
          img.decoding = "async";
          img.className = "map-tile map-tile-loading";
          img.style.left = (tx * TILE_SIZE + w / 2 - state.centerX) + "px";
          img.style.top = (ty * TILE_SIZE + h / 2 - state.centerY) + "px";
          img.style.width = TILE_SIZE + "px";
          img.style.height = TILE_SIZE + "px";
          img.onload = () => { img.classList.remove("map-tile-loading"); };
          img.onerror = () => {
            img.classList.remove("map-tile-loading");
            img.classList.add("map-tile-ph");
            state.loadErr += 1;
            if (state.loadErr >= 3 && !state.failedOnce) {
              state.failedOnce = true;
              setStatus(state.offline
                ? "OFFLINE — live tile fetch paused; placeholder grid shown"
                : "TILE FETCH FAILED — network error, tile server unreachable, or rate-limited (RELOAD to retry)", "bad");
            }
          };
          img.alt = "";
          layer.appendChild(img);
          const wrappedX = ((tx % n) + n) % n;
          img.src = TILE_URL
            .replace("{z}", String(state.zoom))
            .replace("{x}", String(wrappedX))
            .replace("{y}", String(ty));
          state.tiles.set(key, { img, keepCount: 0 });
          requested += 1;
        }
      }

      // position/hide tiles; drop repeatedly-unseen ones
      state.tiles.forEach((entry, key) => {
        const parts = key.split("/");
        const tz = Number(parts[0]);
        const ttx = Number(parts[1]);
        const tty = Number(parts[2]);
        entry.img.style.left = (ttx * TILE_SIZE + w / 2 - state.centerX) + "px";
        entry.img.style.top = (tty * TILE_SIZE + h / 2 - state.centerY) + "px";
        if (tz !== state.zoom || !seen.has(key)) {
          entry.keepCount += 1;
          if (entry.keepCount > 2) {
            entry.img.remove();
            state.tiles.delete(key);
          } else {
            entry.img.style.display = "none";
          }
        } else {
          entry.keepCount = 0;
          entry.img.style.display = "";
        }
      });

      updateCoords();
      if (!state.failedOnce && !state.offline && requested === 0) {
        setStatus("", null); // all tiles resolved; clear transient status
      }
    }

    function setZoom(next, anchor) {
      next = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, next));
      if (next === state.zoom) return;
      const w = wrap.clientWidth || 600;
      const h = wrap.clientHeight || 400;
      const ax = anchor && Number.isFinite(anchor.x) ? anchor.x : w / 2;
      const ay = anchor && Number.isFinite(anchor.y) ? anchor.y : h / 2;
      // world-space point under the anchor stays put on screen
      const worldX = state.centerX - w / 2 + ax;
      const worldY = state.centerY - h / 2 + ay;
      const ratio = Math.pow(2, next - state.zoom);
      state.centerX = worldX * ratio - ax + w / 2;
      state.centerY = worldY * ratio - ay + h / 2;
      state.zoom = next;
      clearTiles(); // different zoom = different tile pyramid level
      render();
    }

    function recenter() {
      state.zoom = 3;
      state.centerX = lng2px(0, state.zoom);
      state.centerY = lat2py(40, state.zoom);
      clearTiles();
      render();
    }

    // ---- interaction
    function onDown(e) {
      if (e.button !== 0) return;
      state.dragging = true;
      state.lastX = e.clientX;
      state.lastY = e.clientY;
      wrap.classList.add("map-grabbing");
      e.preventDefault();
    }
    function onMove(e) {
      if (!state.dragging) return;
      const dx = e.clientX - state.lastX;
      const dy = e.clientY - state.lastY;
      if (dx === 0 && dy === 0) return;
      state.lastX = e.clientX;
      state.lastY = e.clientY;
      state.centerX -= dx;
      state.centerY -= dy;
      render();
    }
    function onUp() {
      if (!state.dragging) return;
      state.dragging = false;
      wrap.classList.remove("map-grabbing");
    }
    wrap.addEventListener("mousedown", onDown);
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    wrap.addEventListener("wheel", (e) => {
      e.preventDefault();
      const rect = wrap.getBoundingClientRect();
      setZoom(state.zoom + (e.deltaY < 0 ? 1 : -1), {
        x: e.clientX - rect.left,
        y: e.clientY - rect.top,
      });
    }, { passive: false });
    wrap.addEventListener("dblclick", (e) => {
      const rect = wrap.getBoundingClientRect();
      setZoom(state.zoom + 1, { x: e.clientX - rect.left, y: e.clientY - rect.top });
    });
    zIn.addEventListener("click", () => setZoom(state.zoom + 1));
    zOut.addEventListener("click", () => setZoom(state.zoom - 1));

    function onNetChange() {
      const was = state.offline;
      state.offline = !navigator.onLine;
      if (was && !state.offline) {
        // back online: refetch tiles that errored or are missing
        state.failedOnce = false;
        state.loadErr = 0;
        clearTiles();
        setStatus("back online — refetching tiles", "ok");
        render();
      } else if (!was && state.offline) {
        setStatus("OFFLINE — live tile fetch paused; placeholder grid shown", "warn");
      }
    }
    window.addEventListener("online", onNetChange);
    window.addEventListener("offline", onNetChange);

    // first paint on the next frame (panel is measured when visible),
    // and a light ResizeObserver so re-ensized panels reflow tiles.
    setStatus(state.offline ? "OFFLINE — tile fetch paused (offline)" : "loading tiles…", state.offline ? "warn" : "ok");
    let ro = null;
    requestAnimationFrame(() => {
      render();
      if (typeof ResizeObserver !== "undefined") {
        ro = new ResizeObserver(() => { if (!state.dragging) render(); });
        ro.observe(wrap);
      }
    });

    return {
      recenter,
      focus() { render(); },
      reload() {
        state.failedOnce = false;
        state.loadErr = 0;
        state.offline = !navigator.onLine;
        clearTiles();
        setStatus(state.offline ? "OFFLINE — tiles unavailable" : "reloading tiles…", state.offline ? "warn" : "ok");
        render();
      },
      destroy() {
        window.removeEventListener("mousemove", onMove);
        window.removeEventListener("mouseup", onUp);
        window.removeEventListener("online", onNetChange);
        window.removeEventListener("offline", onNetChange);
        if (ro) ro.disconnect();
        clearTiles();
        wrap.remove();
      },
    };
  }

  window.IrisMap = { create };
})();
