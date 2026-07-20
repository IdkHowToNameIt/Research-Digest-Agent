/* Fase 3: un solo bottone "Scarica", che apre un popover con la scelta fra
   locale ed email; il campo indirizzo compare solo scegliendo email; si chiude
   cliccando fuori o con Esc. */
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ScaricaDigest from './ScaricaDigest.jsx'

const TEMA = { id: 'chip', nome: 'Chip' }
const GRUPPO = { data: '2026-07-20', titolo: 'Digest', n: 1, minuti: 2 }
const ARTICOLI = [{
  titolo: 'A', fonte: 'F', fonti: [{ nome: 'F' }],
  data: '2026-07-20', sintesi: 's', perche: 'p', nota: null,
}]

function montaggio(props = {}) {
  return render(
    <div>
      <button>fuori</button>
      <ScaricaDigest
        tema={TEMA}
        gruppo={GRUPPO}
        articoli={ARTICOLI}
        invioEmailUrl="https://worker.test"
        {...props}
      />
    </div>,
  )
}

describe('ScaricaDigest', () => {
  it('mostra un solo bottone, senza le scelte, finché non si clicca', () => {
    montaggio()
    expect(screen.getByRole('button', { name: /scarica/i })).toBeInTheDocument()
    expect(screen.queryByText(/salva sul dispositivo/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/ricevi via email/i)).not.toBeInTheDocument()
  })

  it('al click apre il popover con le due scelte', async () => {
    const utente = userEvent.setup()
    montaggio()
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/salva sul dispositivo/i)).toBeInTheDocument()
    expect(screen.getByText(/ricevi via email/i)).toBeInTheDocument()
  })

  it('il campo email NON c\'è finché non si sceglie email', async () => {
    const utente = userEvent.setup()
    montaggio()
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    expect(screen.queryByPlaceholderText(/tua@email/i)).not.toBeInTheDocument()

    await utente.click(screen.getByText(/ricevi via email/i))
    expect(screen.getByPlaceholderText(/tua@email/i)).toBeInTheDocument()
  })

  it('cliccando fuori il popover si chiude', async () => {
    const utente = userEvent.setup()
    montaggio()
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()

    await utente.click(screen.getByRole('button', { name: 'fuori' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('cliccando DENTRO il popover resta aperto', async () => {
    // regressione: escludendo solo il pannello e non il bottone che lo apre, il
    // click di apertura veniva riletto come "click fuori" e non apriva mai nulla.
    const utente = userEvent.setup()
    montaggio()
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    await utente.click(screen.getByText(/ricevi via email/i))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
  })

  it('Esc chiude il popover', async () => {
    const utente = userEvent.setup()
    montaggio()
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    await utente.keyboard('{Escape}')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('si può tornare dalla mail alla scelta iniziale', async () => {
    const utente = userEvent.setup()
    montaggio()
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    await utente.click(screen.getByText(/ricevi via email/i))
    await utente.click(screen.getByText(/torna alla scelta/i))
    expect(screen.getByText(/salva sul dispositivo/i)).toBeInTheDocument()
    expect(screen.queryByPlaceholderText(/tua@email/i)).not.toBeInTheDocument()
  })

  it('senza Worker configurato non offre l\'email', async () => {
    // offrirla vorrebbe dire promettere un invio che non può partire
    const utente = userEvent.setup()
    montaggio({ invioEmailUrl: '' })
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    expect(screen.getByText(/salva sul dispositivo/i)).toBeInTheDocument()
    expect(screen.queryByText(/ricevi via email/i)).not.toBeInTheDocument()
  })

  it('riapre pulito dopo la chiusura, senza restare sulla schermata email', async () => {
    const utente = userEvent.setup()
    montaggio()
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    await utente.click(screen.getByText(/ricevi via email/i))
    await utente.keyboard('{Escape}')
    await utente.click(screen.getByRole('button', { name: /scarica/i }))
    expect(screen.getByText(/salva sul dispositivo/i)).toBeInTheDocument()
  })
})
