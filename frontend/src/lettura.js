/* Quale voce dell'indice e' "in lettura", dato dove sono le voci sullo schermo.
 *
 * Estratta come funzione pura per poterla provare senza un layout vero: in jsdom
 * gli elementi non hanno geometria, quindi la logica non sarebbe verificabile se
 * restasse dentro l'effetto.
 */

/** Frazione dell'altezza della finestra usata come linea di lettura. */
export const LINEA = 0.25

/**
 * @param {number[]} cime  posizione verticale di ogni voce rispetto alla finestra
 * @param {number}   linea coordinata della linea di lettura
 * @param {boolean}  inFondo pagina scrollata fino in fondo
 * @returns {number} indice della voce attiva
 */
export function indiceAttivo(cime, linea, inFondo) {
  if (!cime.length) return -1
  // In fondo alla pagina le ultime voci non raggiungono mai la linea: senza
  // questo caso il segnaposto si ferma a meta' e non arriva mai all'ultima.
  if (inFondo) return cime.length - 1
  let scelto = 0
  for (let i = 0; i < cime.length; i++) {
    // <= e non <: una voce esattamente sulla linea e' gia' quella in lettura.
    if (cime[i] <= linea) scelto = i
    else break
  }
  // Nessuna voce ha superato la linea (siamo sopra la prima): resta la prima,
  // cosi' tornando in cima il segnaposto risale invece di restare bloccato.
  return scelto
}
