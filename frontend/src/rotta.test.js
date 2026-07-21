import { HOME, aHash, daHash } from './rotta.js'

describe('daHash', () => {
  it('legge le quattro viste', () => {
    expect(daHash('')).toEqual(HOME)
    expect(daHash('#/')).toEqual(HOME)
    expect(daHash('#/dashboard')).toEqual({ tipo: 'dashboard' })
    expect(daHash('#/tema/chip')).toEqual({ tipo: 'tema', temaId: 'chip' })
    expect(daHash('#/tema/data_center/2026-07-15')).toEqual({
      tipo: 'gruppo', temaId: 'data_center', data: '2026-07-15',
    })
  })

  it('tollera hash senza barra iniziale e con barre in eccesso', () => {
    expect(daHash('#tema/chip')).toEqual({ tipo: 'tema', temaId: 'chip' })
    expect(daHash('#//tema//chip//')).toEqual({ tipo: 'tema', temaId: 'chip' })
  })

  it('ricade sulla home su qualunque cosa non riconosciuta', () => {
    // L'URL e' modificabile a mano: non deve portare l'app in uno stato illegale.
    for (const h of ['#/pippo', '#/tema', '#/tema/', '#/%%%', '#/../etc']) {
      expect(daHash(h).tipo).toBe('home')
    }
  })

  it('non esplode su una sequenza percent-encoded non valida', () => {
    expect(() => daHash('#/tema/%E0%A4%A')).not.toThrow()
  })
})

describe('aHash', () => {
  it('serializza le quattro viste', () => {
    expect(aHash(HOME)).toBe('#/')
    expect(aHash({ tipo: 'dashboard' })).toBe('#/dashboard')
    expect(aHash({ tipo: 'tema', temaId: 'chip' })).toBe('#/tema/chip')
    expect(aHash({ tipo: 'gruppo', temaId: 'chip', data: '2026-07-15' }))
      .toBe('#/tema/chip/2026-07-15')
  })

  it('e inverso di daHash per ogni vista raggiungibile', () => {
    const viste = [
      HOME,
      { tipo: 'dashboard' },
      { tipo: 'tema', temaId: 'cloud_capacity' },
      { tipo: 'gruppo', temaId: 'supply_chain', data: '2026-06-17' },
    ]
    for (const v of viste) expect(daHash(aHash(v))).toEqual(v)
  })

  it('regge una vista incompleta senza produrre un hash rotto', () => {
    expect(aHash(null)).toBe('#/')
    expect(aHash({ tipo: 'tema' })).toBe('#/')
  })
})
