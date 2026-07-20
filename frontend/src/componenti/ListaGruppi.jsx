import { useEffect, useMemo, useRef, useState } from 'react'
import {
  OPZIONI_PER_PAGINA,
  filtraPerPeriodo,
  fmtData,
  fmtLettura,
  plurale,
} from '../dati.js'
import { useEffetti } from '../effetti.js'
import FiltroPeriodo from './FiltroPeriodo.jsx'
import { IconaTema } from './Icone.jsx'

/* ------------------- LISTA GRUPPI DI UN TEMA ---------------------
   Un gruppo per giorno, rappresentato dal titolo riassuntivo; il click apre il
   dettaglio. In cima, filtri per data (periodo rapido + intervallo Dal/Al). */

function CardGruppo({ gruppo, sogliaNuovo, onApri }) {
  const nuovo = gruppo.giorni <= sogliaNuovo
  const n = gruppo.n                       // conteggio dai metadati (corpi non caricati)
  const lettura = fmtLettura(gruppo.minuti)

  return (
    <div className="gruppo-card reveal" onClick={onApri}>
      <div className="meta">
        {fmtData(gruppo.data)} {nuovo && <span className="badge-nuovo">Nuovo</span>}
        {' · '}{n} {plurale(n, 'aggiornamento', 'aggiornamenti')}
        {lettura ? ' · ' + lettura : ''}
      </div>
      <h4>{gruppo.titolo}</h4>
      {n > 1 && (
        <ul className="preview">
          {gruppo.anteprima.slice(0, 3).map((tit, i) => <li key={i}>{tit}</li>)}
          {n > 3 && <li className="piu">…e altre {n - 3}</li>}
        </ul>
      )}
      <span className="apri">Apri il digest del giorno →</span>
    </div>
  )
}

/* Barra di paginazione: selettore "Per pagina" (10/25/50) + navigazione
   Prec/Succ. La nav compare solo oltre la prima pagina; il selettore c'è sempre
   quando ci sono risultati. */
function Paginazione({ totale, totPagine, inizio, mostrati, pagina, perPagina, onPagina, onPerPagina }) {
  const da = totale ? inizio + 1 : 0
  const a = inizio + mostrati

  return (
    <div className="paginazione">
      <div className="pag-info">
        <label className="pag-perpag">
          Per pagina
          <select value={perPagina} onChange={(e) => onPerPagina(Number(e.target.value) || 10)}>
            {OPZIONI_PER_PAGINA.map((n) => <option key={n} value={n}>{n}</option>)}
          </select>
        </label>
        <span className="pag-conta">{da}–{a} di {totale}</span>
      </div>
      {totPagine > 1 && (
        <div className="pag-nav">
          <button className="pag-btn" disabled={pagina <= 1} onClick={() => onPagina(-1)}>‹ Prec</button>
          <span className="pag-stato">Pagina {pagina} di {totPagine}</span>
          <button className="pag-btn" disabled={pagina >= totPagine} onClick={() => onPagina(1)}>Succ ›</button>
        </div>
      )}
    </div>
  )
}

const FILTRO_VUOTO = { val: 'all', dal: '', al: '' }

export default function ListaGruppi({ tema, indice, caricaGruppi, onHome, onGruppo }) {
  const [gruppi, setGruppi] = useState(null)
  const [errore, setErrore] = useState('')
  // i filtri data NON persistono tra temi diversi: si riparte puliti a ogni tema
  const [filtro, setFiltro] = useState(FILTRO_VUOTO)
  const [pagina, setPagina] = useState(1)
  const [perPagina, setPerPagina] = useState(10)
  const cima = useRef(null)

  useEffect(() => {
    let vivo = true
    setGruppi(null)
    setErrore('')
    setFiltro(FILTRO_VUOTO)
    setPagina(1)
    caricaGruppi(tema)
      .then((g) => { if (vivo) setGruppi(g) })
      .catch((err) => { if (vivo) setErrore(err.message) })
    // `vivo` evita che una risposta lenta di un tema abbandonato sovrascriva
    // quello che l'utente sta guardando adesso.
    return () => { vivo = false }
  }, [tema, caricaGruppi])

  const filtrati = useMemo(
    () => (gruppi ? filtraPerPeriodo(gruppi, filtro) : []),
    [gruppi, filtro],
  )

  const totale = filtrati.length
  const totPagine = Math.max(1, Math.ceil(totale / perPagina))
  // i filtri possono ridurre i risultati sotto la pagina corrente: si rientra nei limiti
  const paginaValida = Math.min(Math.max(pagina, 1), totPagine)
  const inizio = (paginaValida - 1) * perPagina
  const visibili = filtrati.slice(inizio, inizio + perPagina)

  useEffetti(tema.id + ':' + paginaValida + ':' + totale)

  const cambiaFiltro = (nuovo) => {
    setFiltro(nuovo)
    setPagina(1)              // un nuovo filtro riparte dalla prima pagina
  }

  const cambiaPagina = (delta) => {
    setPagina(paginaValida + delta)
    // riporta in cima alla lista, per non ritrovarsi a metà della pagina dopo
    if (cima.current) cima.current.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <section className="view">
      <main className="crono" ref={cima}>
        <button className="indietro" onClick={onHome}>← Home</button>
        <h2><span className="tema-ic"><IconaTema id={tema.id} dim={26} /></span>{tema.nome}</h2>

        {errore && (
          <p className="sez-nota">Dettaglio del tema non disponibile ({errore}).</p>
        )}
        {!errore && gruppi === null && <p className="sez-nota">Caricamento…</p>}

        {!errore && gruppi !== null && (
          gruppi.length === 0 ? (
            <p className="sez-nota">Nessun articolo in archivio per questo tema.</p>
          ) : (
            <>
              <FiltroPeriodo stato={filtro} onCambia={cambiaFiltro} />
              <div id="lista-gruppi">
                {totale === 0 ? (
                  <p className="sez-nota">Nessun aggiornamento per il periodo selezionato.</p>
                ) : (
                  <>
                    {visibili.map((g) => (
                      <CardGruppo
                        key={g.data}
                        gruppo={g}
                        sogliaNuovo={indice.sogliaNuovo}
                        onApri={() => onGruppo(tema.id, g.data)}
                      />
                    ))}
                    <Paginazione
                      totale={totale}
                      totPagine={totPagine}
                      inizio={inizio}
                      mostrati={visibili.length}
                      pagina={paginaValida}
                      perPagina={perPagina}
                      onPagina={cambiaPagina}
                      onPerPagina={(n) => { setPerPagina(n); setPagina(1) }}
                    />
                  </>
                )}
              </div>
            </>
          )
        )}
      </main>
    </section>
  )
}
