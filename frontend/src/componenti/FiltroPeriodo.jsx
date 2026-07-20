import { useCallback, useRef, useState } from 'react'
import { GIORNI_SETT, MESI_FULL, RANGE_TEMA, fmtDataBreve, pad2 } from '../dati.js'
import { usaChiusuraFuori } from '../usaChiusuraFuori.js'

/* Filtro periodo riusabile: pill rapide + intervallo Dal/Al con calendario custom.
   Condiviso tra la lista di un tema e la dashboard, che cambiano solo il set di
   pill (RANGE_TEMA / RANGE_DASH).

   Lo stato vive nel componente padre ({val, dal, al}) perché è lui a filtrare i
   dati: qui si producono solo le modifiche. */

function Calendario({ campo, stato, onSeleziona }) {
  const base = stato[campo] ? new Date(stato[campo] + 'T00:00:00') : new Date()
  const [anno, setAnno] = useState(base.getFullYear())
  const [mese, setMese] = useState(base.getMonth())

  const naviga = (delta) => {
    let m = mese + delta
    let a = anno
    if (m < 0) { m = 11; a-- }
    if (m > 11) { m = 0; a++ }
    setMese(m)
    setAnno(a)
  }

  const offset = (new Date(anno, mese, 1).getDay() + 6) % 7   // lun = 0
  const giorniMese = new Date(anno, mese + 1, 0).getDate()
  const oggiIso = new Date().toISOString().slice(0, 10)
  const { dal, al } = stato

  const celle = []
  for (let i = 0; i < offset; i++) {
    celle.push(<span key={'v' + i} className="cal-vuoto" />)
  }
  for (let g = 1; g <= giorniMese; g++) {
    const iso = `${anno}-${pad2(mese + 1)}-${pad2(g)}`
    // disabilita i giorni che creerebbero un intervallo invertito (Al<Dal o Dal>Al)
    const off = (campo === 'al' && dal && iso < dal) || (campo === 'dal' && al && iso > al)
    const cls = ['cal-g']
    if (off) cls.push('off')
    if (iso === dal || iso === al) cls.push('sel')                       // estremi
    else if (dal && al && iso > dal && iso < al) cls.push('in-range')    // intermedi
    if (iso === oggiIso) cls.push('oggi')
    celle.push(
      <button
        key={iso}
        className={cls.join(' ')}
        disabled={!!off}
        onClick={(e) => { e.stopPropagation(); onSeleziona(iso) }}
      >
        {g}
      </button>,
    )
  }

  return (
    <div className="cal-pop" onClick={(e) => e.stopPropagation()}>
      <div className="cal-head">
        <button className="cal-nav" onClick={() => naviga(-1)} aria-label="Mese precedente">‹</button>
        <span className="cal-titolo">{MESI_FULL[mese]} {anno}</span>
        <button className="cal-nav" onClick={() => naviga(1)} aria-label="Mese successivo">›</button>
      </div>
      <div className="cal-sett">{GIORNI_SETT.map((d) => <span key={d}>{d}</span>)}</div>
      <div className="cal-griglia">{celle}</div>
    </div>
  )
}

export default function FiltroPeriodo({ stato, onCambia, range = RANGE_TEMA }) {
  const [campoAperto, setCampoAperto] = useState(null)
  const pannello = useRef(null)
  const campi = useRef(null)

  const chiudi = useCallback(() => setCampoAperto(null), [])
  usaChiusuraFuori(campoAperto !== null, [pannello, campi], chiudi)

  const scegliDate = (iso) => {
    // le selezioni che invertirebbero l'intervallo sono già disabilitate nella
    // griglia; questo è il presidio in caso ci si arrivi da tastiera.
    if ((campoAperto === 'al' && stato.dal && iso < stato.dal) ||
        (campoAperto === 'dal' && stato.al && iso > stato.al)) return
    onCambia({ ...stato, [campoAperto]: iso })
    chiudi()
  }

  const azzera = () => {
    onCambia({ val: 'all', dal: '', al: '' })
    chiudi()
  }

  const attivo = (stato.val && stato.val !== 'all') || !!stato.dal || !!stato.al

  return (
    <div className="filtri">
      <div className="filtro-range">
        {range.map(([valore, etichetta]) => (
          <button
            key={valore}
            className={'pill-f' + (stato.val === valore ? ' attivo' : '')}
            onClick={() => onCambia({ ...stato, val: valore })}
          >
            {etichetta}
          </button>
        ))}
      </div>

      <div className="filtro-date">
        <span className="filtro-lbl">Periodo</span>
        <div className="date-range" ref={campi}>
          <button
            className="date-field"
            onClick={(e) => { e.stopPropagation(); setCampoAperto('dal') }}
          >
            <span className="df-lbl">Dal</span>
            <span className="df-val">{stato.dal ? fmtDataBreve(stato.dal) : '—'}</span>
          </button>
          <span className="range-sep">→</span>
          <button
            className="date-field"
            onClick={(e) => { e.stopPropagation(); setCampoAperto('al') }}
          >
            <span className="df-lbl">Al</span>
            <span className="df-val">{stato.al ? fmtDataBreve(stato.al) : '—'}</span>
          </button>
          {campoAperto && (
            <div ref={pannello}>
              <Calendario
                key={campoAperto}
                campo={campoAperto}
                stato={stato}
                onSeleziona={scegliDate}
              />
            </div>
          )}
        </div>
        <button
          className={'btn-azzera' + (attivo ? '' : ' nascosto')}
          onClick={azzera}
        >
          ✕ Azzera
        </button>
      </div>
    </div>
  )
}
