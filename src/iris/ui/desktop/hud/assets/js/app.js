/* ============================================================
   IRIS Command Center — application logic.
   All backend access goes through the typed QWebChannel bridge:
   a single `iris.invoke(command, payload)` method plus push signals.
   No external network access. Preferences persist via localStorage.
   ============================================================ */
"use strict";

(function () {
  // ------------------------------------------------------------ helpers
  const $ = (id) => document.getElementById(id);
  const esc = (s) =>
    String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[c]));
  const fmtBytes = (b) => {
    if (b === null || b === undefined || isNaN(b)) return "N/A";
    const units = ["B", "KB", "MB", "GB", "TB"];
    let i = 0, v = Number(b);
    while (v >= 1024 && i < units.length - 1) { v /= 1024; i++; }
    return v.toFixed(i === 0 ? 0 : 1) + " " + units[i];
  };
  const isUnavailable = (v) =>
    v === "N/A" || v === "UNAVAILABLE" || v === "OFFLINE" || v === null || v === undefined;

  const PREFS = {
    reduced: localStorage.getItem("iris.reduced") === "1",
    telem: Number(localStorage.getItem("iris.telem") || 2000),
    sec: Number(localStorage.getItem("iris.sec") || 5000),
  };

  let bridge = null;
  let core = null;
  let mapCtl = null;
  const state = {
    backend: {},
    tools: [],
    chartCpu: [],
    chartMem: [],
    chartNet: [],
    lastNet: null,
    sevFilter: "all",
    paused: false,
    pendingEvents: [],
    events: [],
  };

  // ------------------------------------------------------------ boot

  document.addEventListener("DOMContentLoaded", () => {
    applyPrefs();
    try {
      new QWebChannel(qt.webChannelTransport, (channel) => {
        bridge = channel.objects.iris;
        wireBridge();
        coreInit();
        requestState();
        bridge.invoke("get_diagnostics", "{}");
        bridge.invoke("refresh_security", "{}");
        bridge.invoke("get_history", "{}");
      });
    } catch (err) {
      console.warn("WebChannel unavailable:", err);
      pushSystem("BRIDGE UNAVAILABLE — UI running isolated; backend state cannot update.");
    }
    wireUI();
    clockTick();
    setInterval(clockTick, 1000);
  });

  function clockTick() {
    const el = $("utc-clock");
    if (el) el.textContent = new Date().toISOString().replace("T", " ").slice(0, 19);
  }

  function requestState() {
    if (!bridge) return;
    bridge.invoke("get_state", "{}").then((res) => {
      try {
        const p = JSON.parse(res);
        if (p.ok) {
          state.backend = p.state.backend || {};
          state.tools = p.state.tools || [];
          renderState();
        }
      } catch (e) { console.warn(e); }
    });
  }

  function coreInit() {
    const canvas = $("core-canvas");
    if (!canvas || !window.IrisCore) return;
    core = new window.IrisCore(canvas, (mode, info) => {
      if (mode === "2d") {
        $("fallback-banner").classList.remove("hidden");
        bridge && bridge.invoke("report_webgl", JSON.stringify({ available: false, detail: "2D fallback: " + String(info || "").slice(0, 60) }));
      } else {
        $("fallback-banner").classList.add("hidden");
        bridge && bridge.invoke("report_webgl", JSON.stringify({ available: true, detail: mode + ": " + String(info || "").slice(0, 60) }));
      }
      syncCoreState();
    });
    core.setReducedMotion(PREFS.reduced);
    core.start();
  }

  function syncCoreState() {
    if (!core) return;
    let coreState = "idle";
    const b = state.backend || {};
    if (b.system_status === "OFFLINE") coreState = "disconnected";
    else if (b.action_state === "ERROR") coreState = "error";
    else if (b.action_state === "LISTENING") coreState = "listening";
    else if (b.action_state === "PROCESSING" || b.action_state === "AWAITING CONFIRMATION") coreState = "processing";
    else if (!!window.__irisSpeaking) coreState = "speaking";
    core.setState(coreState);
    $("core-state-label").textContent = coreState.toUpperCase();
  }

  // ------------------------------------------------------------ bridge wiring

  function wireBridge() {
    bridge.pushTelemetry.connect((j) => { try { renderTelemetry(JSON.parse(j)); } catch (e) {} });
    bridge.pushState.connect((j) => {
      try {
        const p = JSON.parse(j);
        state.backend = p.backend || {};
        state.tools = p.tools || [];
        renderState();
      } catch (e) {}
    });
    bridge.pushStatus.connect((j) => {
      try {
        const p = JSON.parse(j);
        $("chat-status").textContent = p.status || "";
        syncCoreState();
      } catch (e) {}
    });
    bridge.pushResponse.connect((j) => {
      try {
        const p = JSON.parse(j);
        pushMessage(p.role === "assistant" ? "assistant" : "system", p.content);
      } catch (e) {}
    });
    bridge.pushError.connect((j) => {
      try {
        const p = JSON.parse(j);
        pushMessage("error", p.content);
        $("chat-error").textContent = "";
        syncCoreState();
      } catch (e) {}
    });
    bridge.pushVoiceEvent.connect((j) => {
      try {
        const p = JSON.parse(j);
        window.__irisSpeaking = p.event === "speak_start";
        syncCoreState();
      } catch (e) {}
    });
    bridge.pushSecurity.connect((j) => {
      try { renderSecurity(JSON.parse(j)); } catch (e) {}
    });
    bridge.pushHistory.connect((j) => {
      try {
        const p = JSON.parse(j);
        state.history = p.turns || [];
      } catch (e) {}
    });
    bridge.pushDiagnostics.connect((j) => {
      try { renderDiagnostics(JSON.parse(j).diagnostics || {}); } catch (e) {}
    });
    bridge.preferencesChanged.connect((telem, sec) => {
      PREFS.telem = telem; PREFS.sec = sec;
    });
  }

  // ------------------------------------------------------------ UI wiring

  function wireUI() {
    // nav
    document.querySelectorAll(".nav-btn[data-view]").forEach((btn) => {
      btn.addEventListener("click", () => switchView(btn.dataset.view));
    });
    // settings toggles mirror
    $("settings-btn").addEventListener("click", () => switchView("settings"));
    $("palette-btn").addEventListener("click", () => openPalette());

    // chat
    $("chat-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      const input = $("chat-input");
      const text = input.value.trim();
      if (!text || !bridge) return;
      pushMessage("user", text);
      input.value = "";
      input.disabled = true;
      $("btn-send").disabled = true;
      const cmd = text.startsWith("/") ? "run_command" : "send_message";
      const payload = cmd === "run_command" ? { command: text } : { text };
      bridge.invoke(cmd, JSON.stringify(payload)).then((res) => {
        let p = {};
        try { p = JSON.parse(res); } catch (e) {}
        if (!p.ok) pushMessage("error", p.error || "backend rejected message");
      }).finally(() => {
        input.disabled = false;
        $("btn-send").disabled = false;
        input.focus();
      });
    });
    $("btn-ptt").addEventListener("click", () => {
      if (!bridge) return;
      // Real backend push-to-talk only works with voice mode ON; enable it
      // first when needed (worker reports availability honestly if STT is
      // missing).
      const ensureVoice = (state.backend.voice || "OFF").toUpperCase() !== "ON"
        ? bridge.invoke("toggle_voice", "{}")
        : Promise.resolve();
      ensureVoice.then(() => bridge.invoke("push_to_talk", "{}"));
    });

    // confirm/cancel
    $("btn-confirm").addEventListener("click", () => runCmd("/confirm"));
    $("btn-cancel").addEventListener("click", () => runCmd("/cancel"));

    // security
    $("btn-export-md").addEventListener("click", () => doExport("md"));
    $("btn-export-json").addEventListener("click", () => doExport("json"));
    $("btn-sec-refresh").addEventListener("click", () => bridge && bridge.invoke("refresh_security", "{}"));
    $("sec-search").addEventListener("input", () => searchFindings());
    document.querySelectorAll(".sev-filter").forEach((b) => {
      b.addEventListener("click", () => {
        document.querySelectorAll(".sev-filter").forEach((x) => x.classList.remove("active"));
        b.classList.add("active");
        state.sevFilter = b.dataset.sev;
        searchFindings();
      });
    });

    // events feed
    $("btn-feed-pause").addEventListener("click", () => {
      state.paused = !state.paused;
      $("btn-feed-pause").textContent = state.paused ? "RESUME" : "PAUSE";
      $("btn-feed-pause").classList.toggle("active", state.paused);
      if (!state.paused) flushEvents();
    });
    $("event-search").addEventListener("input", () => renderEvents());

    // history search
    $("hist-search").addEventListener("input", () => {
      const q = $("hist-search").value;
      if (!bridge) return;
      if (!q) { $("hist-results").innerHTML = ""; return; }
      bridge.invoke("search_history", JSON.stringify({ query: q }))
        .then((res) => {
          try {
            const p = JSON.parse(res);
            renderHistResults(p.turns || []);
          } catch (e) {}
        });
    });

    // prefs
    const t1 = $("pref-telem"), t2 = $("pref-telem2");
    const applyTelem = (ms) => {
      PREFS.telem = ms;
      localStorage.setItem("iris.telem", String(ms));
      if (bridge) bridge.invoke("set_preferences", JSON.stringify({ telemetry_interval_ms: ms, security_interval_ms: PREFS.sec }));
      t1.value = ms; t2.value = ms;
      $("pref-telem-v").textContent = ms + "ms";
      $("pref-telem2-v").textContent = ms + "ms";
    };
    t1.addEventListener("input", () => applyTelem(Number(t1.value)));
    t2.addEventListener("input", () => applyTelem(Number(t2.value)));

    const motion = (v) => {
      PREFS.reduced = v;
      localStorage.setItem("iris.reduced", v ? "1" : "0");
      document.body.classList.toggle("reduced-motion", v);
      $("pref-motion").checked = v;
      $("pref-motion2").checked = v;
      if (core && core.setReducedMotion) core.setReducedMotion(v);
    };
    $("pref-motion").addEventListener("change", (e) => motion(e.target.checked));
    $("pref-motion2").addEventListener("change", (e) => motion(e.target.checked));

    // palette
    $("palette-input").addEventListener("input", () => renderPalette());
    $("palette-input").addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "ArrowUp") {
        e.preventDefault();
        movePaletteSel(e.key === "ArrowDown" ? 1 : -1);
      } else if (e.key === "Enter") {
        e.preventDefault();
        activateSelected();
      } else if (e.key === "Escape") {
        closePalette();
      }
    });
    $("palette-overlay").addEventListener("mousedown", (e) => {
      if (e.target === $("palette-overlay")) closePalette();
    });

    document.addEventListener("keydown", (e) => {
      const mod = e.ctrlKey || e.metaKey;
      if (mod && (e.key === "k" || e.key === "K")) { e.preventDefault(); openPalette(); return; }
      if (!mod) return;
      const views = ["core", "console", "telemetry", "security", "events", "diagnostics", "map"];
      const n = Number(e.key);
      if (n >= 1 && n <= views.length) { e.preventDefault(); switchView(views[n - 1]); }
      if (e.key === "e" || e.key === "E") { e.preventDefault(); doExport("md"); }
      if (e.key === "d" || e.key === "D") { e.preventDefault(); switchView("diagnostics"); bridge && bridge.invoke("get_diagnostics", "{}"); }
    });
  }

  function runCmd(text) {
    if (!bridge) return;
    pushMessage("system", text);
    bridge.invoke("run_command", JSON.stringify({ command: text })).then((res) => {
      try {
        const p = JSON.parse(res);
        if (!p.ok) pushMessage("error", p.error || "command rejected");
      } catch (e) {}
    });
  }

  function applyPrefs() {
    document.body.classList.toggle("reduced-motion", PREFS.reduced);
    $("pref-motion").checked = PREFS.reduced;
    $("pref-motion2").checked = PREFS.reduced;
    $("pref-telem").value = PREFS.telem;
    $("pref-telem2").value = PREFS.telem;
    $("pref-telem-v").textContent = PREFS.telem + "ms";
    $("pref-telem2-v").textContent = PREFS.telem + "ms";
    $("pref-sec").value = PREFS.sec;
    $("pref-sec-v").textContent = PREFS.sec + "ms";
  }

  function switchView(name) {
    document.querySelectorAll(".nav-btn[data-view]").forEach((b) =>
      b.classList.toggle("active", b.dataset.view === name));
    document.querySelectorAll(".view").forEach((v) =>
      v.classList.remove("active"));
    const view = $("view-" + name);
    if (view) view.classList.add("active");
    // Core rAF loop only runs while its view is actually visible.
    if (core && core.setPaused) core.setPaused(name !== "core");
  // The map is lazy: first open initialises tiles (no fetch before that).
      if (name === "map" && !mapCtl && window.IrisMap) {
        mapCtl = window.IrisMap.create($("map-canvas"));
        $("map-recenter").addEventListener("click", () => mapCtl && mapCtl.recenter(), { once: false });
        $("map-reload").addEventListener("click", () => mapCtl && mapCtl.reload(), { once: false });
      } else if (name === "map" && mapCtl) {
        // re-run layout after the panel becomes visible
        mapCtl.focus && mapCtl.focus();
      }
    if (name === "diagnostics" && bridge) bridge.invoke("get_diagnostics", "{}");
  }

  // ------------------------------------------------------------ state pills

  const PILL_STATES = {
    "ONLINE": "st-ok", "READY": "st-ok", "ENABLED": "st-ok", "ACTIVE": "st-ok", "IDLE": "st-ok",
    "OFFLINE": "st-una", "UNAVAILABLE": "st-una", "DISABLED": "st-una", "PASSIVE": "st-warn", "N/A": "st-una",
    "ERROR": "st-err",
    "PROCESSING": "st-busy", "AWAITING CONFIRMATION": "st-warn", "LISTENING": "st-busy",
  };
  const PILL_IDS = {
    system_status: "pill-system",
    ai_status: "pill-ai",
    ai_engine: "pill-aiengine",
    voice: "pill-voice",
    tools: "pill-tools",
    action_state: "pill-action",
    dry_run: "pill-dry",
  };

  function pillFor(value) {
    const v = String(value || "").toUpperCase();
    if (v === "ON") return "st-ok";
    if (v === "OFF") return "st-una";
    let cls = "";
    Object.keys(PILL_STATES).forEach((k) => {
      if ((k === "ON" || k === "OFF") && v === k) cls = PILL_STATES[k];
      else if (k !== "ON" && k !== "OFF" && v.includes(k)) cls = PILL_STATES[k];
    });
    return cls || "";
  }

  function renderState() {
    if (!state.backend) return;
    Object.keys(PILL_IDS).forEach((key) => {
      const el = $(PILL_IDS[key]);
      const valEl = el.querySelector(".pill-value");
      const value = state.backend[key] === undefined ? "N/A" : String(state.backend[key]);
      valEl.textContent = value;
      el.className = "pill " + (el.id === "pill-dry" ? "pill-dry " : "") +
        (PILL_IDS[key] ? pillFor(value) : "");
    });
    // confirm bar
    const awaiting = (state.backend.action_state || "").includes("AWAITING");
    $("confirm-bar").classList.toggle("hidden", !awaiting);
    syncCoreState();
  }

  // ------------------------------------------------------------ chat

  function pushMessage(role, content) {
    const log = $("chat-log");
    if (!log) return;
    if (log.children.length === 0) log.innerHTML = "";
    const div = document.createElement("div");
    div.className = "msg msg-" + role;
    div.innerHTML = "<span class='msg-role'>" + esc(role.toUpperCase()) + "</span>" + esc(content);
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
    // re-enable input if a response arrived
    if (role === "assistant") {
      $("chat-input").disabled = false;
      $("btn-send").disabled = false;
    }
  }

  function pushSystem(text) { pushMessage("system", text); }

  // ------------------------------------------------------------ telemetry

  // Text-content diff cache: only write when the value actually changed.
  const _textCache = new Map();
  function setText(id, value) {
    const el = $(id);
    if (!el) return;
    if (_textCache.get(id) === value) return;
    _textCache.set(id, value);
    el.textContent = value;
  }
  // innerHTML diff cache for tables/lists: DOM untouched on no-change.
  const _htmlCache = new Map();
  function setHtml(id, value) {
    const el = $(id);
    if (!el) return;
    if (_htmlCache.get(id) === value) return;
    _htmlCache.set(id, value);
    el.innerHTML = value;
  }
  function renderTelemetry(tel) {
    if (!tel) return;
    state.lastTel = tel;
    const cpu = tel.cpu || {};
    const mem = tel.memory || {};
    const disk = tel.disk || {};
    const net = tel.network || {};
    const gpu = tel.gpu || {};

    setText("ro-cpu", isUnavailable(cpu.percent) ? "N/A" : cpu.percent + "%");
    setText("ro-mem", isUnavailable(mem.percent) ? "N/A" : mem.percent + "%");
    setText("ro-netdown", isUnavailable(net.down_bytes_sec) ? "N/A" : fmtBytes(net.down_bytes_sec) + "/s");
    setText("ro-netup", isUnavailable(net.up_bytes_sec) ? "N/A" : fmtBytes(net.up_bytes_sec) + "/s");

    setText("t-cpu", isUnavailable(cpu.percent) ? "N/A" : String(cpu.percent));
    setText("t-cpu-sub", "cores: " + (cpu.core_count ?? "N/A") +
      " · freq: " + (cpu.freq_mhz ? cpu.freq_mhz + " MHz" : "UNAVAILABLE"));
    setText("t-mem", isUnavailable(mem.percent) ? "N/A" : String(mem.percent));
    setText("t-mem-sub", "used " + fmtBytes(mem.used_bytes) + " of " + fmtBytes(mem.total_bytes) +
      " (" + fmtBytes(mem.available_bytes) + " free)");
    setText("t-disk", isUnavailable(disk.percent) ? "N/A" : String(disk.percent));
    setText("t-disk-sub", "used " + fmtBytes(disk.used_bytes) + " of " + fmtBytes(disk.total_bytes) +
      " [" + (disk.provenance || "LIVE") + "]");
    setText("t-disk-io", "I/O: " +
      (disk.read_bytes_sec === null || disk.read_bytes_sec === undefined ? "UNAVAILABLE" : "↓ " + fmtBytes(disk.read_bytes_sec) + "/s") +
      " · " +
      (disk.write_bytes_sec === null || disk.write_bytes_sec === undefined ? "UNAVAILABLE" : "↑ " + fmtBytes(disk.write_bytes_sec) + "/s"));

    const dParts = isUnavailable(net.down_bytes_sec) ? ["N/A", ""] : fmtBytes(net.down_bytes_sec).split(" ");
    setText("t-netdown", dParts[0]);
    setText("t-netdown-u", dParts.slice(1).join(" ") + (dParts[1] ? "/s" : ""));
    setText("t-netup", "up: " + (isUnavailable(net.up_bytes_sec) ? "N/A" : fmtBytes(net.up_bytes_sec) + "/s"));

    setText("t-gpu", gpu.available ? String(gpu.util_percent) : "N/A");
    setText("t-gpu-sub", gpu.available
      ? "temp: " + gpu.temperature_c + "°C · VRAM " + fmtBytes(Number(gpu.vram_used_bytes)) + " / " + fmtBytes(Number(gpu.vram_total_bytes)) + " [" + gpu.message + "]"
      : "UNAVAILABLE — " + gpu.message);

    // Sparkline buffers
    pushChart(state.chartCpu, cpu.percent, isUnavailable(cpu.percent));
    pushChart(state.chartMem, mem.percent, isUnavailable(mem.percent));
    pushChart(state.chartNet, isUnavailable(net.down_bytes_sec) ? null : net.down_bytes_sec);
    drawSpark("spark-cpu", state.chartCpu, 0, 100, "%");
    drawSpark("spark-mem", state.chartMem, 0, 100, "%");
    drawSpark("spark-net", state.chartNet, null, null, "B/s");

    const badge = document.querySelector("#view-telemetry .origin-una");
    if (badge) {
      const label = gpu.available ? "LIVE (NVML)" : "UNAVAILABLE";
      if (badge.textContent !== label) {
        badge.textContent = label;
        badge.classList.toggle("origin-una", !gpu.available);
      }
    }
    setText("tele-refreshed", "last update: " + (tel.timestamp || "--") + " [LIVE, psutil · seq " + tel.sequence + "]");

    // processes — single diffed innerHTML write (DOM untouched on no-change)
    const procs = tel.top_processes || [];
    setHtml("proc-body", procs.length
      ? procs.map((p) =>
          "<tr><td class='dim'>" + esc(p.pid) + "</td><td>" + esc(p.name) +
          "</td><td>" + esc(p.cpu_percent) + "</td><td>" + esc(p.memory_percent) + "</td></tr>").join("")
      : "<tr><td colspan='4' class='na'>UNAVAILABLE</td></tr>");

    // interfaces
    const ifs = net.interfaces || [];
    setHtml("iface-list", ifs.length
      ? ifs.map((i) =>
          "<div class='iface-row" + (i.is_up ? "" : " iface-down") + "'>" +
          "<span class='iface-name'>" + esc(i.name) + (i.is_up ? "" : " (DOWN)") + "</span>" +
          "<span class='iface-addr'>" + esc((i.addresses || []).join(", ") || "no addresses") + "</span>" +
          "<span class='dim'>" + (i.speed_mbps === "UNAVAILABLE" ? "speed N/A" : i.speed_mbps + "Mb/s") + "</span></div>").join("")
      : "<div class='iface-row'><span class='dim'>UNAVAILABLE</span></div>");
    syncCoreState();
  }

  function pushChart(buf, value, unavailable) {
    buf.push(unavailable ? null : value);
    while (buf.length > 120) buf.shift();
  }

  function drawSpark(id, data, lo, hi, unit) {
    const c = $(id);
    if (!c) return;
    const ctx = c.getContext("2d");
    const W = c.clientWidth || c.parentElement.clientWidth || 300;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    if (c.width !== W * dpr) { c.width = W * dpr; c.height = 64 * dpr; }
    const H = 64;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, W, H);
    const vals = data.filter((v) => v !== null && v !== undefined && !isNaN(v));
    if (!vals.length) {
      ctx.fillStyle = "rgba(138,151,163,0.8)";
      ctx.font = "9px monospace";
      ctx.fillText("UNAVAILABLE", 8, H / 2);
      return;
    }
    const max = hi !== null ? hi : Math.max(1, ...vals) * 1.15;
    const min = lo !== null ? lo : Math.min(0, ...vals);
    // grid
    ctx.strokeStyle = "rgba(34,211,238,0.09)";
    ctx.lineWidth = 1;
    for (let gy = 0.25; gy < 1; gy += 0.25) {
      ctx.beginPath(); ctx.moveTo(0, H * gy); ctx.lineTo(W, H * gy); ctx.stroke();
    }
    ctx.beginPath();
    ctx.strokeStyle = "#22d3ee";
    ctx.lineWidth = 1.4;
    data.forEach((v, i) => {
      if (v === null || v === undefined || isNaN(v)) return;
      const x = (i / Math.max(1, data.length - 1)) * (W - 4) + 2;
      const y = H - 3 - ((v - min) / Math.max(1e-6, max - min)) * (H - 8);
      if (i === 0 || ctx._moved) { ctx.moveTo(x, y); }
      else ctx.lineTo(x, y);
      ctx._moved = true;
    });
    ctx.stroke();
    ctx._moved = false;
    // last value tag
    const last = vals[vals.length - 1];
    ctx.fillStyle = "rgba(34,211,238,0.85)";
    ctx.font = "9px monospace";
    ctx.fillText(unit === "%" ? last.toFixed(0) + "%" : fmtBytes(last) + "/s", W - 64, 10);
  }

  // ------------------------------------------------------------ security

  function renderSecurity(snapshot) {
    if (!snapshot) return;
    const ts = snapshot.timestamp || "--";
    setText("sec-fresh", "datapoint: " + ts + " [LIVE]");

    // listening sockets
    const items = snapshot.listening || [];
    setHtml("listen-body", items.length
      ? items.map((s) =>
          "<tr><td class='dim'>" + esc(s.protocol) + "</td><td>" + esc(s.address) +
          "</td><td>" + esc(s.port) + "</td><td>" + esc(s.process_name) +
          (!s.pid_readable ? " <span class='dim'>(owner unknown)</span>" : "") + "</td></tr>").join("")
      : "<tr><td colspan='4' class='na'>UNAVAILABLE (global enumeration requires privileges)</td></tr>");

    // interfaces
    const si = snapshot.interfaces || [];
    setHtml("sec-ifaces", si.length
      ? si.map((i) =>
          "<div class='iface-row" + (i.is_up ? "" : " iface-down") + "'>" +
          "<span class='iface-name'>" + esc(i.name) + (i.is_up ? "" : " (DOWN)") + "</span>" +
          "<span class='iface-addr'>" + esc((i.addresses || []).join(", ") || "no addresses") + "</span>" +
          "<span class='dim'>" + esc(i.mac || "") + "</span></div>").join("")
      : "<div class='iface-row'><span class='dim'>UNAVAILABLE</span></div>");

    // connections
    const conns = snapshot.connections || [];
    setHtml("conn-body", conns.length
      ? conns.map((c) =>
          "<tr><td class='dim'>" + esc(c.local_address + ":" + c.local_port) + "</td><td>" +
          (c.remote_address ? esc(c.remote_address + ":" + c.remote_port) : "<span class='dim'>—</span>") +
          "</td><td class='dim'>" + esc(c.status) + "</td><td>" + esc(c.process_name) + "</td></tr>").join("")
      : "<tr><td colspan='4' class='na'>UNAVAILABLE</td></tr>");

    // events
    state.events = snapshot.events || [];
    flushEvents();

    searchFindings();
  }

  function searchFindings() {
    if (!bridge) return;
    const sev = state.sevFilter === "all" ? null : [state.sevFilter];
    const payload = {
      query: $("sec-search").value || "",
      severities: sev,
    };
    bridge.invoke("search_findings", JSON.stringify(payload)).then((res) => {
      try {
        const p = JSON.parse(res);
        renderFindings(p.findings || []);
      } catch (e) {}
    });
  }

  function renderFindings(findings) {
    const box = $("findings-list");
    if (!findings.length) {
      setHtml("findings-list", "<div class='finding-none'>No heuristic indicators raised by the current rule set." +
        "<br><br>IMPORTANT: this does not prove the host is secure. It only means these local, " +
        "host-observable rules found nothing notable. Heuristic findings never assert malice — " +
        "unfamiliar processes, ports and connections are not automatically suspicious.</div>");
      return;
    }
    const html = findings.map((f) => {
      const div = "<div class='finding finding-" + esc(f.severity) + "'>" +
        "<div class='finding-title'><span class='sev-tag " + esc(f.severity) + "'>" + esc(f.severity).toUpperCase() +
        "</span> " + esc(f.title) + "</div>" +
        "<div class='finding-meta'><span>" + esc(f.finding_id) + "</span><span>" + esc(f.timestamp) +
        "</span><span>confidence: " + esc(f.confidence).toUpperCase() + "</span><span>HEURISTIC</span><span>status: " +
        esc(f.status) + "</span></div>" +
        "<div class='finding-desc'>" + esc(f.description) + "</div>" +
        "<div class='finding-ev'>EVIDENCE — " +
        (f.evidence || []).map((e) => esc("[" + e.source + "] " + e.detail)).join(" · ") + "</div>" +
        "<div class='finding-why'>WHY: " + esc(f.explanation) + "</div></div>";
      return div;
    }).join("");
    setHtml("findings-list", html);
  }

  function doExport(fmt) {
    if (!bridge) return;
    bridge.invoke("request_export_path", JSON.stringify({ format: fmt })).then((res) => {
      try {
        const p = JSON.parse(res);
        if (!p.ok || p.cancelled || !p.path) return;
        bridge.invoke("export_report", JSON.stringify({ path: p.path, format: fmt })).then((r2) => {
          try {
            const p2 = JSON.parse(r2);
            if (!p2.ok) pushMessage("error", "Export failed: " + (p2.error || "unknown"));
          } catch (e) {}
        });
      } catch (e) {}
    });
  }

  // ------------------------------------------------------------ events feed

  function flushEvents() {
    if (state.paused) {
      // buffer incoming events while paused
      return;
    }
    renderEvents();
  }

  function renderEvents() {
    const feed = $("event-feed");
    if (!feed) return;
    const q = ($("event-search").value || "").toLowerCase();
    const shown = state.events.filter((e) =>
      !q || (e.detail + " " + e.kind).toLowerCase().includes(q));
    feed.innerText = "";
    if (!shown.length) {
      feed.setAttribute("data-empty", q
        ? "No matching events."
        : "Events appear when the security poller observes listener changes between two polls. Timestamps are UTC.");
    } else {
      feed.removeAttribute("data-empty");
      shown.slice(-200).forEach((e) => {
        const row = document.createElement("div");
        row.className = "event-row";
        row.innerHTML =
          "<span class='event-ts'>" + esc(e.timestamp) + "</span>" +
          "<span class='event-kind'>" + esc(e.kind) + "</span>" +
          "<span class='event-detail'>" + esc(e.detail) + "</span>";
        feed.appendChild(row);
      });
      feed.scrollTop = feed.scrollHeight;
    }
  }

  // ------------------------------------------------------------ diagnostics

  function renderDiagnostics(d) {
    const grid = $("diag-grid");
    if (!grid) return;
    const items = [
      ["BACKEND", d.backend, d.backend === "ONLINE"],
      ["AI PROVIDER", d.provider_configured ? d.provider + " / " + d.model : "UNCONFIGURED", !!d.provider_configured],
      ["TOOLS", d.tool_count === "N/A" ? "N/A" : d.tool_count + " REGISTERED", d.tool_count !== "N/A"],
      ["VOICE STT", d.stt_available ? "AVAILABLE (SpeechRecognition)" : "UNAVAILABLE (pip install SpeechRecognition)", !!d.stt_available],
      ["VOICE TTS", d.tts_available ? "AVAILABLE (pyttsx3)" : "UNAVAILABLE (pip install pyttsx3)", !!d.tts_available],
      ["TELEMETRY", "psutil (LIVE)", !!d.psutil],
      ["WEBENGINE", d.webengine ? "AVAILABLE" : "UNAVAILABLE", !!d.webengine],
      ["WEBGL CORE", String(d.webgl || "UNKNOWN").toUpperCase(), String(d.webgl || "").startsWith("AVAILABLE")],
      ["QT", d.qt_version || "UNAVAILABLE", !!d.qt_version],
      ["VOICE MODE", d.voice_mode || "OFF", (d.voice_mode || "").toUpperCase() === "ON"],
    ];
    if (d.gpu_note) items.push(["GPU NOTE", d.gpu_note, false]);
    if (Array.isArray(d.pending_steps) && d.pending_steps.length) {
      items.push(["PENDING CONFIRMATION", d.pending_steps.join(" | "), false]);
    }
    grid.innerText = "";
    grid.removeAttribute("data-empty");
    items.forEach(([label, value, ok]) => {
      const el = document.createElement("div");
      el.className = "diag-item " + (ok ? "diag-ok" : "diag-bad");
      el.innerHTML = "<div class='diag-label'>" + esc(label) + "</div><div class='diag-value'>" + esc(value) + "</div>";
      grid.appendChild(el);
    });
  }

  function renderHistResults(turns) {
    const box = $("hist-results");
    box.innerText = "";
    if (!turns.length) {
      box.setAttribute("data-empty", "No matching session history.");
    } else {
      box.removeAttribute("data-empty");
      turns.forEach((t) => {
        const div = document.createElement("div");
        div.className = "hist-result";
        div.innerHTML = "<span class='role'>" + esc(t.role.toUpperCase()) + "</span><br>" + esc(t.content);
        box.appendChild(div);
      });
    }
  }

  // ------------------------------------------------------------ palette

  const PALETTE = [
    { label: "Switch: AI Core", hint: "Ctrl+1", run: () => switchView("core") },
    { label: "Switch: Console", hint: "Ctrl+2", run: () => switchView("console") },
    { label: "Switch: Telemetry", hint: "Ctrl+3", run: () => switchView("telemetry") },
    { label: "Switch: Security", hint: "Ctrl+4", run: () => switchView("security") },
    { label: "Switch: Events", hint: "Ctrl+5", run: () => switchView("events") },
    { label: "Switch: Diagnostics", hint: "Ctrl+6", run: () => switchView("diagnostics") },
    { label: "Switch: Geo Map", hint: "Ctrl+7", run: () => switchView("map") },
    { label: "Toggle voice mode", hint: "real backend", run: () => bridge && bridge.invoke("toggle_voice", "{}") },
    { label: "Push to talk", hint: "mic", run: () => bridge && bridge.invoke("push_to_talk", "{}") },
    { label: "Toggle dry-run mode", hint: "/dry-run", run: () => runCmd("/dry-run") },
    { label: "Enable tool orchestration", hint: "/enable-tools", run: () => runCmd("/enable-tools") },
    { label: "Disable tool orchestration", hint: "/disable-tools", run: () => runCmd("/disable-tools") },
    { label: "Tool orchestration status", hint: "/tool-status", run: () => runCmd("/tool-status") },
    { label: "List AI tools", hint: "/tools", run: () => runCmd("/tools") },
    { label: "IRIS help", hint: "/help", run: () => runCmd("/help") },
    { label: "Confirm pending action", hint: "/confirm", run: () => runCmd("/confirm") },
    { label: "Cancel pending action", hint: "/cancel", run: () => runCmd("/cancel") },
    { label: "Refresh telemetry now", hint: "LIVE", run: () => bridge && bridge.invoke("get_telemetry_snapshot", "{}") },
    { label: "Refresh security scan", hint: "read-only", run: () => bridge && bridge.invoke("refresh_security", "{}") },
    { label: "Export security report (MD)", hint: "Ctrl+E", run: () => doExport("md") },
    { label: "Export security report (JSON)", hint: "", run: () => doExport("json") },
    { label: "Toggle reduce motion", hint: "pref", run: () => { const x = !PREFS.reduced; $("pref-motion2").checked = x; $("pref-motion2").dispatchEvent(new Event("change")); } },
  ];

  let paletteIndex = 0;
  let paletteFiltered = PALETTE;

  function openPalette() {
    $("palette-overlay").classList.remove("hidden");
    $("palette-input").value = "";
    renderPalette();
    $("palette-input").focus();
  }
  function closePalette() { $("palette-overlay").classList.add("hidden"); }

  function renderPalette() {
    const q = $("palette-input").value.toLowerCase().trim();
    paletteFiltered = PALETTE.filter((c) => c.label.toLowerCase().includes(q));
    paletteIndex = 0;
    const list = $("palette-list");
    list.innerHTML = "";
    paletteFiltered.forEach((c, i) => {
      const el = document.createElement("div");
      el.className = "pal-item" + (i === paletteIndex ? " sel" : "");
      el.innerHTML = "<span>" + esc(c.label) + "</span><span class='pal-hint'>" + esc(c.hint) + "</span>";
      el.addEventListener("click", () => { closePalette(); c.run(); });
      list.appendChild(el);
    });
  }
  function movePaletteSel(d) {
    paletteIndex = Math.max(0, Math.min(paletteFiltered.length - 1, paletteIndex + d));
    document.querySelectorAll(".pal-item").forEach((el, i) => {
      el.classList.toggle("sel", i === paletteIndex);
    });
  }
  function activateSelected() {
    const c = paletteFiltered[paletteIndex];
    if (c) { closePalette(); c.run(); }
  }
})();
