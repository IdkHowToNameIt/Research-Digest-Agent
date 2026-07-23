import { useEffect, useMemo, useState } from 'react'
import {
  RANGE_DASH,
  caricaMetriche,
  filtraPerPeriodo,
  fmtData,
  fmtEuro,
  fmtNum,
  nomeTema,
} from '../dati.js'
import { useEffetti } from '../effetti.js'
import FiltroPeriodo from './FiltroPeriodo.jsx'
import { IconaOsserva, IconaTema } from './Icone.jsx'

/* ===================== DASHBOARD DI OSSERVABILITÀ =======================
   Legge metriche.json (un record per run) e mostra, per il periodo scelto col
   filtro riusato dalla lista tema: stato delle fonti, costi, selezione delle
   notizie (ex "deduplica") e copertura dei 5 sotto-temi. Nessun dato editoriale né nota interna. */

function Barra({ frazione, cls }) {
  const pct = Math.max(0, Math.min(100, Math.round((frazione || 0) * 100)))
  return <div className={'dash-bar ' + (cls || '')}><span style={{ width: pct + '%' }} /></div>
}

function Stat({ valore, etichetta }) {
  return (
    <div className="dash-stat">
      <div className="ds-val">{valore}</div>
      <div className="ds-lbl">{etichetta}</div>
    </div>
  )
}

function Sommario({ runs }) {
  const ultimo = runs[0]
  const totPub = runs.reduce((s, r) => s + r.dedup.pubblicati, 0)
  const totEur = runs.reduce((s, r) => s + r.costo.costo_stimato, 0)
  const voci = [
    ['Ultimo run', fmtData(ultimo.data)],
    ['Run nel periodo', runs.length],
    ['Articoli pubblicati', fmtNum(totPub)],
    ['Costo', fmtEuro(totEur)],
  ]
  return (
    <div className="dash-sommario">
      {voci.map(([lbl, val]) => (
        <div className="dsm-voce" key={lbl}>
          <span className="dsm-lbl">{lbl}</span>
          <span className="dsm-val">{val}</span>
        </div>
      ))}
    </div>
  )
}

function PannelloFonti({ runs }) {
  const ultimo = runs[0]
  const nomi = []
  runs.forEach((r) => (r.fonti || []).forEach((f) => {
    if (!nomi.includes(f.nome)) nomi.push(f.nome)
  }))
  const koUltimo = (ultimo.fonti || []).filter((f) => f.stato === 'fetch_failed').length

  return (
    <section className="dash-card reveal">
      <div className="dash-tit">
        <IconaOsserva dim={16} /> Fonti <span className="dash-tit-n">{nomi.length}</span>
      </div>
      <div className="dash-sub">
        Ultimo run:{' '}
        {koUltimo === 0
          ? <span className="dash-esito ok">tutte operative</span>
          : <span className="dash-esito ko">{koUltimo} in errore</span>}
      </div>
      <div className="fonti-grid">
        {nomi.map((nome) => {
          const f = (ultimo.fonti || []).find((x) => x.nome === nome) || null
          const cls = !f ? 'na' : (f.stato === 'ok' ? 'ok' : 'ko')
          const tip = f ? f.stato + (f.errore ? ': ' + f.errore : '') : 'assente'
          return (
            <span className={'fonte-pill fp-' + cls} title={tip} key={nome}>
              <span className="fp-dot" />{nome}
              {f && f.consecutivi_falliti > 0 && (
                <span className="fp-strk">×{f.consecutivi_falliti}</span>
              )}
            </span>
          )
        })}
      </div>
    </section>
  )
}

function PannelloCosti({ runs }) {
  const tot = runs.reduce((a, r) => ({
    p: a.p + r.costo.prompt_tokens,
    c: a.c + r.costo.completion_tokens,
    e: a.e + r.costo.costo_stimato,
  }), { p: 0, c: 0, e: 0 })
  const maxTok = Math.max(
    ...runs.map((r) => r.costo.prompt_tokens + r.costo.completion_tokens), 1,
  )

  return (
    <section className="dash-card reveal">
      <div className="dash-tit"><IconaOsserva dim={16} /> Costi</div>
      <div className="dash-big">{fmtEuro(tot.e)}</div>
      <div className="dash-stats">
        <Stat valore={fmtNum(tot.p)} etichetta="token input" />
        <Stat valore={fmtNum(tot.c)} etichetta="token output" />
      </div>
      {tot.e === 0 && (
        <div className="dash-nota-min">
          Sul piano gratuito il costo è 0; i token sono comunque contati. Imposta i
          prezzi in config.yaml per la spesa reale.
        </div>
      )}
      {runs.length > 1 && (
        <div className="dash-runs">
          {runs.map((r) => {
            const tk = r.costo.prompt_tokens + r.costo.completion_tokens
            return (
              <div className="dash-run" key={r.data + r.timestamp}>
                <div className="dr-data">{fmtData(r.data)}</div>
                <div className="dr-bar"><Barra frazione={tk / maxTok} cls="bar-cost" /></div>
                <div className="dr-val">{fmtNum(tk)} tok · {fmtEuro(r.costo.costo_stimato)}</div>
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}

export function PannelloDedup({ runs }) {
  const tot = runs.reduce((a, r) => ({
    racc: a.racc + r.dedup.raccolti,
    pub: a.pub + r.dedup.pubblicati,
    dup: a.dup + r.dedup.duplicati_esatti + r.dedup.duplicati_fuzzy,
    agg: a.agg + r.dedup.aggiornamenti,
    scl: a.scl + r.dedup.scartati_classificazione,
    // I run anteriori al raggruppamento per storia non hanno il campo: senza
    // il "|| 0" il totale diventerebbe NaN e il pannello mostrerebbe "-".
    acc: a.acc + (r.dedup.accorpati_aggregatore || 0),
  }), { racc: 0, pub: 0, dup: 0, agg: 0, scl: 0, acc: 0 })
  const pct = tot.racc ? Math.round((tot.pub / tot.racc) * 100) : 0

  return (
    <section className="dash-card reveal">
      <div className="dash-tit"><IconaOsserva dim={16} /> Selezione delle notizie</div>
      <div className="dash-sub">
        {fmtNum(tot.pub)} pubblicati su {fmtNum(tot.racc)} raccolti
      </div>
      <div className="dash-bar bar-pub"><span style={{ width: pct + '%' }} /></div>
      <div className="dash-stats">
        <Stat valore={fmtNum(tot.dup)} etichetta="doppioni scartati" />
        {tot.acc > 0 && (
          <Stat valore={fmtNum(tot.acc)} etichetta="varianti accorpate" />
        )}
        <Stat valore={fmtNum(tot.agg)} etichetta="inclusi come agg." />
        <Stat valore={fmtNum(tot.scl)} etichetta="fuori tema" />
      </div>
    </section>
  )
}

function PannelloCopertura({ runs, temi }) {
  const ultimo = runs[0]
  const streak = ultimo.energia_zero_consecutivi || 0

  return (
    <section className="dash-card reveal">
      <div className="dash-tit">
        <IconaOsserva dim={16} /> Copertura temi <span className="dash-tit-n">ultimo run</span>
      </div>
      <div className="cop-lista">
        {temi.map((id) => {
          const c = (ultimo.copertura || []).find((x) => x.tema === id) || {}
          const n = c.n_articoli || 0
          return (
            <div className="cop-riga" key={id}>
              <span className="cop-tema"><IconaTema id={id} dim={15} />{nomeTema(id)}</span>
              <span className={'cop-n ' + (n ? '' : 'cop-zero')}>{n}</span>
            </div>
          )
        })}
      </div>
      {streak >= 3 && (
        <div className="dash-avviso">
          ⚠ Energia a zero da {streak} run consecutivi (fonte unica arXiv): controllo manuale.
        </div>
      )}
    </section>
  )
}

export default function Dashboard({ onHome }) {
  const [dati, setDati] = useState(null)
  const [errore, setErrore] = useState('')
  const [filtro, setFiltro] = useState({ val: 'all', dal: '', al: '' })

  useEffect(() => {
    let vivo = true
    caricaMetriche()
      .then((d) => { if (vivo) setDati(d) })
      .catch((err) => { if (vivo) setErrore(err.message) })
    return () => { vivo = false }
  }, [])

  const runs = useMemo(
    () => (dati ? filtraPerPeriodo(dati.run, filtro) : []),
    [dati, filtro],
  )

  useEffetti('dash:' + runs.length)

  return (
    <section className="view">
      <main className="crono dash">
        <button className="indietro" onClick={onHome}>← Home</button>
        <h2><span className="tema-ic"><IconaOsserva dim={26} /></span>Sotto il cofano</h2>
        <p className="sez-nota">
          I numeri dell'agente: stato delle fonti, costi, selezione delle notizie e
          copertura dei temi — per periodo.
        </p>

        {errore && (
          <p className="sez-nota">
            Metriche non ancora disponibili ({errore}). Vengono registrate a partire
            dal primo run.
          </p>
        )}
        {!errore && dati === null && <p className="sez-nota">Caricamento…</p>}
        {!errore && dati !== null && dati.run.length === 0 && (
          <p className="sez-nota">Nessun run registrato finora.</p>
        )}

        {!errore && dati !== null && dati.run.length > 0 && (
          <>
            <FiltroPeriodo stato={filtro} onCambia={setFiltro} range={RANGE_DASH} />
            <div id="dash-pannelli">
              {runs.length === 0 ? (
                <p className="sez-nota">Nessun run nel periodo selezionato.</p>
              ) : (
                <>
                  <Sommario runs={runs} />
                  <div className="dash-grid">
                    <PannelloFonti runs={runs} />
                    <PannelloCosti runs={runs} />
                    <PannelloDedup runs={runs} />
                    <PannelloCopertura runs={runs} temi={dati.temi} />
                  </div>
                </>
              )}
            </div>
          </>
        )}
      </main>
    </section>
  )
}
