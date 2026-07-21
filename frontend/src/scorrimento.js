import Lenis from 'lenis'

/* Scorrimento morbido (inerzia sulla rotella), come sui siti curati.
 *
 * NB: kakashi.ventures NON usa Lenis — verificato nei loro bundle (DECISIONI
 * §30.11). Questo non replica il riferimento, e' una scelta nostra sul "passo"
 * dell'interfaccia, chiesta esplicitamente.
 *
 * Lenis anima lo scroll REALE (scrollTop), non un transform: quindi
 * `window.scrollY`, `getBoundingClientRect()` e l'evento `scroll` continuano a
 * funzionare, e il segnaposto di lettura (lettura.js) non va toccato.
 */

/** Chi preferisce meno movimento non deve subire l'inerzia. */
function motoRidotto() {
  return window.matchMedia
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

export function avviaScorrimento() {
  if (motoRidotto()) return function () {}

  const lenis = new Lenis({
    duration: 0.9,          // inerzia percepibile ma non molle
    smoothWheel: true,
    // Il tocco resta quello nativo: su mobile l'inerzia del sistema e' migliore
    // di qualunque emulazione, e intercettarla peggiora sempre la sensazione.
    smoothTouch: false,
  })

  let vivo = true
  function frame(t) {
    if (!vivo) return
    lenis.raf(t)
    requestAnimationFrame(frame)
  }
  requestAnimationFrame(frame)

  return function ferma() {
    vivo = false
    lenis.destroy()
  }
}
