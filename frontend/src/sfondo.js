/* =========================================================================
   SFONDO DEL CONCEPT — ripreso da kakashi.ventures (KVA "GlyphField").
   Gli 8 simboli reali del sito (/glifi/glifoN.png, qui incorporati) sono disposti
   SPARSI su una griglia (solo una frazione di celle, secondo la densita'), molto
   tenui e ruotati a 0/90/180/270 gradi; vicino al cursore si accendono in
   rosa-rosso rgb(255,120,140) con un alone rosso. Indipendente dall'app qui sopra.
========================================================================= */
export function avviaSfondo(cv) {
  "use strict";
  if (!cv) return function () {};
  var ctx = cv.getContext('2d');
  var vivo = true;

  var GLOW = '255,120,140';        // colore dei glifi accesi (dal sito)
  var HALO = '154,3,30';           // alone rosso attorno al cursore (#9A031E)
  // ZOOM DELLO SFONDO (2026-07-20): il passo della griglia era 46px, glifi molto
  // piccoli e fitti. Portato a 72 per avvicinarsi alla scala di kakashi.ventures,
  // dove i simboli si leggono come segni e non come texture. Tutto il resto scala
  // da qui: la dimensione del glifo e' DRAW*CELL e il raggio del cursore
  // RANGE_CELLS*CELL, quindi per ingrandire o rimpicciolire basta questa riga.
  // EFFETTO AL CURSORE. Spento e poi RIACCESO il 2026-07-21.
  //
  // Le mie misure sul sito di kakashi non rilevavano alcuna reazione al cursore
  // (alpha identica con mouse sopra e lontano, nessun pixel colorato, nessun
  // gradiente o maschera CSS che segua il puntatore), ne' con mouse reale ne'
  // con eventi sintetici. L'utente pero' lo vede: l'effetto c'e' e sono i miei
  // strumenti a non coglierlo. Fra un'osservazione diretta e una sonda che non
  // vede nulla, vince l'osservazione.
  //
  // Resta una costante perche' e' l'unico interruttore utile che abbiamo: da
  // spento non gira alcun ciclo di animazione, e su macchine senza accelerazione
  // grafica (le VM della scuola) lo sfondo smette di costare.
  var EFFETTO_CURSORE = true;

  var CELL = 72;                   // passo della griglia (px) — loro: 72.5 CSS
  // REPLICA DI KAKASHI (2026-07-21), non piu' una stima: misurato sul loro canvas
  // il 58% delle celle contiene un glifo. Il nostro 0.24 era meno della meta', ed
  // e' il motivo per cui la texture appariva rada e slegata invece che uniforme.
  // (Il passo di griglia era gia' giusto: loro 58px canvas / dpr 0.8 = 72.5 CSS,
  // noi CELL = 72.)
  var DENSITY = 0.58;              // frazione di celle con un glifo
  var DRAW = 0.64;                 // dimensione del glifo rispetto alla cella
  var RANGE_CELLS = 3.0;           // raggio d'influenza del cursore (in celle)

  var SRC = [
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAASUAAAElCAMAAACVuQRFAAAAAXNSR0IArs4c6QAAAARnQU1BAACxjwv8YQUAAAAGUExURRgWFwAAAGiMND0AAAACdFJOU/8A5bcwSgAAAAlwSFlzAAAOwwAADsMBx2+oZAAAABl0RVh0U29mdHdhcmUAUGFpbnQuTkVUIDUuMS4xMYoIFs4AAAC4ZVhJZklJKgAIAAAABQAaAQUAAQAAAEoAAAAbAQUAAQAAAFIAAAAoAQMAAQAAAAIAAAAxAQIAEQAAAFoAAABphwQAAQAAAGwAAAAAAAAAYAAAAAEAAABgAAAAAQAAAFBhaW50Lk5FVCA1LjEuMTEAAAMAAJAHAAQAAAAwMjMwAaADAAEAAAABAAAABaAEAAEAAACWAAAAAAAAAAIAAQACAAQAAABSOTgAAgAHAAQAAAAwMTAwAAAAAAY11HOyj3I7AAAGvElEQVR4Xu3RW3IjORQD0Z79b3qiZdkjpfWoIgDCnrjnU0Eii/afP2OMMcYYY4wxxhhjjDHGGGOMMcYYY4zxv/LPBX9N+ihuTS67fivwlBVjH3jqx+CH3uNpC0bu8XQfv/AR3hFx/hHeaeK3Pcebyzj8HG+W8LNe4+0lHH2Ntwv4Se9x4TQOvseFzfg5x3DlFI4dw5WN+CnHcekwDh3HpV34Hadw7BCOnMKxLfgRZ3HvAE6cxb08fsECTr7B6ws4Gcb8Gq6+xMtruJrE9iruvsCrq7ibw/I6Lj/Fi+u4nMKugttP8JqC2xmsijj/AK+IOJ/ApoyBb3hBxoAfizoWiOcNmHBjz4EN4HEHNrxY82DlDg97sOLElgs7N3jUhR0flnxY+sKDPizZMGTE1BWPGTHlwo4TW1c85sSWByterF3wkBdrFoyYMVcpythwY6+TFLHgx2IjqWIgoF6UcT+hn1RxPqJclHE9o51UcTykWpRxO6WbVHE6pliUcTmnmVRxOKeZVHE4qFaUcTepl1RxNqmXVHE2qlSUcTWrlVRxNKuVVHE0q5VUcTSsUpRxM62TVHEyrZNUcTKtk1RxMq2TVHEyrlDUcTKuUNRxMq5Q1HEyrlCUcTGvkVRxMK+RVHEwr5FUcTCvkVRxMK+RVHEwr5FUcTBvf5JvPo+LefuTfPN5XMzbn+Sbz+Ni3v4k33weF+MqSRUX4ypJFRfjKkkVF+MqSRUX4/Yn+eQFnIzbn+STF3AyrZNUcTKtk1RxMm1/ki9ewc2wUlLFzbBSUsXNsP1JPngJR7NaSRVHs1pJFUez9if53jVcjaolVVyN2p/kcxdxNqmXVHE2aX8Sj13G3aBiUsXdoP3J+6cKOJzTTKo4nLM/efdQCZdjqkkVl1O6SRWnU/Ynb4oyboeUkypuZ7STKo5H1JMqrkfsT94XZZxP2J9EUcb9gP1JFmUM+LHYSKoYsGOwklSx4MZePsmcAxtmzP3FM16sWTDixdoFD1kx5sGKE1tXPObElgkzRkx94jkjplzY8WHpCw/aMOTDkgs7N3jUhR0jpkyYucWzHqxYMWbByD2etmDEizUDJojnDZhwY0/GwHe8IWPAj0UR5x/hHRHnE9hUcPsJXlNwO4TZZRx+jjeXcTiH5TVcfYmXl3A0i/WzuHcAJ87i3vi1Cv/YQlJw/7U3eNCGoS88+EPwM7/hBR0LxPNt/L4neE3B7cd4q4df9grvLuLsK7xbwY96h/cXcPId3t+OH3QEN07i3BHc2IofcxR3TuDUUdzZh19yAqcO4swJnNqEn3EO1w7hyDlc24HfcBoH3+LAaRyM4wes4OYbvL6Cm1msr+HqS7y8hqtJbC/j8FO8uIzDOSwLOP0Erwk4ncKuhOMP8ZKE4xGMqrj/AK+ouO/Hoo6Fb3hBx4IdgwZMAI8bMOHGngUjd3jYghEv1kyYucGjJsw4seXCzg0edWHHhyUflr7woA9LLuw4sXXFY05smTBjxdgFD1kx5sGKF2sXPOTFmgMbbux1kiom7BgsFGUs+LHYSKoYCKgXZdxP6CdVnI8oF2Vcz2gnVRwPqRZl3E7pJlWcjikWZVzOaSZVHM7ZX/yNf6XPb+bPQXjrMu4m9ZIqzibtL/7Gv9LHN/PHKD53DVezWkkVR7NaSRVHwypFHUfDKkUZN9M6SRUn0zpJFSfTOkkVJ9M6SRUn4wpFHSfjCkUdJ+MKRR0n4wpFGRfzGkkVB/MaSRUH8xpJFQfzGkkVB/MaSRUH8xpJFQfz9if55vO4mLc/yTefx8W8/Um++Twu5u1P8s3ncTGuklRxMa6SVHExrpJUcTGuklRxMW5/kk9ewMm0TlLFybROUsXJtE5Sxcm0/Um+eAU3w0pJFTfDSkkVN8P2J/ngJRzNaiVVHM1qJVUczdqf5HvXcDWqllRxNWp/ks9dxNmkXlLF2aT9STx2GXeDikkVd4P2J++fKuBwTjOp4nBMNanicsz+5O0zRZxO6SZVnA4pJ1XcDtmfvC3KOJ7RTqo4HlFPqrie0E+qOB/wA5Iq7vux2EiqGPBjMZ9kUMeCHYP5JHsGTJgx9xfPmDHnwIYXaxc85MWaBSNWjH3gKSvGPFhxYuuKx5zYMmHGiKlPPOfDkg1DNgz9hydtGPJhyYWdGzxqwowTWx6s3OFhD1asGHNgA3jcgQ0z5nQsfMMLOhbsGFRx/wFeUXE/gEkN1x/iJQ3XIxgVcPoZ3hNwOoXdVdx9gVdXcTeI6RXcfIPXV3AzjPkzuHUQZ87g1hhjjDHGGGOMMcYYY4wxxhhjjDHGGGP8bv8CejupCVkO8rUAAAAASUVORK5CYII=",
    "data:image/png;base64,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",
    "data:image/png;base64,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",
    "data:image/png;base64,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",
    "data:image/png;base64,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",
    "data:image/png;base64,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",
    "data:image/png;base64,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",
    "data:image/png;base64,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"
  ];

  var grey = [], red = [], ready = false, loaded = 0;
  var W = 0, H = 0, DPR = 1, cols = 0, rows = 0, cells = [], base = null;

  function tint(img, rgb) {
    var t = document.createElement('canvas');
    t.width = img.naturalWidth || img.width; t.height = img.naturalHeight || img.height;
    var c = t.getContext('2d');
    c.drawImage(img, 0, 0);
    c.globalCompositeOperation = 'source-atop';
    c.fillStyle = 'rgb(' + rgb + ')';
    c.fillRect(0, 0, t.width, t.height);
    return t;
  }

  // `ridisegna` serve perche' da EFFETTO_CURSORE spento non c'e' un ciclo che
  // ripassa: dopo un resize (o al primo caricamento) qualcuno deve richiamare il
  // disegno, altrimenti il canvas resta vuoto.
  function build() {
    if (!ready) return;
    DPR = Math.min(2, window.devicePixelRatio || 1);
    W = window.innerWidth; H = window.innerHeight;
    cv.width = W * DPR; cv.height = H * DPR;
    ctx.setTransform(DPR, 0, 0, DPR, 0, 0);
    cols = Math.ceil(W / CELL) + 1;
    rows = Math.ceil(H / CELL) + 1;
    var seed = 20240611;
    var rnd = function () { seed = (seed * 16807) % 2147483647; return (seed - 1) / 2147483646; };
    cells = [];
    for (var r = 0; r < rows; r++) for (var c = 0; c < cols; c++) {
      if (rnd() < DENSITY) {
        cells.push({
          x: c * CELL + CELL / 2, y: r * CELL + CELL / 2,
          g: (rnd() * grey.length) | 0,
          rot: ((rnd() * 4) | 0) * Math.PI / 2,
          // Opacita' COSTANTE, non piu' casuale fra 0.13 e 0.20. Misurato sul
          // riferimento: il 76% dei loro pixel opachi sta su un solo valore
          // (alpha 48 = 0.19), mentre da noi si spalmava fra 32 e 48. E' la
          // variazione casuale a far sembrare i simboli slavati invece che
          // netti: con un valore unico la texture torna "lucida".
          a: 0.19, ig: 0
        });
      } else {
        cells.push(null);
      }
    }
    base = document.createElement('canvas');
    base.width = W * DPR; base.height = H * DPR;
    var b = base.getContext('2d');
    b.setTransform(DPR, 0, 0, DPR, 0, 0);
    var d = DRAW * CELL;
    for (var i = 0; i < cells.length; i++) {
      var s = cells[i];
      if (!s) continue;
      b.save(); b.translate(s.x, s.y); b.rotate(s.rot);
      b.globalAlpha = s.a; b.drawImage(grey[s.g], -d / 2, -d / 2, d, d);
      b.restore();
    }
  }

  var mouse = { x: -9999, y: -9999, on: false };
  // Handler NOMINATI e non anonimi: servono a removeEventListener nella pulizia
  // in fondo. Senza, ogni rimontaggio del componente lascerebbe attivi un ciclo di
  // disegno e tre listener in piu'.
  function onMove(e) { mouse.x = e.clientX; mouse.y = e.clientY; mouse.on = true; }
  function onOut(e) { if (!e.relatedTarget) mouse.on = false; }
  if (EFFETTO_CURSORE) {
    window.addEventListener('mousemove', onMove, { passive: true });
    window.addEventListener('mouseout', onOut);
  }
  function ridisegna() { build(); if (!EFFETTO_CURSORE) requestAnimationFrame(frame); }
  window.addEventListener('resize', ridisegna);

  function frame() {
    if (!vivo) return;
    if (!ready) { requestAnimationFrame(frame); return; }
    ctx.clearRect(0, 0, W, H);
    ctx.drawImage(base, 0, 0, base.width, base.height, 0, 0, W, H);
    // Texture statica come il riferimento: disegnata una volta, nessun ciclo.
    if (!EFFETTO_CURSORE) return;
    var range = CELL * RANGE_CELLS, d = DRAW * CELL;

    if (mouse.on) {
      var halo = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, range);
      halo.addColorStop(0, 'rgba(' + HALO + ',0.10)');
      halo.addColorStop(0.6, 'rgba(' + HALO + ',0.035)');
      halo.addColorStop(1, 'rgba(' + HALO + ',0)');
      ctx.fillStyle = halo;
      ctx.fillRect(mouse.x - range, mouse.y - range, range * 2, range * 2);
    }

    for (var i = 0; i < cells.length; i++) {
      var s = cells[i];
      if (!s) continue;
      var target = 0;
      if (mouse.on) {
        var dist = Math.hypot(s.x - mouse.x, s.y - mouse.y);
        if (dist < range) target = Math.pow(1 - dist / range, 1.7);
      }
      s.ig += (target - s.ig) * (target > s.ig ? 0.35 : 0.10);
      if (s.ig < 0.02) continue;

      var rr = CELL * (0.7 + 1.3 * s.ig);
      var g = ctx.createRadialGradient(s.x, s.y, 0, s.x, s.y, rr);
      g.addColorStop(0, 'rgba(' + GLOW + ',' + (0.30 * s.ig).toFixed(3) + ')');
      g.addColorStop(1, 'rgba(' + GLOW + ',0)');
      ctx.fillStyle = g;
      ctx.beginPath(); ctx.arc(s.x, s.y, rr, 0, 6.2832); ctx.fill();

      ctx.save(); ctx.translate(s.x, s.y); ctx.rotate(s.rot);
      ctx.globalAlpha = Math.min(1, 0.25 + s.ig);
      ctx.drawImage(red[s.g], -d / 2, -d / 2, d, d);
      ctx.restore();
    }
    requestAnimationFrame(frame);
  }

  SRC.forEach(function (src, i) {
    var im = new Image();
    im.onload = function () {
      grey[i] = tint(im, '232,232,238');   // colore loro, estratto dal bundle
      red[i] = tint(im, GLOW);
      if (++loaded === SRC.length) { ready = true; ridisegna(); }
    };
    im.onerror = function () { if (++loaded === SRC.length) { ready = true; ridisegna(); } };
    im.src = src;
  });
  requestAnimationFrame(frame);

  // Pulizia restituita al componente React: ferma il ciclo e stacca i listener.
  return function ferma() {
    vivo = false;
    window.removeEventListener('mousemove', onMove);
    window.removeEventListener('mouseout', onOut);
    window.removeEventListener('resize', ridisegna);
  };
}
