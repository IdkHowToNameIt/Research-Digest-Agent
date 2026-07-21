import { LINEA, indiceAttivo, lineaLettura } from './lettura.js'

const H = 800          // altezza finestra
const LONTANO = 5000   // scroll rimanente: siamo lontani dal fondo

it('la linea di lettura e un quarto della finestra', () => {
  expect(LINEA).toBe(0.25)
})

describe('lineaLettura', () => {
  it('lontano dal fondo sta al 25%', () => {
    expect(lineaLettura(H, LONTANO)).toBe(200)
  })

  it('sul fondo esatto coincide col bordo inferiore', () => {
    // Cosi' l'ultima voce e' raggiungibile: e' il caso che prima si bloccava.
    expect(lineaLettura(H, 0)).toBe(H)
  })

  it('scivola in proporzione nell ultimo tratto', () => {
    expect(lineaLettura(H, H / 2)).toBe(200 + 400 * 0.75)
  })
})

describe('indiceAttivo', () => {
  it('segue la voce piu recente che ha superato la linea', () => {
    expect(indiceAttivo([-500, -120, 350], H, LONTANO)).toBe(1)
  })

  it('in cima alla pagina resta sulla prima voce', () => {
    // Prima il segnaposto restava bloccato sull'ultimo valore e non risaliva.
    expect(indiceAttivo([320, 900, 1500], H, LONTANO)).toBe(0)
  })

  it('nell ultimo tratto accende le ultime voci UNA A UNA', () => {
    // Il difetto segnalato: da 1 a 5 andava, poi saltava dritto all'8.
    // Otto voci, le ultime tre visibili insieme nella schermata finale.
    const cime = [-2400, -2000, -1600, -1200, -800, 100, 400, 700]
    expect(indiceAttivo(cime, H, 600)).toBe(5)   // ancora scroll disponibile
    expect(indiceAttivo(cime, H, 300)).toBe(6)   // piu' vicino al fondo
    expect(indiceAttivo(cime, H, 0)).toBe(7)     // fondo esatto
  })

  it('sul fondo non salta all ultima se le voci sono ancora lontane', () => {
    // Voce fuori schermo in basso: nemmeno col fondo raggiunto va scelta.
    expect(indiceAttivo([-200, 400, 2000], H, 0)).toBe(1)
  })

  it('segue la lettura scorrendo, e torna indietro risalendo', () => {
    const iniziali = [300, 900, 1600]
    const dopo = (px) => iniziali.map((c) => c - px)
    expect(indiceAttivo(dopo(0), H, LONTANO)).toBe(0)
    expect(indiceAttivo(dopo(800), H, LONTANO)).toBe(1)
    expect(indiceAttivo(dopo(1500), H, LONTANO)).toBe(2)
    expect(indiceAttivo(dopo(800), H, LONTANO)).toBe(1)
    expect(indiceAttivo(dopo(0), H, LONTANO)).toBe(0)
  })

  it('regge la lista vuota', () => {
    expect(indiceAttivo([], H, LONTANO)).toBe(-1)
    expect(indiceAttivo([], H, 0)).toBe(-1)
  })
})
