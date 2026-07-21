import { useEffect, useMemo, useRef, useState } from 'react'
import { LINEA, indiceAttivo } from '../lettura.js'
import { useEffetti } from '../effetti.js'
import { fmtData, fmtLettura, pad2, plurale } from '../dati.js'
import { IconaTema } from './Icone.jsx'
import ScaricaDigest from './ScaricaDigest.jsx'

/* ---------------- DETTAGLIO DEL GRUPPO (giorno) ------------------
   Le notizie di quel tema in quel giorno, per intero. Se provengono da PIÙ fonti,
   in cima compare un filtro per fonte. A lato, l'indice della giornata evidenzia
   la voce in lettura mentre si scorre. */

function Voce({ tema, articolo, n }) {
  const fonti = (articolo.fonti || []).length
    ? articolo.fonti.map((f, i) => (
      <span key={i}>
        {i > 0 && ' · '}
        {f.link
          ? <a href={f.link} target="_blank" rel="noopener">{f.nome} ↗</a>
          : f.nome}
      </span>
    ))
    : articolo.fonte

  return (
    <article className="art reveal" id={'art-' + n}>
      <div className="art-head">
        <span className="art-n">{pad2(n)}</span>
        <h4>{articolo.titolo}</h4>
      </div>
      <div className="meta">
        <span className="fonte">{fonti}</span>
        <span className="tag"><IconaTema id={tema.id} dim={13} />{tema.nome}</span>
        {' · '}{fmtData(articolo.data)}
      </div>
      {articolo.nota && <div className="nota">{articolo.nota}</div>}
      <p className="sintesi">{articolo.sintesi}</p>
      <div className="perche"><strong>Perché conta:</strong> {articolo.perche}</div>
    </article>
  )
}

/** Evidenzia nell'indice la voce correntemente in lettura, mentre si scorre.
 *
 * Prima si usava un IntersectionObserver con una fascia alta il 10% dello
 * schermo (`rootMargin: -15%/-75%`), aggiornando SOLO all'ingresso di una voce
 * nella fascia. Due difetti riportati dall'uso reale: in fondo alla pagina le
 * ultime voci non raggiungono mai la fascia e il segnaposto si blocca a meta';
 * e tornando su, se nessuna voce attraversa la fascia, resta il valore vecchio.
 * Ora la voce attiva si CALCOLA dalla posizione a ogni scroll: e' sempre
 * definita, senza dipendere dal fatto che sia scattato un evento.
 */
function useIndiceAttivo(articoli) {
  const [attivo, setAttivo] = useState(null)
  // Voce scelta col click sull'indice. Lo scroll morbido che segue farebbe
  // ricalcolare la posizione e, in fondo alla pagina, riporterebbe subito
  // sull'ultima voce: cliccando 6 o 7 si finiva sempre sull'8. Finche' e'
  // valorizzato il calcolo da scroll non tocca la selezione.
  const fissato = useRef(null)

  useEffect(() => {
    if (articoli.length < 2) return undefined
    let programmato = false

    const calcola = () => {
      programmato = false
      if (fissato.current) return
      const nodi = [...document.querySelectorAll('.digest-lettura .art')]
      if (!nodi.length) return
      const doc = document.documentElement
      const restante = doc.scrollHeight - window.innerHeight - window.scrollY
      const cime = nodi.map((n) => n.getBoundingClientRect().top)
      const i = indiceAttivo(cime, window.innerHeight, restante)
      if (i >= 0) setAttivo(nodi[i].id)
    }
    // Lo scroll emette molti eventi: si accorpa il lavoro in un frame solo.
    const suScroll = () => {
      if (programmato) return
      programmato = true
      requestAnimationFrame(calcola)
    }
    // Lo scroll dell'utente libera il fissaggio; quello programmatico no,
    // perche' rotella, tasti e dito emettono questi eventi e scrollIntoView no.
    const suGestoUtente = () => {
      if (!fissato.current) return
      fissato.current = null
      suScroll()
    }

    calcola()
    window.addEventListener('scroll', suScroll, { passive: true })
    window.addEventListener('resize', suScroll)
    window.addEventListener('wheel', suGestoUtente, { passive: true })
    window.addEventListener('touchstart', suGestoUtente, { passive: true })
    window.addEventListener('keydown', suGestoUtente)
    return () => {
      window.removeEventListener('scroll', suScroll)
      window.removeEventListener('resize', suScroll)
      window.removeEventListener('wheel', suGestoUtente)
      window.removeEventListener('touchstart', suGestoUtente)
      window.removeEventListener('keydown', suGestoUtente)
    }
  }, [articoli])

  const fissa = (id) => { fissato.current = id; setAttivo(id) }

  return [attivo, fissa]
}

export default function ArticoliGruppo({
  tema, data, indice, caricaGruppi, caricaArticoli, onHome, onTema,
}) {
  const [gruppo, setGruppo] = useState(null)
  const [articoli, setArticoli] = useState(null)
  const [errore, setErrore] = useState('')
  const [fonte, setFonte] = useState('')       // '' = tutte

  useEffect(() => {
    let vivo = true
    setArticoli(null)
    setErrore('')
    setFonte('')
    ;(async () => {
      try {
        const gruppi = await caricaGruppi(tema)
        const g = gruppi.find((x) => x.data === data)
        if (!vivo) return
        if (!g) { setErrore('Digest del giorno non trovato.'); return }
        setGruppo(g)
        const arts = await caricaArticoli(tema, data)
        // la navigazione può essere cambiata durante il fetch: senza questo
        // controllo la risposta lenta sovrascriverebbe la vista corrente
        if (vivo) setArticoli(arts)
      } catch (err) {
        if (vivo) setErrore(err.message)
      }
    })()
    return () => { vivo = false }
  }, [tema, data, caricaGruppi, caricaArticoli])

  const fonti = useMemo(
    () => (articoli ? [...new Set(articoli.map((a) => a.fonte).filter(Boolean))] : []),
    [articoli],
  )
  const visibili = useMemo(
    () => (articoli ? (fonte ? articoli.filter((a) => a.fonte === fonte) : articoli) : []),
    [articoli, fonte],
  )

  const [attivo, fissaAttivo] = useIndiceAttivo(visibili)
  // La comparsa allo scroll mancava proprio nella vista con piu' contenuto.
  // La chiave include il filtro fonte: cambiandolo l'elenco si rigenera e i
  // nuovi articoli resterebbero invisibili (opacity 0) senza rimontare.
  useEffetti('gruppo:' + tema.id + ':' + data + ':' + fonte + ':' + visibili.length)

  const nuovo = gruppo && gruppo.giorni <= indice.sogliaNuovo
  const lettura = gruppo ? fmtLettura(gruppo.minuti) : ''

  return (
    <section className="view">
      <main className="crono report">
        <button className="indietro" onClick={() => onTema(tema.id)}>← {tema.nome}</button>

        {gruppo && (
          <div className="giorno-testata">
            <div className="giorno-testa-riga">
              <h2>{gruppo.titolo}</h2>
              <div className="giorno-azioni">
                {/* il PDF si genera dai corpi: finché non sono caricati non si offre */}
                {articoli && articoli.length > 0 && (
                  <ScaricaDigest
                    tema={tema}
                    gruppo={gruppo}
                    articoli={articoli}
                    invioEmailUrl={indice.invioEmailUrl}
                  />
                )}
              </div>
            </div>
            <div className="giorno-sub">
              <span className="tag"><IconaTema id={tema.id} dim={13} />{tema.nome}</span>
              {' · '}{fmtData(gruppo.data)} {nuovo && <span className="badge-nuovo">Nuovo</span>}
              {' · '}{gruppo.n} {plurale(gruppo.n, 'aggiornamento', 'aggiornamenti')}
              {lettura ? ' · ' + lettura : ''}
            </div>
          </div>
        )}

        {errore && <p className="sez-nota">Dettaglio del giorno non disponibile ({errore}).</p>}
        {!errore && articoli === null && <p className="sez-nota">Caricamento…</p>}

        {!errore && articoli !== null && (
          <>
            {fonti.length > 1 && (
              <div className="filtro-fonte">
                <span className="filtro-lbl">Fonte:</span>
                {['(tutte)', ...fonti].map((f, i) => {
                  const valore = i === 0 ? '' : f
                  return (
                    <button
                      key={f}
                      className={'chip-f' + (fonte === valore ? ' attivo' : '')}
                      onClick={() => setFonte(valore)}
                    >
                      {f}
                    </button>
                  )
                })}
              </div>
            )}

            <div className="digest-layout">
              <aside className="digest-indice">
                {visibili.length > 1 && (
                  <>
                    <div className="idx-tit">Nella giornata</div>
                    <ol className="idx-lista">
                      {visibili.map((a, i) => {
                        const id = 'art-' + (i + 1)
                        return (
                          <li key={id}>
                            <a
                              className={attivo === id ? 'attivo' : ''}
                              onClick={() => {
                                fissaAttivo(id)
                                const el = document.getElementById(id)
                                if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
                              }}
                            >
                              <span className="idx-n">{pad2(i + 1)}</span>
                              <span>{a.titolo}</span>
                            </a>
                          </li>
                        )
                      })}
                    </ol>
                  </>
                )}
              </aside>

              <div className="digest-lettura">
                {visibili.length ? (
                  visibili.map((a, i) => (
                    <Voce key={i} tema={tema} articolo={a} n={i + 1} />
                  ))
                ) : (
                  <p className="sez-nota">Nessuna notizia per la fonte selezionata.</p>
                )}
              </div>
            </div>
          </>
        )}
      </main>
    </section>
  )
}
