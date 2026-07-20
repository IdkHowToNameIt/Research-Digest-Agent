import { useCallback, useEffect, useRef, useState } from 'react'
import { usaChiusuraFuori } from '../usaChiusuraFuori.js'

/* jsPDF si porta dietro html2canvas e dompurify (~230 kB) per una funzione che
   non usiamo: il PDF si costruisce dai dati strutturati, non dal DOM. Con un
   import statico li scaricherebbe ogni visitatore, anche chi non esporta mai
   nulla. Con l'import dinamico il modulo arriva al primo click su "Scarica". */
const modulopdf = () => import('../pdf.js')

/* Fase 3 dell'export: un SOLO bottone "Scarica". Il click apre un popover con la
   scelta fra salvataggio locale e invio per email; scegliendo email compare il
   campo indirizzo. Si chiude cliccando fuori o con Esc.

   Prima erano due bottoni sempre visibili più un pannello email inline: la scelta
   occupava spazio nella testata anche per chi voleva solo scaricare il file. */

function IconaScarica() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 3v12" /><path d="M8 11l4 4 4-4" /><path d="M5 21h14" />
    </svg>
  )
}

function IconaEmail() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor"
      strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" />
    </svg>
  )
}

export default function ScaricaDigest({ tema, gruppo, articoli, invioEmailUrl }) {
  const [aperto, setAperto] = useState(false)
  const [modo, setModo] = useState(null)          // null | 'email'
  const [email, setEmail] = useState('')
  const [stato, setStato] = useState(null)        // {testo, cls}
  const [inCorso, setInCorso] = useState(false)

  const bottone = useRef(null)
  const popover = useRef(null)
  const campo = useRef(null)

  const chiudi = useCallback(() => {
    setAperto(false)
    setModo(null)
    setStato(null)
  }, [])

  usaChiusuraFuori(aperto, [bottone, popover], chiudi)

  // il campo email prende il fuoco appena compare: chi ha scelto "email" vuole scrivere
  useEffect(() => { if (modo === 'email' && campo.current) campo.current.focus() }, [modo])

  const scaricaInLocale = async () => {
    setInCorso(true)
    try {
      const { scaricaPdf } = await modulopdf()
      await scaricaPdf(tema, gruppo, articoli)
      chiudi()
    } catch (e) {
      setStato({ testo: 'Non è stato possibile generare il PDF (' + ((e && e.message) || e) + ').', cls: 'ko' })
    } finally {
      setInCorso(false)
    }
  }

  const invia = async () => {
    setInCorso(true)
    setStato({ testo: 'Invio in corso…', cls: 'loading' })
    const { inviaPdfEmail } = await modulopdf()
    const esito = await inviaPdfEmail(invioEmailUrl, email.trim(), tema, gruppo, articoli)
    setInCorso(false)
    if (esito.ok) {
      setStato({ testo: 'Inviato a ' + email.trim() + '.', cls: 'ok' })
      setEmail('')
    } else {
      setStato({ testo: esito.errore, cls: 'ko' })
      if (campo.current) campo.current.focus()
    }
  }

  return (
    <div className="scarica-wrap">
      <button
        ref={bottone}
        className="btn-pdf"
        aria-haspopup="dialog"
        aria-expanded={aperto}
        onClick={() => (aperto ? chiudi() : setAperto(true))}
        title="Scarica questo digest"
      >
        <IconaScarica />
        <span>Scarica</span>
      </button>

      {aperto && (
        <div className="scarica-pop" ref={popover} role="dialog" aria-label="Scarica il digest">
          {modo !== 'email' && (
            <>
              <button className="scarica-voce" disabled={inCorso} onClick={scaricaInLocale}>
                <IconaScarica />
                <span>
                  <strong>Salva sul dispositivo</strong>
                  <em>File PDF</em>
                </span>
              </button>
              {/* la voce email compare solo se il Worker è configurato: senza URL
                  offrirla vorrebbe dire promettere un invio che non può partire */}
              {invioEmailUrl && (
                <button className="scarica-voce" onClick={() => { setModo('email'); setStato(null) }}>
                  <IconaEmail />
                  <span>
                    <strong>Ricevi via email</strong>
                    <em>Allegato PDF</em>
                  </span>
                </button>
              )}
            </>
          )}

          {modo === 'email' && (
            <div className="scarica-mail">
              <label className="scarica-lbl" htmlFor="mail-input">Indirizzo email</label>
              <div className="scarica-mail-riga">
                <input
                  id="mail-input"
                  ref={campo}
                  type="email"
                  inputMode="email"
                  autoComplete="email"
                  placeholder="tua@email.it"
                  value={email}
                  disabled={inCorso}
                  onChange={(e) => setEmail(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter') invia() }}
                />
                <button className="btn-pdf mail-send" disabled={inCorso} onClick={invia}>
                  <span>Invia</span>
                </button>
              </div>
              <button className="scarica-indietro" onClick={() => { setModo(null); setStato(null) }}>
                ← Torna alla scelta
              </button>
            </div>
          )}

          {stato && (
            <span className={'mail-stato ' + stato.cls} role="status" aria-live="polite">
              {stato.testo}
            </span>
          )}
        </div>
      )}
    </div>
  )
}
