/* =========================================================================
   SIMULAZIONE DI FLUIDO SU GPU (WebGL1) — layer sotto ai glifi dello sfondo.
   Muovendo il mouse si "spinge" un campo di velocita'; un campo di colorante
   (dye) viene trasportato da quella velocita', vortica e si dissolve. E' un
   vero solutore incomprimibile: advezione + vorticita' + proiezione di
   pressione (Jacobi). Nessuna libreria: le shader sono qui sotto.

   Non disegna nulla a schermo: gira su un canvas WebGL FUORI dal DOM e serve
   solo a produrre il campo `dye`, che `sfondo.js` legge (readPixels) per
   accendere i glifi e colorare la pozza. Se WebGL o i float a 16 bit non ci
   sono (VM senza GPU), `creaFluido` torna null e lo sfondo ripiega sul canvas
   2D. Struttura derivata dal classico solutore di Stam su GPU.
========================================================================= */

const VERT = `
  precision highp float;
  attribute vec2 aPos;
  varying vec2 vUv;
  varying vec2 vL, vR, vT, vB;
  uniform vec2 uTexel;
  void main() {
    vUv = aPos * 0.5 + 0.5;
    vL = vUv - vec2(uTexel.x, 0.0);
    vR = vUv + vec2(uTexel.x, 0.0);
    vT = vUv + vec2(0.0, uTexel.y);
    vB = vUv - vec2(0.0, uTexel.y);
    gl_Position = vec4(aPos, 0.0, 1.0);
  }
`;

// Advezione: sposta un campo all'indietro lungo la velocita' (semi-Lagrangiano),
// con dissipazione per far svanire dye e velocita' nel tempo.
const ADVECT = `
  precision highp float;
  varying vec2 vUv;
  uniform sampler2D uVel;
  uniform sampler2D uSrc;
  uniform vec2 uTexel;
  uniform float uDt;
  uniform float uDiss;
  void main() {
    vec2 coord = vUv - uDt * texture2D(uVel, vUv).xy * uTexel;
    gl_FragColor = texture2D(uSrc, coord) / (1.0 + uDiss * uDt);
  }
`;

const DIVERGENCE = `
  precision highp float;
  varying vec2 vUv; varying vec2 vL, vR, vT, vB;
  uniform sampler2D uVel;
  void main() {
    float l = texture2D(uVel, vL).x;
    float r = texture2D(uVel, vR).x;
    float t = texture2D(uVel, vT).y;
    float b = texture2D(uVel, vB).y;
    gl_FragColor = vec4(0.5 * (r - l + t - b), 0.0, 0.0, 1.0);
  }
`;

const CURL = `
  precision highp float;
  varying vec2 vUv; varying vec2 vL, vR, vT, vB;
  uniform sampler2D uVel;
  void main() {
    float l = texture2D(uVel, vL).y;
    float r = texture2D(uVel, vR).y;
    float t = texture2D(uVel, vT).x;
    float b = texture2D(uVel, vB).x;
    gl_FragColor = vec4(0.5 * (r - l - t + b), 0.0, 0.0, 1.0);
  }
`;

// Vorticita' confinata: rimette energia nei vortici, cosi' il fluido "gira"
// invece di appiattirsi subito. E' cio' che da' il moto ad acqua.
const VORTICITY = `
  precision highp float;
  varying vec2 vUv; varying vec2 vL, vR, vT, vB;
  uniform sampler2D uVel;
  uniform sampler2D uCurl;
  uniform float uCurlAmt;
  uniform float uDt;
  void main() {
    float l = texture2D(uCurl, vL).x;
    float r = texture2D(uCurl, vR).x;
    float t = texture2D(uCurl, vT).x;
    float b = texture2D(uCurl, vB).x;
    float c = texture2D(uCurl, vUv).x;
    vec2 force = 0.5 * vec2(abs(t) - abs(b), abs(r) - abs(l));
    force /= length(force) + 0.0001;
    force *= uCurlAmt * c;
    force.y *= -1.0;
    vec2 vel = texture2D(uVel, vUv).xy + force * uDt;
    gl_FragColor = vec4(vel, 0.0, 1.0);
  }
`;

const PRESSURE = `
  precision highp float;
  varying vec2 vUv; varying vec2 vL, vR, vT, vB;
  uniform sampler2D uPress;
  uniform sampler2D uDiv;
  void main() {
    float l = texture2D(uPress, vL).x;
    float r = texture2D(uPress, vR).x;
    float t = texture2D(uPress, vT).x;
    float b = texture2D(uPress, vB).x;
    float d = texture2D(uDiv, vUv).x;
    gl_FragColor = vec4((l + r + t + b - d) * 0.25, 0.0, 0.0, 1.0);
  }
`;

const GRADIENT = `
  precision highp float;
  varying vec2 vUv; varying vec2 vL, vR, vT, vB;
  uniform sampler2D uPress;
  uniform sampler2D uVel;
  void main() {
    float l = texture2D(uPress, vL).x;
    float r = texture2D(uPress, vR).x;
    float t = texture2D(uPress, vT).x;
    float b = texture2D(uPress, vB).x;
    vec2 vel = texture2D(uVel, vUv).xy - vec2(r - l, t - b);
    gl_FragColor = vec4(vel, 0.0, 1.0);
  }
`;

// Copia il dye in un framebuffer a byte, da cui readPixels legge in modo
// affidabile: leggere UNSIGNED_BYTE da un target half-float non e' garantito in
// WebGL1 (molte GPU tornano zeri), quindi facciamo il passaggio esplicito.
const COPIA = `
  precision highp float;
  varying vec2 vUv;
  uniform sampler2D uSrc;
  void main() {
    float v = clamp(texture2D(uSrc, vUv).x, 0.0, 1.0);
    gl_FragColor = vec4(v, v, v, 1.0);
  }
`;

// Aggiunge una macchia gaussiana a un campo (velocita' o dye), additiva.
const SPLAT = `
  precision highp float;
  varying vec2 vUv;
  uniform sampler2D uSrc;
  uniform vec3 uColor;
  uniform vec2 uPoint;
  uniform float uRadius;
  uniform float uAspect;
  void main() {
    vec2 p = vUv - uPoint;
    p.x *= uAspect;
    vec3 splat = exp(-dot(p, p) / uRadius) * uColor;
    gl_FragColor = vec4(texture2D(uSrc, vUv).xyz + splat, 1.0);
  }
`;

function compila(gl, tipo, src) {
  const s = gl.createShader(tipo);
  gl.shaderSource(s, src);
  gl.compileShader(s);
  if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
    throw new Error(gl.getShaderInfoLog(s) || 'shader');
  }
  return s;
}

function programma(gl, vert, frag) {
  const p = gl.createProgram();
  gl.attachShader(p, compila(gl, gl.VERTEX_SHADER, vert));
  gl.attachShader(p, compila(gl, gl.FRAGMENT_SHADER, frag));
  gl.linkProgram(p);
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(p) || 'link');
  }
  const uniformi = {};
  const n = gl.getProgramParameter(p, gl.ACTIVE_UNIFORMS);
  for (let i = 0; i < n; i++) {
    const nome = gl.getActiveUniform(p, i).name;
    uniformi[nome] = gl.getUniformLocation(p, nome);
  }
  return { p, u: uniformi };
}

export function creaFluido() {
  let gl = null;
  try {
    const c = document.createElement('canvas');
    gl = c.getContext('webgl', { alpha: false, depth: false, stencil: false,
      antialias: false, preserveDrawingBuffer: false })
      || c.getContext('experimental-webgl');
  } catch (e) { gl = null; }
  if (!gl) return null;

  const halfExt = gl.getExtension('OES_texture_half_float');
  if (!halfExt) return null;
  const linExt = gl.getExtension('OES_texture_half_float_linear');
  const HALF = halfExt.HALF_FLOAT_OES;
  const filtro = linExt ? gl.LINEAR : gl.NEAREST;

  // verifica che si possa davvero renderizzare su una texture half-float:
  // alcune GPU espongono l'estensione ma poi il framebuffer e' incompleto.
  function nuovaFBO(w, h, filt, tipo) {
    const t = tipo || HALF;
    const tex = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, filt);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, filt);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, t, null);
    const fbo = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fbo);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, tex, 0);
    return { tex, fbo, w, h };
  }

  let progs;
  try {
    progs = {
      advect: programma(gl, VERT, ADVECT),
      diverg: programma(gl, VERT, DIVERGENCE),
      curl: programma(gl, VERT, CURL),
      vort: programma(gl, VERT, VORTICITY),
      press: programma(gl, VERT, PRESSURE),
      grad: programma(gl, VERT, GRADIENT),
      splat: programma(gl, VERT, SPLAT),
      copia: programma(gl, VERT, COPIA),
    };
  } catch (e) { return null; }

  const quad = gl.createBuffer();
  gl.bindBuffer(gl.ARRAY_BUFFER, quad);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);

  // Risoluzione della simulazione: bassa di proposito. Il campo e' morbido e
  // viene ingrandito con interpolazione, quindi 160px sul lato lungo bastano e
  // tengono readPixels e i 20 passi di pressione a costo trascurabile.
  const SIM = 160;
  let W = SIM, H = SIM, aspetto = 1;
  let vel, div, curlF, press0, press1, dye0, dye1, lettura;
  let pronto = false;

  function liberaFBO(f) {
    if (!f) return;
    gl.deleteTexture(f.tex); gl.deleteFramebuffer(f.fbo);
  }
  function liberaTutti() {
    // il resize rialloca: senza questa pulizia ogni ridimensionamento lascerebbe
    // in giro le texture/FBO precedenti (perdita di memoria sulla GPU).
    if (vel) { liberaFBO(vel[0]); liberaFBO(vel[1]); }
    [div, curlF, press0, press1, dye0, dye1, lettura].forEach(liberaFBO);
  }

  function alloca(vw, vh) {
    liberaTutti();
    aspetto = vw / vh;
    if (aspetto >= 1) { W = SIM; H = Math.round(SIM / aspetto); }
    else { H = SIM; W = Math.round(SIM * aspetto); }
    vel = [nuovaFBO(W, H, filtro), nuovaFBO(W, H, filtro)];
    dye0 = nuovaFBO(W, H, filtro); dye1 = nuovaFBO(W, H, filtro);
    div = nuovaFBO(W, H, gl.NEAREST);
    curlF = nuovaFBO(W, H, gl.NEAREST);
    press0 = nuovaFBO(W, H, gl.NEAREST); press1 = nuovaFBO(W, H, gl.NEAREST);
    lettura = nuovaFBO(W, H, gl.NEAREST, gl.UNSIGNED_BYTE);
    // controlla la completezza del framebuffer una volta sola
    gl.bindFramebuffer(gl.FRAMEBUFFER, vel[0].fbo);
    pronto = gl.checkFramebufferStatus(gl.FRAMEBUFFER) === gl.FRAMEBUFFER_COMPLETE;
    return pronto;
  }

  function usa(prog) {
    gl.useProgram(prog.p);
    gl.bindBuffer(gl.ARRAY_BUFFER, quad);
    const loc = gl.getAttribLocation(prog.p, 'aPos');
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    if (prog.u.uTexel) gl.uniform2f(prog.u.uTexel, 1 / W, 1 / H);
  }
  function verso(target) {
    gl.bindFramebuffer(gl.FRAMEBUFFER, target.fbo);
    gl.viewport(0, 0, target.w, target.h);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
  }
  function lega(loc, fbo, unita) {
    gl.activeTexture(gl.TEXTURE0 + unita);
    gl.bindTexture(gl.TEXTURE_2D, fbo.tex);
    gl.uniform1i(loc, unita);
  }

  const PRESS_ITER = 20;
  const splatCoda = [];

  function applicaSplat(x, y, dx, dy, dye) {
    // velocita'
    usa(progs.splat);
    lega(progs.splat.u.uSrc, vel[0], 0);
    gl.uniform1f(progs.splat.u.uAspect, aspetto);
    gl.uniform2f(progs.splat.u.uPoint, x, y);
    gl.uniform1f(progs.splat.u.uRadius, 0.0028);
    gl.uniform3f(progs.splat.u.uColor, dx, dy, 0);
    verso(vel[1]); [vel[0], vel[1]] = [vel[1], vel[0]];
    // dye (intensita' nel canale rosso)
    lega(progs.splat.u.uSrc, dye0, 0);
    gl.uniform1f(progs.splat.u.uRadius, 0.004);
    gl.uniform3f(progs.splat.u.uColor, dye, dye * 0.15, dye * 0.2);
    verso(dye1); [dye0, dye1] = [dye1, dye0];
  }

  return {
    disponibile: () => true,

    ridimensiona(vw, vh) { return alloca(vw, vh); },

    // x,y in [0,1] (origine in basso a sinistra, come le UV WebGL);
    // dx,dy spinta di velocita'; dye quantita' di colorante.
    splat(x, y, dx, dy, dye) { splatCoda.push([x, y, dx, dy, dye]); },

    passo(dt) {
      if (!pronto) return;
      const h = Math.min(dt, 0.016);
      gl.disable(gl.BLEND);

      for (const s of splatCoda) applicaSplat(s[0], s[1], s[2], s[3], s[4]);
      splatCoda.length = 0;

      // curl
      usa(progs.curl); lega(progs.curl.u.uVel, vel[0], 0); verso(curlF);
      // vorticita' confinata
      usa(progs.vort);
      lega(progs.vort.u.uVel, vel[0], 0); lega(progs.vort.u.uCurl, curlF, 1);
      gl.uniform1f(progs.vort.u.uCurlAmt, 22.0); gl.uniform1f(progs.vort.u.uDt, h);
      verso(vel[1]); [vel[0], vel[1]] = [vel[1], vel[0]];
      // divergenza
      usa(progs.diverg); lega(progs.diverg.u.uVel, vel[0], 0); verso(div);
      // pressione (Jacobi), partendo da zero non serve: iteriamo su press0
      usa(progs.press);
      for (let i = 0; i < PRESS_ITER; i++) {
        lega(progs.press.u.uPress, press0, 0); lega(progs.press.u.uDiv, div, 1);
        verso(press1); [press0, press1] = [press1, press0];
      }
      // sottrai il gradiente -> velocita' senza divergenza
      usa(progs.grad);
      lega(progs.grad.u.uPress, press0, 0); lega(progs.grad.u.uVel, vel[0], 1);
      verso(vel[1]); [vel[0], vel[1]] = [vel[1], vel[0]];
      // advezione della velocita' (dissipa un filo)
      usa(progs.advect);
      gl.uniform1f(progs.advect.u.uDt, h);
      lega(progs.advect.u.uVel, vel[0], 0); lega(progs.advect.u.uSrc, vel[0], 1);
      gl.uniform1f(progs.advect.u.uDiss, 0.2);
      verso(vel[1]); [vel[0], vel[1]] = [vel[1], vel[0]];
      // advezione del dye (dissipa piu' in fretta: la scia deve svanire)
      lega(progs.advect.u.uVel, vel[0], 0); lega(progs.advect.u.uSrc, dye0, 1);
      gl.uniform1f(progs.advect.u.uDiss, 1.1);
      verso(dye1); [dye0, dye1] = [dye1, dye0];
    },

    // legge il campo dye (canale rosso) nel buffer fornito (Uint8, RGBA).
    // Torna {w,h}. Origine in basso a sinistra.
    leggi(buf) {
      if (!pronto) return { w: 0, h: 0 };
      // copia dye -> framebuffer a byte, poi legge quello
      usa(progs.copia);
      lega(progs.copia.u.uSrc, dye0, 0);
      verso(lettura);
      gl.readPixels(0, 0, W, H, gl.RGBA, gl.UNSIGNED_BYTE, buf);
      return { w: W, h: H };
    },

    dim: () => ({ w: W, h: H }),

    distruggi() {
      liberaTutti();
      const perdi = gl.getExtension('WEBGL_lose_context');
      if (perdi) perdi.loseContext();
    },
  };
}
