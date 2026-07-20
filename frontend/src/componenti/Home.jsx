import { fmtData, plurale } from '../dati.js'
import { useEffetti } from '../effetti.js'
import { IconaTema } from './Icone.jsx'

/* ---------------------------- HOMEPAGE ----------------------------
   Un box per OGNI tema. Se il tema ha novità nella settimana mostra il gruppo più
   recente (titolo riassuntivo + data); altrimenti resta comunque presente con lo
   stato "Nessun aggiornamento settimanale". Il click porta alla lista del tema. */

function BoxTema({ tema, sogliaNuovo, sogliaSettimana, onTema }) {
  // usa i gruppi recenti dell'indice, non il dettaglio (non ancora caricato)
  const recenti = tema.recenti.filter((g) => g.giorni <= sogliaSettimana)

  if (!recenti.length) {
    // nessuna novità nella settimana: box presente ma "vuoto" (storico apribile)
    return (
      <div className="box box-vuota reveal" data-tilt onClick={() => onTema(tema.id)}>
        <h3><span className="tema-ic"><IconaTema id={tema.id} dim={22} /></span>{tema.nome}</h3>
        <div className="box-vuoto">Nessun aggiornamento settimanale</div>
        <span className="apri">Apri {tema.nome} →</span>
      </div>
    )
  }

  const g0 = recenti[0]                       // più recente (il backend ordina desc)
  const nuovo = g0.giorni <= sogliaNuovo
  const nNews = recenti.reduce((s, g) => s + g.n, 0)

  return (
    <div className="box reveal" data-tilt onClick={() => onTema(tema.id)}>
      <h3><span className="tema-ic"><IconaTema id={tema.id} dim={22} /></span>{tema.nome}</h3>
      <div className="box-data">
        {fmtData(g0.data)} {nuovo && <span className="badge-nuovo">Nuovo</span>}
      </div>
      <div className="box-titolo">{g0.titolo}</div>
      <div className="box-conta">
        {nNews} {plurale(nNews, 'aggiornamento', 'aggiornamenti')} questa settimana
      </div>
      <span className="apri">Apri {tema.nome} →</span>
    </div>
  )
}

export default function Home({ indice, onTema }) {
  useEffetti('home')
  const oggi = fmtData(new Date().toISOString().slice(0, 10))

  return (
    <section className="view home">
      <div className="hero">
        <div className="kicker">Digest settimanale interno</div>
        <h1 className="title">Digest Research Agent</h1>
        <p className="sub">
          Infrastruttura &amp; Hardware AI — chip, data center, energia, supply chain,
          capacità cloud.
        </p>
        <div className="settimana">Settimana del {oggi}</div>
      </div>

      <div className="temi-nav">
        {indice.temi.map((t) => (
          <button key={t.id} className="pill" onClick={() => onTema(t.id)}>
            <IconaTema id={t.id} dim={15} />{t.nome}
          </button>
        ))}
      </div>

      <main>
        <div className="sez-titolo">Aggiornamenti di questa settimana</div>
        <div className="sez-nota">
          Un box per ogni tema: le notizie dello stesso giorno sono un unico digest.
        </div>
        <div className="boxes">
          {indice.temi.map((t) => (
            <BoxTema
              key={t.id}
              tema={t}
              sogliaNuovo={indice.sogliaNuovo}
              sogliaSettimana={indice.sogliaSettimana}
              onTema={onTema}
            />
          ))}
        </div>
      </main>
    </section>
  )
}
