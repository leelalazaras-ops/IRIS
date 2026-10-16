/* ============================================================
   IRIS 3D Core — hand-written WebGL2, zero dependencies, fully local.
   Real 3D: perspective projection, orbital shell geometry, additive
   particle field, noise-shaded inner core, scan sweep.

   Reacts to IRIS states emitted by app.js via window.IrisCore.setState():
     idle | processing | speaking | error | listening | disconnected

   If WebGL2 (and WebGL1) are unavailable, draws a restrained 2D canvas
   fallback ring instead and reports it through a callback.
   ============================================================ */
"use strict";

(function () {
  const STATES = {
    idle:        { speed: 0.6,  glow: 1.0, hue: 0.00, jitter: 0.0, points: 1.0 },
    processing:  { speed: 3.2,  glow: 1.8, hue: 0.55, jitter: 0.5, points: 1.6 },
    listening:   { speed: 1.6,  glow: 1.4, hue: 0.15, jitter: 0.15, points: 1.2 },
    speaking:    { speed: 1.2,  glow: 1.6, hue: 0.12, jitter: 0.9, points: 0.9 },
    error:       { speed: 1.0,  glow: 1.1, hue: -0.18, jitter: 0.25, points: 0.7 },
    disconnected:{ speed: 0.15, glow: 0.4, hue: -0.5, jitter: 0.0, points: 0.5 },
  };

  function IrisCore(canvas, onModeChange) {
    this.canvas = canvas;
    this.onModeChange = onModeChange || function () {};
    this.stateName = "disconnected";
    this.target = STATES.disconnected;
    this.current = STATES.disconnected;
    this.mode = "none";       // "webgl2" | "webgl1" | "2d"
    this._last_t = 0;
    this._particles = [];
    this._running = true;
  }

  IrisCore.prototype.setState = function (name) {
    if (!STATES[name]) name = "idle";
    if (name === this.stateName) return;
    this.stateName = name;
    this.target = STATES[name];
    if (this.mode === "2d") this._draw2dImmediate();
  };

  /* ------------------------------------------------ init */

  IrisCore.prototype.start = function () {
    var ok = this._initGL();
    if (!ok) ok = this._init2D();
    if (!ok) return false;
    var self = this;
    function frame(t) {
      if (!self._running) return;
      self._frame(t);
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    this.onModeChange(this.mode, this._rendererInfo);
    return true;
  };

  IrisCore.prototype.stop = function () { this._running = false; };

  IrisCore.prototype._initGL = function () {
    var gl = null;
    var glver = "";
    try {
      gl = this.canvas.getContext("webgl2", { antialias: true, alpha: true });
      glver = "webgl2";
      if (!gl) {
        gl = this.canvas.getContext("webgl", { antialias: true, alpha: true }) ||
             this.canvas.getContext("experimental-webgl");
        glver = "webgl1";
      }
    } catch (e) { gl = null; }
    if (!gl) return false;

    this.gl = gl;
    this.glver = glver;

    var glsl = glver === "webgl2" ? "#version 300 es\n" : "";
    var is3 = glver === "webgl2";
    var a = is3 ? "in " : "attribute ";      // vertex inputs
    var v = is3 ? "out " : "varying ";       // vertex outputs
    var vf = is3 ? "in " : "varying ";       // fragment inputs
    var f = is3 ? "out vec4 fragColor;" : "";
    var fragPre = is3 ? "#version 300 es\nprecision highp float;\n" : "precision mediump float;\n";

    // ---- core sphere shaders
    this.coreProg = this._program(
      glsl + `
      ${a} vec3 aPos;
      uniform mat4 uProj, uView;
      uniform float uJitter;
      ${v} vec3 vPos;
      void main(){
        vec3 p = aPos * (1.0 + uJitter * 0.03 * sin(aPos.y * 24.0));
        vPos = aPos;
        gl_Position = uProj * uView * vec4(p, 1.0);
      }`,
      fragPre + `
      ${vf} vec3 vPos;
      uniform float uGlow, uScan;
      ${f}
      void main(){
        float rr = length(vPos);
        float rim = smoothstep(0.72, 1.0, rr);
        float n = sin(vPos.x*12.0 + uScan)*sin(vPos.y*9.0 - uScan)*sin(vPos.z*11.0);
        vec3 base = mix(vec3(0.05, 0.16, 0.22), vec3(0.13, 0.83, 0.94), rim);
        vec3 col = base * uGlow + vec3(0.0, 0.06, 0.08) * (0.5 + 0.5 * n);
        float alpha = 0.14 + rim * 0.85;
        ${is3 ? "fragColor = vec4(col, alpha);" : "gl_FragColor = vec4(col, alpha);"}
      }`
    );
    if (!this.coreProg) return false;

    // ---- particle shaders (additive points on an orbital shell)
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
        // breathing shell
        r = r * (1.0 + 0.04 * sin(uTime * 1.4 + s * 3.0)) * uSpread;
        p = p / length(p) * r;
        gl_Position = uProj * uView * uModel * vec4(p, 1.0);
        gl_PointSize = uSize * (0.6 + 0.6 * fract(aSeed * 7.0));
        vA = 0.35 + 0.45 * fract(aSeed * 13.0);
      }`,
      fragPre + `
      ${vf} float vA;
      uniform float uGlow; uniform vec3 uTint;
      ${f}
      void main(){
        vec2 d = gl_PointCoord - vec2(0.5);
        float m = smoothstep(0.5, 0.0, length(d));
        ${is3 ? "fragColor = vec4(uTint, vA * m * uGlow);" : "gl_FragColor = vec4(uTint, vA * m * uGlow);"}
      }`
    );
    if (!this.partProg) return false;

    // core sphere geometry (icosahedron-ish sphere mesh)
    var sphere = this._sphereGeometry(1.0, 28);
    this.coreBuf = gl.createBuffer();
    this.coreCount = sphere.length / 3;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.coreBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(sphere), gl.STATIC_DRAW);

    // particles on two orbital shells
    var N = 1400;
    var parts = [];
    for (var i = 0; i < N; i++) {
      var shell = i % 3 === 0 ? 1.25 : 1.55;
      var u = Math.random(), w = Math.random();
      var th = 2 * Math.PI * u, ph = Math.acos(2 * w - 1);
      parts.push(
        shell * Math.sin(ph) * Math.cos(th),
        shell * Math.cos(ph),
        shell * Math.sin(ph) * Math.sin(th),
        Math.random()
      );
    }
    this.partBuf = gl.createBuffer();
    this.partCount = N;
    gl.bindBuffer(gl.ARRAY_BUFFER, this.partBuf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(parts), gl.STATIC_DRAW);

    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    gl.pointSizeRange = null;

    this.mode = glver;

    var dbg = gl.getExtension("WEBGL_debug_renderer_info");
    this._rendererInfo = dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : "";
    return true;
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
    var nU = gl.getProgramParameter(prog, gl.ACTIVE_UNIFORMS);
    for (var i = 0; i < nU; i++) {
      var info = gl.getActiveUniform(prog, i);
      uniforms[info.name.replace("[0]", "")] = gl.getUniformLocation(prog, info.name);
    }
    return { prog: prog, uniforms: uniforms };
  };

  IrisCore.prototype._sphereGeometry = function (radius, seg) {
    var verts = [];
    for (var y = 0; y < seg; y++) {
      var v0 = y / seg, v1 = (y + 1) / seg;
      var th0 = v0 * Math.PI, th1 = v1 * Math.PI;
      for (var x = 0; x < seg; x++) {
        var u0 = x / seg, u1 = (x + 1) / seg;
        var ph0 = u0 * 2 * Math.PI, ph1 = u1 * 2 * Math.PI;
        function pt(th, ph) {
          return [
            radius * Math.sin(th) * Math.cos(ph),
            radius * Math.cos(th),
            radius * Math.sin(th) * Math.sin(ph),
          ];
        }
        var p00 = pt(th0, ph0), p01 = pt(th0, ph1), p10 = pt(th1, ph0), p11 = pt(th1, ph1);
        verts.push.apply(verts, p00); verts.push.apply(verts, p10); verts.push.apply(verts, p01);
        verts.push.apply(verts, p01); verts.push.apply(verts, p10); verts.push.apply(verts, p11);
      }
    }
    return verts;
  };

  /* ------------------------------------------------ 2D fallback */

  IrisCore.prototype._init2D = function () {
    this.ctx2d = this.canvas.getContext("2d");
    if (!this.ctx2d) return false;
    this.mode = "2d";
    this._rendererInfo = "2D canvas fallback (WebGL unavailable)";
    return true;
  };

  IrisCore.prototype._draw2dImmediate = function () {
    // also used by the per-frame 2d loop
  };

  IrisCore.prototype._draw2d = function (t) {
    var ctx = this.ctx2d;
    var W = this.canvas.width, H = this.canvas.height;
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

  /* ------------------------------------------------ render loop */

  IrisCore.prototype._frame = function (tms) {
    var t = tms / 1000;
    var dt = Math.min(0.1, (tms - this._last_t) / 1000 || 0.016);
    this._last_t = tms;

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
    var W = this.canvas.clientWidth, H = this.canvas.clientHeight;
    var dpr = Math.min(2, window.devicePixelRatio || 1);
    if (W !== 0 && this.canvas.width !== Math.floor(W * dpr)) {
      this.canvas.width = Math.floor(W * dpr);
      this.canvas.height = Math.floor(H * dpr);
    }
    gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    gl.clearColor(0.0, 0.0, 0.0, 0.0);
    gl.clear(gl.COLOR_BUFFER_BIT);

    var proj = this._persp(38 * Math.PI / 180, this.canvas.width / Math.max(1, this.canvas.height), 0.1, 40);
    var eyeDist = 4.6;
    var view = this._lookAt([0, 0.4, eyeDist], [0, 0, 0], [0, 1, 0]);

    // slow global spin, faster when processing
    this._rot += dt * 0.25 * s.speed;
    var model = this._rotY(this._rot);

    // ---- particles (drawn first, additive)
    gl.useProgram(this.partProg.prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.partBuf);
    this._abstract({
      proj: proj, view: view, model: model, time: t,
      spread: s.points, size: (3.4) * (this.glver === "webgl2" ? 1 : 1),
      glow: s.glow,
      tint: this._tint(s.hue),
    }, this.partProg.uniforms);

    var aPos = gl.getAttribLocation(this.partProg.prog, "aPos");
    var aSeed = gl.getAttribLocation(this.partProg.prog, "aSeed");
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 16, 0);
    gl.enableVertexAttribArray(aSeed);
    gl.vertexAttribPointer(aSeed, 1, gl.FLOAT, false, 16, 12);
    gl.drawArrays(gl.POINTS, 0, this.partCount);
    gl.disableVertexAttribArray(aSeed);

    // ---- core sphere
    gl.enable(gl.DEPTH_TEST);
    gl.depthMask(false);
    gl.useProgram(this.coreProg.prog);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.coreBuf);
    var u = this.coreProg.uniforms;
    gl.uniformMatrix4fv(u.uProj, false, proj);
    gl.uniformMatrix4fv(u.uView, false, view);
    gl.uniform1f(u.uGlow, s.glow);
    gl.uniform1f(u.uScan, t);
    gl.uniform1f(u.uJitter, s.jitter);
    var aP = gl.getAttribLocation(this.coreProg.prog, "aPos");
    gl.enableVertexAttribArray(aP);
    gl.vertexAttribPointer(aP, 3, gl.FLOAT, false, 0, 0);
    gl.drawArrays(gl.TRIANGLES, 0, this.coreCount);
    gl.disable(gl.DEPTH_TEST);

    // orbital scan ring drawn as second particle pass
    gl.useProgram(this.partProg.prog);
    gl.uniformMatrix4fv(this.partProg.uniforms.uModel, false, this._rotY(-this._rot * 1.7));
    gl.uniform1f(this.partProg.uniforms.uSpread, 1.06);
    gl.uniform1f(this.partProg.uniforms.uSize, 5.2);
    gl.bindBuffer(gl.ARRAY_BUFFER, this.partBuf);
    gl.enableVertexAttribArray(aPos);
    gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 16, 0);
    gl.uniform3f(this.partProg.uniforms.uTint, 0.18, 0.9, 0.75);
    gl.drawArrays(gl.POINTS, 0, Math.floor(this.partCount / 5));
  };

  IrisCore.prototype._abstract = function (values, uniforms) {
    var gl = this.gl;
    if (uniforms.uProj) gl.uniformMatrix4fv(uniforms.uProj, false, values.proj);
    if (uniforms.uView) gl.uniformMatrix4fv(uniforms.uView, false, values.view);
    if (uniforms.uModel) gl.uniformMatrix4fv(uniforms.uModel, false, values.model);
    if (uniforms.uTime) gl.uniform1f(uniforms.uTime, values.time);
    if (uniforms.uSpread) gl.uniform1f(uniforms.uSpread, values.spread);
    if (uniforms.uSize) gl.uniform1f(uniforms.uSize, values.size);
    if (uniforms.uGlow) gl.uniform1f(uniforms.uGlow, values.glow);
    if (uniforms.uTint) gl.uniform3f(uniforms.uTint, values.tint[0], values.tint[1], values.tint[2]);
  };

  IrisCore.prototype._tint = function (hueShift) {
    // cyan -> teal -> blue scale; hueShift offsets toward warm/red on error/disconnect
    var r = 0.13 + Math.max(0, -hueShift) * 0.65;
    var g = 0.83 + hueShift * 0.1;
    var b = 0.94 + Math.min(0, hueShift) * 0.3;
    return [Math.min(1, r), Math.max(0.1, Math.min(1, g)), Math.min(1, b)];
  };

  IrisCore.prototype._persp = function (fovy, aspect, near, far) {
    var f = 1 / Math.tan(fovy / 2);
    var nf = 1 / (near - far);
    return new Float32Array([
      f / aspect, 0, 0, 0,
      0, f, 0, 0,
      0, 0, (far + near) * nf, -1,
      0, 0, 2 * far * near * nf, 0,
    ]);
  };

  IrisCore.prototype._lookAt = function (eye, center, up) {
    function norm(v) {
      var l = Math.hypot(v[0], v[1], v[2]) || 1;
      return [v[0] / l, v[1] / l, v[2] / l];
    }
    function sub(a, b) { return [a[0] - b[0], a[1] - b[1], a[2] - b[2]]; }
    function cross(a, b) {
      return [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
    }
    function dot(a, b) { return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]; }
    var z = norm(sub(eye, center));
    var x = norm(cross(up, z));
    var y = cross(z, x);
    return new Float32Array([
      x[0], y[0], z[0], 0,
      x[1], y[1], z[1], 0,
      x[2], y[2], z[2], 0,
      -dot(x, eye), -dot(y, eye), -dot(z, eye), 1,
    ]);
  };

  IrisCore.prototype._rotY = function (a) {
    var c = Math.cos(a), s = Math.sin(a);
    return new Float32Array([c, 0, -s, 0, 0, 1, 0, 0, s, 0, c, 0, 0, 0, 0, 1]);
  };

  window.IrisCore = IrisCore;
})();
