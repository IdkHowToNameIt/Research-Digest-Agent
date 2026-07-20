/* Livello dati: proiezione, formattazione e filtro periodo.
   Diversi di questi casi sono regressioni di errori fatti DURANTE la migrazione
   da app.js: il comportamento va riprodotto, non reinventato. */
import { describe, it, expect } from 'vitest'
import {
  caricaIndice,
  caricaTema,
  conVersione,
  filtraPerPeriodo,
  filtroPeriodoAttivo,
  fmtEuro,
  fmtLettura,
  mapArt,
} from './dati.js'

function rispostaFinta(payload, ok = true) {
  return async () => ({ ok, status: ok ? 200 : 404, json: async () => payload })
}

describe('mapArt', () => {
  it('unisce i nomi delle fonti con il separatore a punto medio', () => {
    const a = mapArt({ titolo: 'T', fonti: [{ nome: 'A' }, { nome: 'B' }] })
    expect(a.fonte).toBe('A · B')
    expect(a.fonti).toHaveLength(2)
  })

  it('regge un articolo senza fonti né note', () => {
    const a = mapArt({ titolo: 'T' })
    expect(a.fonte).toBe('')
    expect(a.nota).toBeNull()
  })
})

describe('fmtEuro', () => {
  it('usa due decimali per i costi normali', () => {
    expect(fmtEuro(1.5)).toBe('€ 1,50')
  })

  it('non collassa a zero i costi sotto il centesimo', () => {
    // il free tier produce costi stimati minuscoli: "€ 0,00" farebbe sembrare
    // che non ci sia alcun costo.
    const testo = fmtEuro(0.000123)
    expect(testo).not.toBe('€ 0,00')
    expect(testo).toContain('0,000123')
  })

  it('mostra zero come zero, non con sei decimali', () => {
    expect(fmtEuro(0)).toBe('€ 0,00')
  })
})

describe('filtraPerPeriodo', () => {
  const items = [
    { data: '2026-07-20', giorni: 0 },
    { data: '2026-07-10', giorni: 10 },
    { data: '2026-05-01', giorni: 80 },
  ]

  it('"all" non filtra nulla', () => {
    expect(filtraPerPeriodo(items, { val: 'all', dal: '', al: '' })).toHaveLength(3)
  })

  it('la pill a giorni taglia per anzianità', () => {
    const out = filtraPerPeriodo(items, { val: '30', dal: '', al: '' })
    expect(out.map((x) => x.data)).toEqual(['2026-07-20', '2026-07-10'])
  })

  it('"run" tiene solo la data più recente, non un intervallo', () => {
    const out = filtraPerPeriodo(items, { val: 'run', dal: '', al: '' })
    expect(out).toEqual([{ data: '2026-07-20', giorni: 0 }])
  })

  it('pill e date si combinano in AND, nessuna prevale', () => {
    // errore commesso durante la migrazione: avevo dato la precedenza alle date,
    // ignorando la pill quando entrambe erano attive.
    const out = filtraPerPeriodo(items, { val: '30', dal: '2026-07-15', al: '' })
    expect(out.map((x) => x.data)).toEqual(['2026-07-20'])
  })

  it('l\'intervallo Dal/Al taglia da entrambi i lati', () => {
    const out = filtraPerPeriodo(items, { val: 'all', dal: '2026-06-01', al: '2026-07-15' })
    expect(out.map((x) => x.data)).toEqual(['2026-07-10'])
  })
})

describe('filtroPeriodoAttivo', () => {
  it('è spento solo con pill "all" e nessuna data', () => {
    expect(filtroPeriodoAttivo({ val: 'all', dal: '', al: '' })).toBe(false)
    expect(filtroPeriodoAttivo({ val: '7', dal: '', al: '' })).toBe(true)
    expect(filtroPeriodoAttivo({ val: 'all', dal: '2026-01-01', al: '' })).toBe(true)
  })
})

describe('conVersione', () => {
  it('aggiunge il token del run ai file dati', () => {
    // gli asset dell'app hanno l'hash nel nome (Vite), i JSON no: stesso nome a
    // ogni run. Senza questo il browser servirebbe il digest della settimana prima.
    expect(conVersione('tema-chip.json', '2026-07-20')).toBe('tema-chip.json?v=2026-07-20')
  })

  it('senza token lascia il nome pulito', () => {
    expect(conVersione('tema-chip.json', '')).toBe('tema-chip.json')
  })
})

describe('caricaIndice', () => {
  it('normalizza temi e soglie', async () => {
    const idx = await caricaIndice(rispostaFinta({
      generato: '2026-07-20',
      badge_giorni: 3,
      invio_email_url: 'https://worker.example',
      temi: [{ id: 'chip', nome: 'Chip', recenti: [{ data: '2026-07-20', n_articoli: 4 }] }],
    }))
    expect(idx.generato).toBe('2026-07-20')
    expect(idx.sogliaNuovo).toBe(3)
    expect(idx.invioEmailUrl).toBe('https://worker.example')
    expect(idx.temi[0].file).toBe('tema-chip.json')
    expect(idx.temi[0].recenti[0].n).toBe(4)
  })

  it('applica i default quando le soglie mancano', async () => {
    const idx = await caricaIndice(rispostaFinta({ temi: [] }))
    expect(idx.sogliaNuovo).toBe(2)
    expect(idx.sogliaSettimana).toBe(7)
    expect(idx.invioEmailUrl).toBe('')
  })

  it('solleva su risposta non ok, così la UI mostra il messaggio di attesa', async () => {
    await expect(caricaIndice(rispostaFinta({}, false))).rejects.toThrow('HTTP 404')
  })
})

describe('caricaTema', () => {
  it('conserva le anteprime dei titoli', async () => {
    // dimenticate alla prima stesura: la landing le usa nei box dei temi.
    const gruppi = await caricaTema(
      { id: 'chip', file: 'tema-chip.json' },
      '2026-07-20',
      rispostaFinta({ gruppi: [{ data: '2026-07-20', anteprima_titoli: ['uno', 'due'] }] }),
    )
    expect(gruppi[0].anteprima).toEqual(['uno', 'due'])
  })
})

describe('fmtLettura', () => {
  it('tace quando la stima è zero', () => {
    expect(fmtLettura(0)).toBe('')
    expect(fmtLettura(3)).toBe('~3 min di lettura')
  })
})
