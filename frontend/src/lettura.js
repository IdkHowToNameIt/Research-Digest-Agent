/* Quale voce dell'indice e' "in lettura", dato dove sono le voci sullo schermo.
 *
 * Estratta come funzione pura per poterla provare senza un layout vero: in jsdom
 * gli elementi non hanno geometria, quindi la logica non sarebbe verificabile se
 * restasse dentro l'effetto.
 */

/** Frazione dell'altezza della finestra usata come linea di lettura. */
export const LINEA = 0.25

/**
 * Linea di lettura, che SCENDE nell'ultimo tratto di pagina.
 *
 * Le ultime voci non possono mai raggiungere una linea fissa al 25%: quando la
 * pagina e' in fondo non c'e' piu' scroll da consumare. Tenendo la linea fissa
 * il segnaposto si ferma (si bloccava alla 5 su 8); forzando l'ultima voce
 * quando si tocca il fondo salta invece direttamente all'8, e la 6 e la 7 non
 * compaiono mai. Qui la linea scivola in proporzione a quanto scroll resta:
 * lontano dal fondo sta al 25%, sul fondo esatto coincide col bordo inferiore,
 * cosi' le ultime voci si accendono una dopo l'altra.
 */
export function lineaLettura(altezzaFinestra, restanteScroll) {
  const usato = Math.max(0, altezzaFinestra - Math.max(0, restanteScroll))
  return LINEA * altezzaFinestra + usato * (1 - LINEA)
}

/**
 * @param {number[]} cime   posizione verticale di ogni voce rispetto alla finestra
 * @param {number}   altezzaFinestra
 * @param {number}   restanteScroll pixel di scroll ancora disponibili
 * @returns {number} indice della voce attiva, -1 se non ci sono voci
 */
export function indiceAttivo(cime, altezzaFinestra, restanteScroll) {
  if (!cime.length) return -1
  const linea = lineaLettura(altezzaFinestra, restanteScroll)
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
