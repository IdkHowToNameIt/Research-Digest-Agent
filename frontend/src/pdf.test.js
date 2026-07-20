/* Esportazione PDF. Due cose da presidiare:
   1. `sanifica` — il fix dei caratteri fuori cp1252 (DECISIONI §16): senza, una
      riga intera esce con le lettere spaziate e tagliata fuori pagina.
   2. l'API di jsPDF, salita da 2.5.2 a 4.x nella migrazione a React. Qui il PDF
      viene generato davvero: se una firma fosse cambiata, questi test cadono. */
import { describe, it, expect, vi } from 'vitest'
import { EMAIL_VALIDA, creaDocGruppo, inviaPdfEmail, nomeFile, sanifica } from './pdf.js'

const TEMA = { id: 'chip', nome: 'Chip' }
const GRUPPO = { data: '2026-07-20', titolo: 'Digest di prova', n: 2, minuti: 4 }
const ARTICOLI = [
  {
    titolo: 'Primo articolo',
    fonte: 'Fonte A',
    fonti: [{ nome: 'Fonte A', link: 'https://esempio.test/1' }],
    data: '2026-07-20',
    sintesi: 'Sintesi del primo.',
    perche: 'Conta perché sì.',
    nota: null,
  },
  {
    titolo: 'Secondo articolo',
    fonte: 'Fonte B',
    fonti: [{ nome: 'Fonte B' }],
    data: '2026-07-19',
    sintesi: 'Sintesi del secondo.',
    perche: 'Anche questo conta.',
    nota: 'Nota interna di prova',
  },
]

describe('sanifica', () => {
  it('sostituisce i caratteri che rompevano la riga', () => {
    // U+2011 e U+202F sono i due colpevoli trovati nel PDF del 2026-07-19
    expect(sanifica('AI‑ready')).toBe('AI-ready')
    expect(sanifica('300 MW')).toBe('300 MW')
  })

  it('lascia intatto ciò che i font standard sanno già rendere', () => {
    expect(sanifica('Perché è così: «città» —  è ok')).toBe('Perché è così: «città» —  è ok')
  })

  it('toglie i caratteri a larghezza zero invece di stamparli', () => {
    expect(sanifica('a​b﻿c')).toBe('abc')
  })

  it('scompone gli accenti esotici invece di perdere la riga', () => {
    // il ripiego NFKD: meglio la lettera base che una riga illeggibile
    expect(sanifica('ǘ')).toBe('u')
  })

  it('regge null e undefined senza esplodere', () => {
    expect(sanifica(null)).toBe('')
    expect(sanifica(undefined)).toBe('')
  })
})

describe('nomeFile', () => {
  it('produce un nome sicuro per il filesystem', () => {
    expect(nomeFile({ id: 'chip' }, { data: '2026-07-20' })).toBe('DRA_chip_2026-07-20.pdf')
  })

  it('ripiega su segnaposti se i dati mancano', () => {
    expect(nomeFile({}, {})).toBe('DRA_digest_giorno.pdf')
  })
})

describe('creaDocGruppo (API jsPDF 4.x)', () => {
  it('genera un PDF vero dai dati del gruppo', async () => {
    const { doc, filename } = await creaDocGruppo(TEMA, GRUPPO, ARTICOLI)
    expect(filename).toBe('DRA_chip_2026-07-20.pdf')
    const uri = doc.output('datauristring')
    expect(uri.startsWith('data:application/pdf')).toBe(true)
    // un PDF con due articoli non può pesare una manciata di byte
    expect(uri.length).toBeGreaterThan(2000)
  })

  it('si rifiuta di generare senza articoli, invece di produrre un PDF vuoto', async () => {
    await expect(creaDocGruppo(TEMA, GRUPPO, [])).rejects.toThrow('Nessun digest aperto')
  })
})

describe('inviaPdfEmail', () => {
  it('rifiuta un indirizzo non valido senza chiamare la rete', async () => {
    const fetchFinto = vi.fn()
    const esito = await inviaPdfEmail('https://w.test', 'non-una-email', TEMA, GRUPPO, ARTICOLI, fetchFinto)
    expect(esito.ok).toBe(false)
    expect(fetchFinto).not.toHaveBeenCalled()
  })

  it('senza URL del Worker non promette un invio che non può partire', async () => {
    const esito = await inviaPdfEmail('', 'a@b.it', TEMA, GRUPPO, ARTICOLI)
    expect(esito.ok).toBe(false)
    expect(esito.errore).toContain('non configurato')
  })

  it('manda il PDF in base64 puro, senza il prefisso data:', async () => {
    const fetchFinto = vi.fn(async () => ({ ok: true, json: async () => ({ ok: true }) }))
    const esito = await inviaPdfEmail('https://w.test', 'a@b.it', TEMA, GRUPPO, ARTICOLI, fetchFinto)
    expect(esito.ok).toBe(true)
    const corpo = JSON.parse(fetchFinto.mock.calls[0][1].body)
    expect(corpo.pdf.startsWith('data:')).toBe(false)
    expect(corpo.pdf.length).toBeGreaterThan(100)
    expect(corpo.filename).toBe('DRA_chip_2026-07-20.pdf')
  })

  it('riporta l\'errore del Worker invece di dire genericamente "non riuscito"', async () => {
    const fetchFinto = async () => ({ ok: false, json: async () => ({ errore: 'Quota esaurita' }) })
    const esito = await inviaPdfEmail('https://w.test', 'a@b.it', TEMA, GRUPPO, ARTICOLI, fetchFinto)
    expect(esito).toEqual({ ok: false, errore: 'Quota esaurita' })
  })

  it('una rete giù diventa un messaggio, non un\'eccezione', async () => {
    const fetchFinto = async () => { throw new Error('offline') }
    const esito = await inviaPdfEmail('https://w.test', 'a@b.it', TEMA, GRUPPO, ARTICOLI, fetchFinto)
    expect(esito.ok).toBe(false)
    expect(esito.errore).toContain('Rete non disponibile')
  })
})

describe('EMAIL_VALIDA', () => {
  it('accetta gli indirizzi normali e rifiuta le forme monche', () => {
    expect(EMAIL_VALIDA.test('mario.rossi@example.it')).toBe(true)
    expect(EMAIL_VALIDA.test('senza-chiocciola.it')).toBe(false)
    expect(EMAIL_VALIDA.test('a@b')).toBe(false)
    expect(EMAIL_VALIDA.test('con spazio@b.it')).toBe(false)
  })
})
