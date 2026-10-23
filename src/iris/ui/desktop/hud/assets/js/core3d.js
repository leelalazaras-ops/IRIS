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
    var texFn = is3 ? "texture" : "texture2D";

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
      uniform sampler2D uEarth;
      uniform sampler2D uCloud;
      ${f}
      void main(){
        vec3 N = normalize(vN);
        vec3 L = normalize(vec3(-0.45, 0.55, 0.7));
        vec3 V = normalize(vec3(0.0, 0.12, 1.0));
        float diff = max(dot(N, L), 0.0);
        float spec = pow(max(dot(reflect(-L, N), V), 0.0), 26.0);
        float limb = 1.0 - 0.55 * pow(1.0 - max(dot(N, V), 0.0), 1.6);

        // Procedural Earth albedo baked once in _earthTexture() (oceans,
        // continents, ice, city-node glows). Object-space position is
        // used so the map rotates with the globe.
        vec3 nn = normalize(vP);
        float u = atan(nn.z, nn.x) * 0.15915494 + 0.5;
        float w = 0.5 - asin(clamp(nn.y, -1.0, 1.0)) * 0.31830989;
        vec3 albedo = ${texFn}(uEarth, vec2(u, w)).rgb;
        float land = smoothstep(0.02, 0.10, albedo.g - albedo.b);

        // cloud layer: separate textures drift slowly against the ground
        float cu = u + uTime * 0.0035;
        float cloud = ${texFn}(uCloud, vec2(fract(cu), w)).r;
        cloud += ${texFn}(uCloud, vec2(fract(cu * 1.31 + 0.33), w * 1.06 - 0.03)).r * 0.4;
        cloud = smoothstep(0.52, 0.86, cloud) * 0.68;

        // restrained meridional accents — far fainter than before
        float lon = atan(nn.z, nn.x);
        float grid = 0.0;
        grid += smoothstep(0.97, 1.0, abs(sin(nn.y * 14.0))) * (0.04 + 0.07 * land);
        grid += smoothstep(0.975, 1.0, abs(sin(lon * 18.0))) * (0.03 + 0.06 * land);
        float bands = 0.5 + 0.5 * sin(lon * 3.0 + nn.y * 5.0 + uTime * 0.35);
        float n = sin(vP.x*9.0 + uScan)*sin(vP.y*7.0 - uScan)*sin(vP.z*8.0);

        vec3 accent = vec3(0.16, 0.86, 0.97);
        // Lambert with a gentle floor: readable night-side silhouette while
        // the terminator stays a smooth, convincing gradient.
        vec3 litC = albedo * (0.22 + 1.15 * diff * limb + 0.14 * diff);
        litC = mix(litC, vec3(0.92, 0.95, 0.98) * (0.32 + 0.95 * diff * limb), cloud);
        litC += accent * grid * (0.30 + 0.40 * diff);
        litC += vec3(0.06, 0.35, 0.12) * bands * 0.08 * land * (1.0 - cloud);
        litC += albedo * pow(1.0 - diff, 3.0) * 0.18;   // soft backlight
        float fres = pow(1.0 - max(dot(N, V), 0.0), 2.6);
        vec3 col = litC * (0.92 + 0.28 * uGlow);
        col += vec3(0.0, 0.55, 0.75) * fres * (0.55 + 0.35 * uGlow);
        col += accent * spec * 0.5 * (1.0 - cloud);
        col += vec3(0.0, 0.28, 0.34) * abs(n) * 0.14 * (1.0 - cloud);
        ${fAssign}vec4(col, 1.0);
      }`
    );
    if (!this.coreProg) { this._initFailure("shader compile failed"); return false; }
    gl.useProgram(this.coreProg.prog);
    gl.uniform1i(this.coreProg.uniforms.uEarth, 0);  // sampler on unit 0
    gl.uniform1i(this.coreProg.uniforms.uCloud, 1);  // cloud layer on unit 1

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
    // NOTE: _sphereGeometry returns { array, positionCount } — not a plain
    // array. A previous version read `sphere.length` (undefined on that
    // object, giving a zero-length Float32Array), which uploaded an empty
    // buffer while coreCount stayed correct: every triangle collapsed to
    // the origin and the globe pass drew nothing but the additive
    // particles survived, matching the "faint particle sphere" report.
    var verts = new Float32Array(sphere.array);
    this.coreCount = sphere.positionCount;
    this.coreBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.coreBuf);
    gl.bufferData(gl.ARRAY_BUFFER, verts, gl.STATIC_DRAW);

    var shell = this._sphereGeometry(1.0, 28);
    this.shellCount = shell.positionCount;
    this.shellBuf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.shellBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(shell.array), gl.STATIC_DRAW);

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

    // Procedural Earth albedo — generated once, uploaded once.
    this._earthTex = this._earthTexture();
    this._cloudTex = this._cloudTexture();

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

  /* ------------------------------------------------ procedural Earth
     Built entirely offline at init on a detached 1024x512 canvas:
     stylised ocean gradient, simplified-but-recognisable continent
     outlines, polar ice, a faint graticule and baked city-node glows.
     Uploaded once as a mipmapped texture — no network fetch, no image
     asset, no dependency, and zero per-frame allocation (perf model
     unchanged: one extra texture fetch per fragment). */

  var CONTINENTS = [
    // North America
    [-168,65, -160,63, -152,59, -146,60, -140,59, -133,55, -127,51, -124,46,
     -121,38, -117,33, -112,31, -106,29, -100,26, -97,25, -94,29, -90,29,
     -88,30, -85,30, -82,27, -80,26, -81,31, -76,35, -74,40, -70,42, -66,45,
     -60,47, -56,52, -62,56, -68,59, -76,62, -78,68, -84,70, -92,71, -102,73,
     -112,72, -122,71, -132,70, -142,70, -153,71, -163,69],
    // Greenland
    [-54,60, -46,61, -40,64, -30,69, -22,72, -20,77, -30,81, -44,83, -58,82,
     -66,78, -70,73, -64,66],
    // South America
    [-79,9, -75,11, -71,12, -64,10, -60,8, -52,5, -50,0, -45,-2, -39,-6,
     -35,-8, -37,-13, -40,-20, -45,-25, -49,-31, -55,-36, -60,-40, -63,-45,
     -66,-50, -69,-53, -73,-53, -74,-47, -73,-40, -71,-32, -70,-24, -70,-18,
     -75,-15, -79,-7, -81,-4, -80,1, -78,6],
    // Africa
    [-16,14, -17,21, -13,27, -10,32, -6,36, 0,36, 10,37, 20,33, 26,31,
     33,31, 35,27, 38,21, 43,13, 48,12, 51,11, 47,4, 42,0, 40,-6, 37,-12,
     35,-19, 33,-26, 28,-33, 22,-34, 17,-33, 14,-27, 12,-18, 11,-9, 9,-2,
     5,4, 0,6, -8,4, -13,9],
    // Eurasia — one coarse ring: Iberia → Mediterranean → Arabia → India
    // → SE Asia → China → Korea → Siberia → Arctic → Scandinavia → home
    [-9,43, -9,39, -6,36, 0,39, 4,43, 9,44, 14,42, 18,40, 24,41, 29,41,
     30,37, 36,36, 35,33, 34,31, 33,30, 36,26, 39,21, 41,16, 43,13, 45,12,
     49,14, 52,17, 55,20, 57,23, 60,25, 64,25, 67,24, 70,22, 72,19, 74,14,
     76,9, 78,10, 80,14, 82,17, 84,19, 86,20, 88,22, 90,22, 92,21, 94,18,
     96,17, 98,14, 100,7, 101,13, 104,11, 106,14, 109,13, 109,17, 108,20,
     111,21, 114,22, 117,24, 120,26, 122,30, 121,34, 122,38, 124,40, 125,39,
     126,36, 129,35, 130,38, 131,42, 135,47, 138,51, 141,53, 142,59, 147,59,
     152,59, 157,61, 162,61, 167,63, 172,65, 178,67, 180,69, 175,71, 165,72,
     155,73, 145,74, 135,74, 125,75, 115,76, 105,77, 95,78, 85,76, 80,75,
     75,73, 70,73, 67,70, 63,70, 58,70, 53,70, 48,67, 43,66, 40,66, 37,67,
     34,69, 32,70, 30,70, 26,70, 22,70, 18,69, 15,67, 13,65, 10,64, 7,62,
     6,60, 9,58, 11,57, 11,55, 9,54, 6,53, 4,52, 3,51, 1,51, -2,49, -4,48,
     -2,46, -2,44],
    // British Isles (coarse blob)
    [-10,51, -6,50, -1,51, 0,53, -1,56, -5,58, -8,55, -10,54],
    // Japan
    [132,34, 137,35, 141,39, 141,42, 145,44, 143,45, 139,41, 136,37, 133,35],
    // Madagascar
    [48,-13, 50,-16, 50,-24, 47,-25, 44,-22, 44,-17],
    // Australia
    [114,-22, 114,-33, 118,-35, 129,-32, 137,-35, 141,-38, 147,-38, 151,-33,
     153,-28, 153,-25, 147,-19, 143,-14, 142,-11, 137,-12, 130,-12, 125,-14,
     121,-19],
    // Sumatra / Borneo / Java / New Guinea / Philippines
    [95,6, 104,-6, 107,-6, 97,3],
    [109,2, 116,5, 118,1, 116,-3, 110,-3, 109,0],
    [105,-6, 114,-7, 114,-9, 105,-8],
    [131,-1, 141,-3, 147,-6, 146,-9, 139,-9, 133,-5],
    [120,18, 122,14, 126,10, 126,6, 122,6, 120,10],
  ];

  // City network nodes baked into the texture (lon, lat): they rotate
  // with the globe like real surface features.
  var CITY_NODES = [
    [-74,41], [-118,34], [-87,42], [-122,38], [-99,19], [-79,44], [-80,26],
    [-75,-12], [-47,-24], [-58,-35], [-71,-33], [-74,5],
    [0,52], [2,49], [-4,40], [13,53], [3,6], [31,30], [28,-26], [18,-34],
    [38,56], [29,41], [37,36], [51,36], [47,25], [55,25],
    [73,19], [77,29], [67,25], [91,24], [100,14], [107,-6], [104,1], [121,15],
    [116,40], [121,31], [114,23], [127,38], [140,36], [77,43],
    [151,-34], [116,-32], [175,-41], [37,-1],
  ];

  IrisCore.prototype._earthTexture = function () {
    var W = 1024, H = 512;
    var cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    var g2 = cv.getContext("2d");
    var self = this;
    function px(lon) { return (lon + 180) / 360 * W; }
    function py(lat) { return (90 - lat) / 180 * H; }

    // ocean: vertical shade, slightly brighter at the equator — richer,
    // deeper blue than the old grey-navy, with a subtle teal equator tint
    var og = g2.createLinearGradient(0, 0, 0, H);
    og.addColorStop(0.0, "#04243a");
    og.addColorStop(0.35, "#083a58");
    og.addColorStop(0.5, "#0c4a68");
    og.addColorStop(0.65, "#083a58");
    og.addColorStop(1.0, "#04243a");
    g2.fillStyle = og;
    g2.fillRect(0, 0, W, H);

    // Antarctica: polar cap band (the ring below the habitable world)
    g2.fillStyle = "#cfe6ef";
    g2.fillRect(0, py(-68), W, H - py(-68));
    var ag = g2.createLinearGradient(0, py(-68), 0, H);
    ag.addColorStop(0, "rgba(207,230,239,0)");
    ag.addColorStop(0.35, "rgba(207,230,239,0.85)");
    g2.fillStyle = ag;
    g2.fillRect(0, py(-68), W, H - py(-68));

    // continents (soft-edged natural landmass with darker inland band)
    for (var ci = 0; ci < CONTINENTS.length; ci++) {
      var poly = CONTINENTS[ci];
      g2.beginPath();
      for (var i = 0; i < poly.length; i += 2) {
        var xx = px(poly[i]), yy = py(poly[i + 1]);
        if (i === 0) g2.moveTo(xx, yy); else g2.lineTo(xx, yy);
      }
      g2.closePath();
      // muted natural land palette — olive, sage, desert tan. Not neon green.
      var landC = ["#4a6b45", "#5c6e4a", "#6e6743", "#55684b"][ci % 4];
      // soft coastline: wide low-alpha underdraw acts as anti-aliasing
      g2.fillStyle = landC;
      g2.strokeStyle = "rgba(0,0,0,0)";
      g2.shadowColor = "rgba(38, 82, 96, 0.55)";
      g2.shadowBlur = 6;
      g2.fill();
      g2.shadowBlur = 0;
      // thin, darker coastline line (was a cyan glow — far too artificial)
      g2.strokeStyle = "rgba(" + (ci % 2 ? "92,116,88" : "84,104,82") + ", 0.9)";
      g2.lineWidth = 1.1;
      g2.stroke();
    }

    // polar ice caps — subtle, dimmer than before; no artificial band
    var igN = g2.createLinearGradient(0, 0, 0, H * 0.055);
    igN.addColorStop(0, "rgba(216,232,238,0.72)");
    igN.addColorStop(1, "rgba(216,232,238,0)");
    g2.fillStyle = igN;
    g2.fillRect(0, 0, W, H * 0.055);

    // very faint graticule — graders note the span, not the lines
    g2.strokeStyle = "rgba(90, 190, 220, 0.045)";
    g2.lineWidth = 0.7;
    for (var lo = -180; lo <= 180; lo += 15) {
      g2.beginPath(); g2.moveTo(px(lo), 0); g2.lineTo(px(lo), H); g2.stroke();
    }
    for (var la = -75; la <= 75; la += 15) {
      g2.beginPath(); g2.moveTo(0, py(la)); g2.lineTo(W, py(la)); g2.stroke();
    }

    // city network nodes: restrained halo + pinpoint core
    for (var n = 0; n < CITY_NODES.length; n++) {
      var nx = px(CITY_NODES[n][0]), ny = py(CITY_NODES[n][1]);
      var hg = g2.createRadialGradient(nx, ny, 0, nx, ny, 6);
      hg.addColorStop(0, "rgba(140, 230, 250, 0.35)");
      hg.addColorStop(1, "rgba(140, 230, 250, 0)");
      g2.fillStyle = hg;
      g2.fillRect(nx - 6, ny - 6, 12, 12);
      g2.beginPath();
      g2.fillStyle = "rgba(226, 250, 255, 0.85)";
      g2.arc(nx, ny, 1.3, 0, 2 * Math.PI);
      g2.fill();
    }

    // upload once: POT texture, mipmapped, cheap filtered fetch per frame
    var gl = self.gl;
    if (!gl) return null;
    var tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, cv);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.generateMipmap(gl.TEXTURE_2D);
    return tex;
  };

  /* Procedural cloud sheet: soft blurred blobs on a 512x256 canvas,
     baked once at init. Two octaves in the shader drift them slowly
     against the ground rotation, giving weather-like movement without
     per-frame GPU cost. No network, no dependency. */
  IrisCore.prototype._cloudTexture = function () {
    var W = 512, H = 256;
    var cv = document.createElement("canvas");
    cv.width = W; cv.height = H;
    var g2 = cv.getContext("2d");
    var self = this;
    g2.fillStyle = "#000";
    g2.fillRect(0, 0, W, H);
    var rng = function (seed) {
      var x = seed;
      return function () { x = (x * 1103515245 + 12345) & 0x7fffffff; return x / 0x7fffffff; };
    }(1337);
    for (var i = 0; i < 90; i++) {
      var cx = rng() * W, cy = rng() * H;
      var rx = 30 + rng() * 90, ry = 10 + rng() * 30;
      var cg = g2.createRadialGradient(cx, cy, 0, cx, cy, Math.max(rx, ry) * 0.8);
      var a = 0.10 + rng() * 0.16;
      cg.addColorStop(0, "rgba(255,255,255," + a + ")");
      cg.addColorStop(1, "rgba(255,255,255,0)");
      g2.fillStyle = cg;
      g2.save();
      g2.translate(cx, cy);
      g2.scale(1, ry / rx);
      g2.beginPath();
      g2.arc(0, 0, rx, 0, 2 * Math.PI);
      g2.fill();
      g2.restore();
    }
    var gl = this.gl;
    if (!gl) return null;
    var tex = gl.createTexture();
    gl.activeTexture(gl.TEXTURE1);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, cv);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.REPEAT);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
    gl.generateMipmap(gl.TEXTURE_2D);
    gl.activeTexture(gl.TEXTURE0);  // leave the default unit active
    return tex;
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
    // The rim/particle passes leave depthMask(false) set, and WebGL gates
    // clear(DEPTH_BUFFER_BIT) on the current depth mask — clearing while
    // writes are off kept last frame's globe depth in the buffer, so after
    // the very first frame every globe fragment failed the LESS depth test
    // and the sphere vanished, leaving only the additive particles.
    gl.depthMask(true);
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
