/* ============================================================
   IRIS 3D Core — hand-written WebGL2 (with WebGL1 fallback path),
   zero dependencies, fully local.

   Genuine 3D render pipeline:
     - real perspective projection + view matrix
     - per-vertex normal lighting (Lambert + specular, limb darkening)
     - procedurally detailed surface (grid lines + noise bands + sweep)
     - additive atmospheric rim shell
     - orbital particle field occluded by the globe (depth-tested)
     - drag-rotate with inertia, auto-spin while idle

   Performance model:
     - every matrix is preallocated; only one rotation is rewritten
       per frame (no per-frame Float32Array churn)
     - DPR capped at 1.5; adaptive "reduced effects" mode drops DPR to
       1.0, halves particle draw count and skips the rim shell when the
       rolling average frame time exceeds ~26 ms on 90 frames
     - rendering fully stops (rAF cancelled) when the page is hidden or
       the core view is inactive, and resumes on demand
     - fallback: if WebGL2/WebGL1 cannot initialise, a restrained 2D
       canvas ring is drawn and the failure is surfaced via onModeChange
       ("2d") — never presented as true 3D.
   ============================================================ */
"use strict";

(function () {
  const STATES = {
    idle:         { speed: 0.6,  glow: 1.0, hue: 0.00,  jitter: 0.0,  points: 1.0 },
    processing:   { speed: 3.2,  glow: 1.8, hue: 0.55,  jitter: 0.5,  points: 1.6 },
    listening:    { speed: 1.6,  glow: 1.4, hue: 0.15,  jitter: 0.15, points: 1.2 },
    speaking:     { speed: 1.2,  glow: 1.6,  hue: 0.12,  jitter: 0.9,  points: 0.9 },
    error:        { speed: 1.0,  glow: 1.1, hue: -0.18, jitter: 0.25, points: 0.7 },
    disconnected: { speed: 0.15, glow: 0.4, hue: -0.5,  jitter: 0.0,  points: 0.5 },
  };

  function IrisCore(canvas, onModeChange) {
    this.canvas = canvas;
    this.onModeChange = onModeChange || function () {};
    this.stateName = "disconnected";
    this.target = STATES.disconnected;
    this.current = Object.assign({}, STATES.disconnected);
    this.mode = null;              // null | "webgl2" | "webgl1" | "2d"
    this.quality = "high";         // "high" | "reduced"
    this.fps = 0;                  // rolling display estimate
    this._rot = 0;                 // Y rotation accumulated
    this._dragVel = 0;             // pointer inertia (rad/s)
    this._dragging = false;
    this._lastPointerX = 0;
    this._last_t = 0;
    this._raf = 0;
    this._running = false;
    this._paused = false;          // set by app (view switch)
    this._hidden = document.hidden; // page hidden/minimized
    this._frameAvg = 16;           // ms, rolling
    this._slowLimit = 26;
    this._slowTicks = 0;
    this._reducedReported = false;

    // Preallocated matrices — never allocated per frame.
    this._mProj = new Float32Array(16);
    this._mView = new Float32Array(16);
    this._mModel = new Float32Array(16);
    this._mTilt = new Float32Array(16);
    this._mSpin = new Float32Array(16);

    this._bindPointer();
    document.addEventListener("visibilitychange", () => {
      this._hidden = document.hidden;
      this._updateRunning();
    });
  }

  IrisCore.prototype.setState = function (name) {
    if (!STATES[name]) name = "idle";
    if (name === this.stateName) return;
    this.stateName = name;
    this.target = STATES[name];
  };

  /* ------------------------------------------------ lifecycle */

  IrisCore.prototype.start = function () {
    if (this._running) return true;
    if (!this.mode) {
      // Try WebGL first; only fall back to 2D if it cannot initialise.
      if (this._initGL()) {
        // fall through to a first draw below (mode set by _initGL)
      } else if (!this._init2D()) {
        this.mode = null;
        this._running = false;
        // Surface failure explicitly; app shows the 2D-fallback banner
        // and reports UNAVAILABLE (not a silent blank canvas).
        this.onModeChange(null, this._rendererInfo || "no rendering backend");
        return false;
      }
    }
    this._running = true;
    this._updateRunning();
    this.onModeChange(this.mode, this._rendererInfo);
    // Draw one frame synchronously so the globe is visible immediately
    // after start(), rather than waiting for the first rAF tick (rAF can
    // be delayed when the window is offscreen or just restored).
    try {
      this._frame(performance.now());
    } catch (e) {
      console.warn("IRIS core first-frame failed:", e);
    }
    return true;
  };

  IrisCore.prototype.stop = function () {
    this._running = false;
    if (this._raf) { cancelAnimationFrame(this._raf); this._raf = 0; }
  };

  /** Pause/resume driven from app.js (view switches). */
  IrisCore.prototype.setPaused = function (paused) {
    this._paused = !!paused;
    this._updateRunning();
  };

  IrisCore.prototype.setReducedMotion = function (reduced) {
    this._reducedMotion = !!reduced;
    if (reduced) this.quality = "reduced";
    this._updateRunning();
  };

  IrisCore.prototype._updateRunning = function () {
    const wantRun = this._running && !this._paused && !this._hidden;
    if (wantRun && !this._raf) {
      this._last_t = 0;
      const self = this;
      function frame(t) {
        if (!self._running || self._paused || self._hidden) { self._raf = 0; return; }
        self._frame(t);
        self._raf = requestAnimationFrame(frame);
      }
      this._raf = requestAnimationFrame(frame);
    } else if (!wantRun && this._raf) {
      cancelAnimationFrame(this._raf);
      this._raf = 0;
    }
  };

  /* ------------------------------------------------ init GL */

  IrisCore.prototype._initGL = function () {
    var gl = null, glver = "";
    try {
      gl = this.canvas.getContext("webgl2", { antialias: true, alpha: true, powerPreference: "high-performance" });
      glver = "webgl2";
      if (!gl) {
        gl = this.canvas.getContext("webgl", { antialias: true, alpha: true }) ||
             this.canvas.getContext("experimental-webgl");
        glver = "webgl1";
      }
    } catch (e) { gl = null; }
    if (!gl) {
      this._rendererInfo = "WEBGL UNAVAILABLE (2D fallback active)";
      return false;
    }

    this.gl = gl;
    this.glver = glver;

    var is3 = glver === "webgl2";
    var glsl = is3 ? "#version 300 es\n" : "";
    var a = is3 ? "in " : "attribute ";
    var v = is3 ? "out " : "varying ";
    var vf = is3 ? "in " : "varying ";
    var f = is3 ? "out vec4 fragColor;" : "";
    var fAssign = is3 ? "fragColor = " : "gl_FragColor = ";
    var fragPre = is3 ? "#version 300 es\nprecision highp float;\n" : "precision mediump float;\n";

    // ---------- lit globe: Lambert + specular + procedural surface ----
    this.coreProg = this._program(
      glsl + `
      ${a} vec3 aPos;
      ${a} vec3 aNorm;
      uniform mat4 uProj, uView, uModel;
      uniform mat3 uNormMat;
      uniform float uJitter;
      ${v} vec3 vN;
      ${v} vec3 vP;
      void main(){
        vec3 p = aPos * (1.0 + uJitter * 0.02 * sin(aPos.y * 18.0));
        vP = p;
        vN = uNormMat * aNorm;
        gl_Position = uProj * uView * uModel * vec4(p, 1.0);
      }`,
      fragPre + `
      ${vf} vec3 vN;
      ${vf} vec3 vP;
      uniform float uGlow, uScan, uTime;
      ${f}
      void main(){
        vec3 N = normalize(vN);
        vec3 L = normalize(vec3(-0.45, 0.55, 0.7));
        vec3 V = normalize(vec3(0.0, 0.12, 1.0));
        float diff = max(dot(N, L), 0.0);
        float spec = pow(max(dot(reflect(-L, N), V), 0.0), 26.0);
        float limb = 1.0 - 0.55 * pow(1.0 - max(dot(N, V), 0.0), 1.6);

        // cheap procedural detail: lat/long tech grid + breathing bands
        float lat = vP.y;
        float lon = atan(vP.z, vP.x);
        float grid = 0.0;
        grid += smoothstep(0.96, 1.0, abs(sin(lat * 14.0))) * 0.28;
        grid += smoothstep(0.965, 1.0, abs(sin(lon * 18.0))) * 0.22;
        float bands = 0.5 + 0.5 * sin(lon * 3.0 + vP.y * 5.0 + uTime * 0.35);
        float n = sin(vP.x*9.0 + uScan)*sin(vP.y*7.0 - uScan)*sin(vP.z*8.0);

        vec3 deep   = vec3(0.03, 0.09, 0.13);
        vec3 lit    = vec3(0.10, 0.42, 0.52);
        vec3 accent = vec3(0.13, 0.82, 0.94);
        vec3 base = mix(deep, lit, diff * limb);
        base += accent * grid * (0.25 + 0.35 * diff);
        base += vec3(0.05, 0.35, 0.10) * bands * 0.14;
        float fres = pow(1.0 - max(dot(N, V), 0.0), 2.6);
        vec3 col = base * (0.85 + 0.30 * uGlow);
        col += vec3(0.0, 0.55, 0.75) * fres * (0.55 + 0.35 * uGlow);
        col += accent * spec * 0.6;
        col += vec3(0.0, 0.22, 0.28) * abs(n) * 0.22;
        float alpha = 1.0;
        ${fAssign}vec4(col, alpha);
      }`
    );
    if (!this.coreProg) { this._initFailure("shader compile failed"); return false; }

    // ---------- additive atmosphere rim shell ------------------------
    this.rimProg = this._program(
      glsl + `
      ${a} vec3 aPos;
      uniform mat4 uProj, uView, uModel;
      ${v} vec3 vP;
      void main(){
        vP = aPos;
        gl_Position = uProj * uView * uModel * vec4(aPos * 1.045, 1.0);
      }`,
      fragPre + `
      ${vf} vec3 vP;
      uniform float uGlow;
      ${f}
      void main(){
        vec3 N = normalize(vP);
        vec3 V = normalize(vec3(0.0, 0.12, 1.0));
        float fres = pow(1.0 - abs(dot(N, V)), 3.2);
        float glow = fres * (0.5 + 0.5 * uGlow);
        vec3 rim = mix(vec3(0.05, 0.35, 0.45), vec3(0.30, 0.85, 0.95), glow);
        ${fAssign}vec4(rim, glow * 0.9);
      }`
    );
    if (!this.rimProg) { this._initFailure("rim shader compile failed"); return false; }

    // ---------- particles (additive, depth-occluded) ------------------
    this.partProg = this._program(
      glsl + `
      ${a} vec3 aPos;
      ${a} float aSeed;
      uniform mat4 uProj, uView, uModel;
      uniform float uTime, uSpread, uSize;
      ${v} float vA;
      void main(){
        float s = aSeed * 6.28318;
        vec3 p = aPos;
        float r = length(p);
        p.y += 0.12 * sin(uTime * 0.9 + s);
        r = r * (1.0 + 0.04 * sin(uTime * 1.4 + s * 3.0)) * uSpread;
        p = p / length(p) * r;
        gl_Position = uProj * uView * uModel * vec4(p, 1.0);
        gl_PointSize = uSize * (0.6 + 0.6 * fract(aSeed * 7.0));
        vA = 0.35 + 0.45 * fract(aSeed * 13.0);
      }`,
      fragPre + `
      ${vf} float vA;
      uniform float uGlow;
      uniform vec3 uTint;
      ${f}
      void main(){
        vec2 d = gl_PointCoord - vec2(0.5);
        float m = smoothstep(0.5, 0.0, length(d));
        ${fAssign}vec4(uTint, vA * m * uGlow);
      }`
    );
    if (!this.partProg) { this._initFailure("particle shader compile failed"); return false; }

    // ---------- static geometry (built once, never re-sent) -----------
    var sphere = this._sphereGeometry(1.0, 44);
    var verts = new Float32Array(sphere.length);
    verts.set(sphere);
    this.coreCount = sphere.positionCount;
    this.coreBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.coreBuf);
    gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);

    var shell = this._sphereGeometry(1.0, 28);
    this.shellCount = shell.positionCount;
    this.shellBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.shellBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(shell), gl.STATIC_DRAW);

    var N = 1400;
    var parts = new Float32Array(N * 4);
    for (var i = 0; i < N; i++) {
      var sh = i % 3 === 0 ? 1.25 : 1.55;
      var u = Math.random(), w = Math.random();
      var th = 2 * Math.PI * u, ph = Math.acos(2 * w - 1);
      parts[i * 4]     = sh * Math.sin(ph) * Math.cos(th);
      parts[i * 4 + 1] = sh * Math.cos(ph);
      parts[i * 4 + 2] = sh * Math.sin(ph) * Math.sin(th);
      parts[i * 4 + 3] = Math.random();
    }
    this.partBuf = gl.createBuffer();
    this.partCount = N;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.partBuf);
    gl.bufferData(gl.ARRAY_BUFFER, parts, gl.STATIC_DRAW);

    gl.enable(gl.BLEND);
    // NOTE: back-face culling intentionally DISABLED — the sphere's
    // triangle winding is assumed-front but not guaranteed CCW-outward,
    // and with depth testing + an opaque core surface the back faces are
    // occluded anyway. Culling would silently cull the visible surface
    // if winding were wrong; rendering both faces cannot produce a
    // hollow globe.
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.disable(gl.CULL_FACE);

    // Fixed static viewspace-dependent pieces, built once.
    this._tilt = 23.4 * Math.PI / 180.0;
    this._computeProj();

    var dbg = gl.getExtension("WEBGL_debug_renderer_info");
    this._rendererInfo = dbg
      ? String(gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL))
      : gl.getParameter(gl.RENDERER) || "unidentified renderer";

    this.mode = glver;
    if (/swiftshader|llvmpipe|software|basic render/i.test(this._rendererInfo)) {
      this._rendererInfo = "software renderer: " + this._rendererInfo;
    }
    return true;
  };

  IrisCore.prototype._initFailure = function (why) {
    this.gl = null;
    this._rendererInfo = "WEBGL UNAVAILABLE — " + why;
    this.mode = null;
  };

  IrisCore.prototype._program = function (vsSrc, fsSrc) {
    var gl = this.gl;
    function compile(type, src) {
      var sh = gl.createShader(type);
      gl.shaderSource(sh, src);
      gl.compileShader(sh);
      if (!gl.getShaderParameter(sh, gl.COMPILE_STATUS)) {
        console.warn("IRIS core shader:", gl.getShaderInfoLog(sh));
        return null;
      }
      return sh;
    }
    var vs = compile(gl.VERTEX_SHADER, vsSrc);
    var fs = compile(gl.FRAGMENT_SHADER, fsSrc);
    if (!vs || !fs) return null;
    var prog = gl.createProgram();
    gl.attachShader(prog, vs);
    gl.attachShader(prog, fs);
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
      console.warn("IRIS core link:", gl.getProgramInfoLog(prog));
      return null;
    }
    var uniforms = {};
    var attrs = {};
    var nU = gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS);
    for (var i = 0; i < nU; i++) {
      var info = gl.getActiveUniform(prog, i);
      uniforms[info.name.replace("[0]", "")] = gl.getUniformLocation(prog, info.name);
    }
    var nA = gl.getProgramParameter(prog, gl.ACTIVE_ATTRIBUTES);
    for (var j = 0; j < nA; j++) {
      var aInfo = gl.getActiveAttrib(prog, j);
      attrs[aInfo.name] = gl.getAttribLocation(prog, aInfo.name);
    }
    return { prog: prog, uniforms: uniforms, attrs: attrs };
  };

  /** Interleaved sphere: pos(3) + normal(3). Returns {array, positionCount}. */
  IrisCore.prototype._sphereGeometry = function (radius, seg) {
    var rows = Math.round(seg * 0.7);
    var verts = [];
    var count = 0;
    function push(th, ph) {
      var x = radius * Math.sin(th) * Math.cos(ph),
          y = radius * Math.cos(th),
          z = radius * Math.sin(th) * Math.sin(ph);
      verts.push(x, y, z, x / radius, y / radius, z / radius);
      count++;
    }
    // Quad grid over (th, ph). Winding is not relied upon for correctness:
    // the renderer keeps back-face culling DISABLED (see _initGL), so both
    // orientations render; depth testing resolves front/back visibility.
    for (var y = 0; y < rows; y++) {
      var th0 = (y / rows) * Math.PI, th1 = ((y + 1) / rows) * Math.PI;
      for (var x = 0; x < seg; x++) {
        var ph0 = (x / seg) * 2 * Math.PI, ph1 = ((x + 1) / seg) * 2 * Math.PI;
        push(th0, ph0); push(th1, ph1); push(th0, ph1);
        push(th0, ph0); push(th1, ph0); push(th1, ph1);
      }
    }
    return { array: verts, positionCount: count };
  };

  /* ------------------------------------------------ 2D fallback */

  IrisCore.prototype._init2D = function () {
    this.ctx2d = this.canvas.getContext("2d");
    if (!this.ctx2d) return false;
    this.mode = "2d";
    this.quality = "high";
    this._rendererInfo = "2D canvas fallback (WEBGL UNAVAILABLE — not true 3D)";
    return true;
  };

  IrisCore.prototype._draw2d = function (t) {
    // Sync the backing buffer to the CSS size once here — the WebGL path
    // never runs in this mode, so without this the fallback ring draws
    // at the stale 300x150 default inside a much larger canvas box.
    var cssW = this.canvas.clientWidth, cssH = this.canvas.clientHeight;
    if (cssW > 0 && cssH > 0) {
      var dpr = Math.min(1.5, this._reducedMotion ? 1 : (window.devicePixelRatio || 1));
      var bw = Math.floor(cssW * dpr), bh = Math.floor(cssH * dpr);
      if (this.canvas.width !== bw || this.canvas.height !== bh) {
        this.canvas.width = bw;
        this.canvas.height = bh;
      }
    }
    var ctx = this.ctx2d;
    var W = this.canvas.width, H = this.canvas.height;
    var d = (W / Math.max(1, cssW)) || 1; // draw in device px (as before)
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, W, H);
    var cx = W / 2, cy = H / 2;
    var R = Math.min(W, H) * 0.22;
    var s = this.current;
    var hue = 185 + s.hue * 60;
    ctx.lineWidth = 1.5;
    for (var i = 0; i < 3; i++) {
      var r = R * (1 + i * 0.35) * (1 + 0.02 * Math.sin(t / 700 + i));
      ctx.beginPath();
      ctx.strokeStyle = "hsla(" + hue + ",80%,60%," + (0.5 - i * 0.13) + ")";
      ctx.ellipse(cx, cy, r, r * 0.96, t / (3000 + i * 900) * s.speed, 0, 2 * Math.PI);
      ctx.stroke();
    }
    ctx.beginPath();
    ctx.fillStyle = "hsla(" + hue + ",80%,65%," + 0.25 * s.glow + ")";
    ctx.arc(cx, cy, R * 0.4, 0, 2 * Math.PI);
    ctx.fill();
  };

  /* ------------------------------------------------ interaction */

  IrisCore.prototype._bindPointer = function () {
    var self = this;
    var el = this.canvas;
    el.style.touchAction = "none";
    el.addEventListener("pointerdown", function (e) {
      self._dragging = true;
      self._lastPointerX = e.clientX;
      self._dragVel = 0;
      try { el.setPointerCapture(e.pointerId); } catch (err) {}
    });
    el.addEventListener("pointermove", function (e) {
      if (!self._dragging) return;
      var dx = e.clientX - self._lastPointerX;
      self._lastPointerX = e.clientX;
      self._rot += dx * 0.008;
      self._dragVel = dx * 0.008 * 60; // rad/s estimate at pointer event rate
    });
    function end() { self._dragging = false; }
    el.addEventListener("pointerup", end);
    el.addEventListener("pointercancel", end);
    el.addEventListener("pointerleave", end);
  };

  /* ------------------------------------------------ matrices */

  IrisCore.prototype._computeProj = function () {
    var W = this.canvas.clientWidth, H = this.canvas.clientHeight || 1;
    var aspect = Math.max(0.1, W / Math.max(1, H));
    var f = 1 / Math.tan(38 * Math.PI / 360);
    var near = 0.1, far = 40, nf = 1 / (near - far);
    var m = this._mProj;
    m[0] = f / aspect; m[1] = 0; m[2] = 0; m[3] = 0;
    m[4] = 0; m[5] = f; m[6] = 0; m[7] = 0;
    m[8] = 0; m[9] = 0; m[10] = (far + near) * nf; m[11] = -1;
    m[12] = 0; m[13] = 0; m[14] = 2 * far * near * nf; m[15] = 0;
  };

  // Static view matrix (eye at 0,0.4,4.6 looking at origin), built once.
  IrisCore.prototype._viewCache = new Float32Array([
    1, 0, 0, 0,
    0, 0.99483, 0.10163, 0,
    0, -0.10163, 0.99483, 0,
    0, -0.43907, -4.58019, 1,
  ]);

  IrisCore.prototype._tiltMat = function () {
    var c = Math.cos(this._tilt), s = Math.sin(this._tilt);
    var m = this._mTilt;
    m[0] = 1; m[1] = 0; m[2] = 0; m[3] = 0;
    m[4] = 0; m[5] = c; m[6] = s; m[7] = 0;
    m[8] = 0; m[9] = -s; m[10] = c; m[11] = 0;
    m[12] = 0; m[13] = 0; m[14] = 0; m[15] = 1;
  };

  IrisCore.prototype._spinMat = function (a) {
    var c = Math.cos(a), s = Math.sin(a);
    var m = this._mSpin;
    m[0] = c; m[1] = 0; m[2] = -s; m[3] = 0;
    m[4] = 0; m[5] = 1; m[6] = 0; m[7] = 0;
    m[8] = s; m[9] = 0; m[10] = c; m[11] = 0;
    m[12] = 0; m[13] = 0; m[14] = 0; m[15] = 1;
  };

  // model = tilt * spin (column-major, column-major stored)
  IrisCore.prototype._mul4 = function (out, a, b) {
    for (var col = 0; col < 4; col++) {
      var b0 = b[col * 4], b1 = b[col * 4 + 1], b2 = b[col * 4 + 2], b3 = b[col * 4 + 3];
      out[col * 4]     = a[0] * b0 + a[4] * b1 + a[8] * b2 + a[12] * b3;
      out[col * 4 + 1] = a[1] * b0 + a[5] * b1 + a[9] * b2 + a[13] * b3;
      out[col * 4 + 2] = a[2] * b0 + a[6] * b1 + a[10] * b2 + a[14] * b3;
      out[col * 4 + 3] = a[3] * b0 + a[7] * b1 + a[11] * b2 + a[15] * b3;
    }
  };

  // Fixed 3x3 upper-left of identity-based tilt*spin model for normals.
  IrisCore.prototype._normMat = function (out, model) {
    // uniform scale => rotation part works directly for normals
    out[0] = model[0]; out[1] = model[1]; out[2] = model[2];
    out[3] = model[4]; out[4] = model[5]; out[5] = model[6];
    out[6] = model[8]; out[7] = model[9]; out[8] = model[10];
  };

  /* ------------------------------------------------ render loop */

  IrisCore.prototype._frame = function (tms) {
    var t = tms / 1000;
    var dt = Math.min(0.1, (this._last_t ? (tms - this._last_t) / 1000 : 0.016));
    this._last_t = tms;

    // rolling frame-time monitor -> adaptive quality
    var ft = dt * 1000;
    this._frameAvg += (ft - this._frameAvg) * 0.05;
    this.fps = Math.round(1000 / Math.max(1, this._frameAvg));
    if (this.mode !== "2d" && this.quality !== "reduced") {
      if (this._frameAvg > this._slowLimit) {
        if (++this._slowTicks >= 90) {
          this.quality = "reduced";
          this._dropEffects();
          this.onModeChange(this.mode,
            "REDUCED EFFECTS (avg frame " + this._frameAvg.toFixed(0) + "ms)");
          this._reducedReported = true;
        }
      } else {
        this._slowTicks = Math.max(0, this._slowTicks - 2);
      }
    }

    // ease current towards target state
    var s = this.current, tgt = this.target;
    var k = 1 - Math.pow(0.002, dt);
    s.speed += (tgt.speed - s.speed) * k;
    s.glow += (tgt.glow - s.glow) * k;
    s.hue += (tgt.hue - s.hue) * k;
    s.jitter += (tgt.jitter - s.jitter) * k;
    s.points += (tgt.points - s.points) * k;

    if (this.mode === "2d") { this._draw2d(tms); return; }

    var gl = this.gl;

    // size sync only when actually changed (clientWidth read is cheap
    // enough once per frame, resize writes are rare)
    var W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    var dprCap = (this.quality === "reduced" || this._reducedMotion)
      ? 1.0 : Math.min(1.5, window.devicePixelRatio || 1);
    var cw = Math.floor(W * dprCap), ch = Math.floor(H * dprCap);
    if (W !== 0 && (this.canvas.width !== cw || this.canvas.height !== ch)) {
      this.canvas.width = cw;
      this.canvas.height = ch;
      this._computeProj();
    }
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0.0, 0.0, 0.0, 0.0);
    gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);

    // rotation: auto-spin or drag inertia
    if (!this._dragging) {
      if (Math.abs(this._dragVel) > 0.02) {
        this._rot += this._dragVel * dt;
        this._dragVel *= Math.pow(0.02, dt); // exponential decay
      } else {
        this._dragVel = 0;
        var spin = (this._reducedMotion ? 0.1 : 0.25) * s.speed;
        this._rot += dt * spin;
      }
    }
    this._spinMat(this._rot);
    this._tiltMat();
    this._mul4(this._mModel, this._mTilt, this._mSpin);
    var normM = this._normScratch || (this._normScratch = new Float32Array(9));
    this._normMat(normM, this._mModel);

    // ---- globe (opaque, lit, depth-written) --------------------------
    gl.enable(gl.DEPTH_TEST);
    gl.depthMask(true);
    gl.disable(gl.BLEND);
    var cp = this.coreProg;
    gl.useProgram(cp.prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.coreBuf);
    var u = cp.uniforms;
    gl.uniformMatrix4fv(u.uProj, false, this._mProj);
    gl.uniformMatrix4fv(u.uView, false, this._viewCache);
    gl.uniformMatrix4fv(u.uModel, false, this._mModel);
    gl.uniformMatrix3fv(u.uNormMat, false, normM);
    gl.uniform1f(u.uGlow, s.glow);
    gl.uniform1f(u.uScan, t);
    gl.uniform1f(u.uTime, t);
    gl.uniform1f(u.uJitter, s.jitter);
    gl.enableVertexAttribArray(cp.attrs.aPos);
    gl.vertexAttribPointer(cp.attrs.aPos, 3, gl.FLOAT, false, 24, 0);
    gl.enableVertexAttribArray(cp.attrs.aNorm);
    gl.vertexAttribPointer(cp.attrs.aNorm, 3, gl.FLOAT, false, 24, 12);
    gl.drawArrays(gl.TRIANGLES, 0, this.coreCount);

    // ---- atmospheric rim (additive, no depth write) ------------------
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.depthMask(false);
    if (this.quality === "high") {
      var rp = this.rimProg;
      gl.useProgram(rp.prog);
      gl.bindBuffer(gl.ARRAY_BUFFER, this.shellBuf);
      var ru = rp.uniforms;
      gl.uniformMatrix4fv(ru.uProj, false, this._mProj);
      gl.uniformMatrix4fv(ru.uView, false, this._viewCache);
      gl.uniformMatrix4fv(ru.uModel, false, this._mModel);
      gl.uniform1f(ru.uGlow, s.glow);
      gl.enableVertexAttribArray(rp.attrs.aPos);
      gl.vertexAttribPointer(rp.attrs.aPos, 3, gl.FLOAT, false, 0, 0);
      gl.drawArrays(gl.TRIANGLES, 0, this.shellCount);
    }

    // ---- particles (additive points on orbital shells) ---------------
    var pp = this.partProg;
    gl.useProgram(pp.prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.partBuf);
    var pu = pp.uniforms;
    var drawCount = this.quality === "reduced"
      ? Math.floor(this.partCount * 0.45) : this.partCount;
    gl.uniformMatrix4fv(pu.uProj, false, this._mProj);
    gl.uniformMatrix4fv(pu.uView, false, this._viewCache);
    gl.uniformMatrix4fv(pu.uModel, false, this._mModel);
    gl.uniform1f(pu.uTime, t);
    gl.uniform1f(pu.uSpread, s.points);
    gl.uniform1f(pu.uSize, (this.quality === "reduced" ? 2.6 : 3.4));
    gl.uniform1f(pu.uGlow, s.glow);
    var tint = this._tint(s.hue);
    gl.uniform3f(pu.uTint, tint[0], tint[1], tint[2]);
    gl.enableVertexAttribArray(pp.attrs.aPos);
    gl.vertexAttribPointer(pp.attrs.aPos, 3, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(pp.attrs.aSeed);
    gl.vertexAttribPointer(pp.attrs.aSeed, 1, gl.FLOAT, false, 16, 12);
    gl.drawArrays(gl.POINTS, 0, drawCount);

    // ---- counter-rotating scan ring (same buffer, different model) ---
    if (this.quality === "high" && !this._reducedMotion) {
      this._spinMat(-this._rot * 1.7);
      var ring = this._mRing || (this._mRing = new Float32Array(16));
      this._mul4(ring, this._mTilt, this._mSpin);
      gl.uniformMatrix4fv(pu.uModel, false, ring);
      gl.uniform1f(pu.uSpread, 1.06);
      gl.uniform1f(pu.uSize, 5.2);
      gl.uniform3f(pu.uTint, 0.18, 0.9, 0.75);
      gl.drawArrays(gl.POINTS, 0, Math.floor(drawCount / 5));
    }
  };

  IrisCore.prototype._dropEffects = function () {
    // Signals the loop to: DPR 1.0, skip rim + scan ring, fewer points.
    // Actual switches happen inline in _frame; nothing else to do here.
  };

  IrisCore.prototype._tint = function (hueShift) {
    var r = 0.13 + Math.max(0, -hueShift) * 0.65;
    var g = 0.83 + hueShift * 0.1;
    var b = 0.94 + Math.min(0, hueShift) * 0.3;
    return [Math.min(1, r), Math.max(0.1, Math.min(1, g)), Math.min(1, b)];
  };

  window.IrisCore = IrisCore;
})();
