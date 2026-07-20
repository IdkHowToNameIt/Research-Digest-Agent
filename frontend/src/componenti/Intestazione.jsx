import logo from '../assets/kva-logo.webp'
import { IconaOsserva } from './Icone.jsx'

/* Barra in alto: logo cliccabile (torna alla home) e accesso alla dashboard. */
export default function Intestazione({ onHome, onDashboard }) {
  return (
    <header>
      <a
        className="logo"
        href="#"
        onClick={(e) => { e.preventDefault(); onHome() }}
        title="Digest Research Agent (DRA)"
      >
        <span className="mark" aria-hidden="true">
          <img className="mark-img" src={logo} alt="kakashi.ventures" width="48" height="38" />
        </span>
        <span className="wm">DRA</span>
      </a>
      <nav className="topnav">
        <a
          className="topnav-link"
          href="#"
          onClick={(e) => { e.preventDefault(); onDashboard() }}
          title="Sotto il cofano — i numeri dell'agente"
        >
          <IconaOsserva dim={16} />
          <span>Sotto il cofano</span>
        </a>
      </nav>
    </header>
  )
}
