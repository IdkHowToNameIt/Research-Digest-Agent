import { LINEA, indiceAttivo } from './lettura.js'

const LINEA_PX = 200   // finestra da 800px con LINEA = 0.25

it('la linea di lettura e un quarto della finestra', () => {
  expect(LINEA).toBe(0.25)
})

it('segue la voce piu recente che ha superato la linea', () => {
  //            0     1     2
  const cime = [-500, -120, 350]
  expect(indiceAttivo(cime, LINEA_PX, false)).toBe(1)
})

it('in cima alla pagina resta sulla prima voce', () => {
  // Nessuna voce ha ancora superato la linea: prima il segnaposto restava
  // bloccato sull'ultimo valore e "non tornava su".
  expect(indiceAttivo([320, 900, 1500], LINEA_PX, false)).toBe(0)
})

it('in fondo alla pagina arriva sempre allultima voce', () => {
  // Il caso che si bloccava: scorrendo in fondo le ultime voci non superano
  // mai la linea, perche' la pagina non puo' scorrere oltre.
  expect(indiceAttivo([-2000, -1500, 400, 600], LINEA_PX, true)).toBe(3)
})

it('una voce esattamente sulla linea e gia quella in lettura', () => {
  expect(indiceAttivo([-100, LINEA_PX, 900], LINEA_PX, false)).toBe(1)
})

it('segue la lettura scorrendo, e torna indietro risalendo', () => {
  // Le cime crescono sempre in ordine di documento: si simula lo scroll
  // sottraendo la stessa quantita' a tutte.
  const iniziali = [300, 900, 1600]
  const dopoScroll = (px) => iniziali.map((c) => c - px)
  expect(indiceAttivo(dopoScroll(0), LINEA_PX, false)).toBe(0)      // in cima
  expect(indiceAttivo(dopoScroll(800), LINEA_PX, false)).toBe(1)    // seconda
  expect(indiceAttivo(dopoScroll(1500), LINEA_PX, false)).toBe(2)   // terza
  expect(indiceAttivo(dopoScroll(800), LINEA_PX, false)).toBe(1)    // risalendo
  expect(indiceAttivo(dopoScroll(0), LINEA_PX, false)).toBe(0)      // di nuovo in cima
})

it('regge la lista vuota', () => {
  expect(indiceAttivo([], LINEA_PX, false)).toBe(-1)
  expect(indiceAttivo([], LINEA_PX, true)).toBe(-1)
})
