import { useCallback, useEffect, useRef, useState } from 'react'
import { caricaAnno, caricaIndice, caricaTema } from './dati.js'
import Sfondo from './componenti/Sfondo.jsx'
import Intestazione from './componenti/Intestazione.jsx'
import Home from './componenti/Home.jsx'
import ListaGruppi from './componenti/ListaGruppi.jsx'
import ArticoliGruppo from './componenti/ArticoliGruppo.jsx'
import Dashboard from './componenti/Dashboard.jsx'

/* Guscio dell'app: tiene i dati dell'indice, la vista corrente e la cache dei
   dettagli caricati on-demand. La navigazione è a 3 livelli (home -> lista di un
   tema -> digest di un giorno) più la dashboard, come nell'originale. */

const HOME = { tipo: 'home' }

export default function App() {
  const [indice, setIndice] = useState(null)
  const [errore, setErrore] = useState('')
  const [vista, setVista] = useState(HOME)

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

  const vaiHome = useCallback(() => {
    setVista(HOME)
    window.scrollTo(0, 0)
  }, [])

  const vaiTema = useCallback((temaId) => {
    setVista({ tipo: 'tema', temaId })
    window.scrollTo(0, 0)
  }, [])

  const vaiGruppo = useCallback((temaId, data) => {
    setVista({ tipo: 'gruppo', temaId, data })
    window.scrollTo(0, 0)
  }, [])

  const vaiDashboard = useCallback(() => {
    setVista({ tipo: 'dashboard' })
    window.scrollTo(0, 0)
  }, [])

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

  const tema = vista.temaId ? indice.temi.find((t) => t.id === vista.temaId) : null

  return (
    <>
      <Sfondo />
      <Intestazione onHome={vaiHome} onDashboard={vaiDashboard} />
      <div id="app">
        {vista.tipo === 'home' && (
          <Home indice={indice} onTema={vaiTema} />
        )}
        {vista.tipo === 'tema' && tema && (
          <ListaGruppi
            tema={tema}
            indice={indice}
            caricaGruppi={gruppiDelTema}
            onHome={vaiHome}
            onGruppo={vaiGruppo}
          />
        )}
        {vista.tipo === 'gruppo' && tema && (
          <ArticoliGruppo
            tema={tema}
            data={vista.data}
            indice={indice}
            caricaGruppi={gruppiDelTema}
            caricaArticoli={articoliDelGiorno}
            onHome={vaiHome}
            onTema={vaiTema}
          />
        )}
        {vista.tipo === 'dashboard' && (
          <Dashboard indice={indice} onHome={vaiHome} />
        )}
      </div>
    </>
  )
}
