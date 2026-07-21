import { render, screen } from '@testing-library/react'
import { PannelloDedup } from './Dashboard.jsx'

// Un run come lo scrive metriche.py; `accorpati_aggregatore` esiste solo dai
// run successivi al raggruppamento per storia (sez. 24).
function run(extra = {}) {
  return {
    dedup: {
      raccolti: 95, pubblicati: 87, duplicati_esatti: 6, duplicati_fuzzy: 0,
      aggiornamenti: 0, scartati_classificazione: 2, ...extra,
    },
  }
}

it('mostra le varianti accorpate quando ci sono', () => {
  render(<PannelloDedup runs={[run({ accorpati_aggregatore: 8 })]} />)
  expect(screen.getByText('varianti accorpate')).toBeInTheDocument()
  expect(screen.getByText('8')).toBeInTheDocument()
})

it('non mostra la voce quando non c e stato nulla da accorpare', () => {
  render(<PannelloDedup runs={[run({ accorpati_aggregatore: 0 })]} />)
  expect(screen.queryByText('varianti accorpate')).toBeNull()
})

it('regge i run vecchi che non hanno il campo, senza NaN', () => {
  // I record scritti prima della sez. 24 non hanno accorpati_aggregatore:
  // senza il "|| 0" la somma diventerebbe NaN e il pannello mostrerebbe "-".
  render(<PannelloDedup runs={[run()]} />)
  expect(screen.queryByText('varianti accorpate')).toBeNull()
  expect(screen.getByText(/87 pubblicati su 95 raccolti/)).toBeInTheDocument()
  expect(document.body.textContent).not.toMatch(/NaN/)
})

it('somma i contributi di piu run', () => {
  render(<PannelloDedup runs={[
    run({ accorpati_aggregatore: 8 }),
    run({ accorpati_aggregatore: 5 }),
    run(),                                  // run vecchio, non deve rompere
  ]} />)
  expect(screen.getByText('13')).toBeInTheDocument()
})
