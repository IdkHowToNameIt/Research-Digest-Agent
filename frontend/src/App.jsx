import { useCallback, useEffect, useRef, useState } from 'react'
import { caricaAnno, caricaIndice, caricaTema } from './dati.js'
import { HOME, aHash, daHash } from './rotta.js'
import { avviaScorrimento } from './scorrimento.js'
import Sfondo from './componenti/Sfondo.jsx'
import Intestazione from './componenti/Intestazione.jsx'
import Home from './componenti/Home.jsx'
import ListaGruppi from './componenti/ListaGruppi.jsx'
import ArticoliGruppo from './componenti/ArticoliGruppo.jsx'
import Dashboard from './componenti/Dashboard.jsx'

/* Guscio dell'app: tiene i dati dell'indice, la vista corrente e la cache dei
   dettagli caricati on-demand. La navigazione è a 3 livelli (home -> lista di un
   tema -> digest di un giorno) più la dashboard, come nell'originale. */

export default function App() {
  const [indice, setIndice] = useState(null)
  const [errore, setErrore] = useState('')
  // La vista vive nell'URL: al refresh si riparte da dove si era, e i tasti
  // avanti/indietro del browser funzionano senza codice aggiuntivo.
  const [vista, setVista] = useState(() => daHash(window.location.hash))

  // Cache di sessione: { [temaId]: {gruppi, dettaglio: {data: articoli}, anni:{}} }
  // in un ref e non in stato — riempirla non deve provocare un render da sola.
  const cache = useRef({})

  useEffect(() => {
    let vivo = true
    caricaIndice()
      .then((idx) => { if (vivo) setIndice(idx) })
      .catch((err) => { if (vivo) setErrore(err.message) })
    return () => { vivo = false }
  }, [])

  // L'hash e' l'unica fonte di verita': si naviga scrivendolo, e lo stato lo
  // segue dall'evento. Cosi' un click e un "indietro" del browser passano
  // esattamente per la stessa strada.
  // Scorrimento morbido per tutta l'app, fermato allo smontaggio.
  useEffect(() => avviaScorrimento(), [])

  useEffect(() => {
    const suHash = () => setVista(daHash(window.location.hash))
    window.addEventListener('hashchange', suHash)
    return () => window.removeEventListener('hashchange', suHash)
  }, [])

  const vai = useCallback((prossima) => {
    const hash = aHash(prossima)
    window.scrollTo(0, 0)
    if (window.location.hash === hash) {
      setVista(prossima)          // stesso hash: nessun evento, si aggiorna qui
    } else {
      window.location.hash = hash
    }
  }, [])

  const vaiHome = useCallback(() => vai(HOME), [vai])
  const vaiTema = useCallback((temaId) => vai({ tipo: 'tema', temaId }), [vai])
  const vaiGruppo = useCallback(
    (temaId, data) => vai({ tipo: 'gruppo', temaId, data }), [vai],
  )
  const vaiDashboard = useCallback(() => vai({ tipo: 'dashboard' }), [vai])

  /** Gruppi di un tema (lista leggera), una volta sola per sessione. */
  const gruppiDelTema = useCallback(async (tema) => {
    const voce = cache.current[tema.id] || (cache.current[tema.id] = {})
    if (!voce.gruppi) {
      voce.gruppi = await caricaTema(tema, indice.generato)
    }
    return voce.gruppi
  }, [indice])

  /** Corpi degli articoli di un giorno: un fetch per ANNO, riusato per gli altri
   *  giorni dello stesso anno. */
  const articoliDelGiorno = useCallback(async (tema, data) => {
    const voce = cache.current[tema.id] || (cache.current[tema.id] = {})
    if (!voce.dettaglio) voce.dettaglio = {}
    if (!voce.anni) voce.anni = {}
    const anno = (data || '').slice(0, 4)
    if (!voce.anni[anno]) {
      const perData = await caricaAnno(tema.id, anno, indice.generato)
      Object.assign(voce.dettaglio, perData)
      voce.anni[anno] = true
    }
    return voce.dettaglio[data] || []
  }, [indice])

  if (errore) {
    return (
      <>
        <Sfondo />
        <Intestazione onHome={vaiHome} onDashboard={vaiDashboard} />
        <div id="app">
          <section className="view home">
            <div className="hero">
              <div className="kicker">Digest settimanale interno</div>
              <h1 className="title">Digest Research Agent</h1>
              <p className="sub">
                Dati non ancora disponibili ({errore}). Il digest viene rigenerato ogni settimana.
              </p>
            </div>
          </section>
        </div>
      </>
    )
  }

  if (!indice) {
    return (
      <>
        <Sfondo />
        <Intestazione onHome={vaiHome} onDashboard={vaiDashboard} />
        <div id="app" />
      </>
    )
  }

  // L'hash e' modificabile a mano e l'archivio cambia a ogni run: un tema che
  // non esiste piu' non deve lasciare la pagina bianca.
  const tema = vista.temaId ? indice.temi.find((t) => t.id === vista.temaId) : null
  const vistaEffettiva = vista.temaId && !tema ? HOME : vista

  return (
    <>
      <Sfondo />
      <Intestazione onHome={vaiHome} onDashboard={vaiDashboard} />
      <div id="app">
        {vistaEffettiva.tipo === 'home' && (
          <Home indice={indice} onTema={vaiTema} />
        )}
        {vistaEffettiva.tipo === 'tema' && (
          <ListaGruppi
            tema={tema}
            indice={indice}
            caricaGruppi={gruppiDelTema}
            onHome={vaiHome}
            onGruppo={vaiGruppo}
          />
        )}
        {vistaEffettiva.tipo === 'gruppo' && (
          <ArticoliGruppo
            tema={tema}
            data={vistaEffettiva.data}
            indice={indice}
            caricaGruppi={gruppiDelTema}
            caricaArticoli={articoliDelGiorno}
            onHome={vaiHome}
            onTema={vaiTema}
          />
        )}
        {vistaEffettiva.tipo === 'dashboard' && (
          <Dashboard indice={indice} onHome={vaiHome} />
        )}
      </div>
    </>
  )
}
