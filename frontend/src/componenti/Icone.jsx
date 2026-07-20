/* Icone dei temi: una per tema, stesso stile (stroke lineare), stesso peso.
   I tracciati restano stringhe di markup SVG come nell'originale — sono costanti
   di modulo, non contenuto dell'utente, quindi dangerouslySetInnerHTML qui non
   apre alcuna superficie: nessun dato dei JSON passa mai di qui. */

const ICONE_TEMA = {
  chip: '<rect x="7" y="7" width="10" height="10" rx="1.5"/><line x1="9" y1="2" x2="9" y2="7"/><line x1="15" y1="2" x2="15" y2="7"/><line x1="9" y1="17" x2="9" y2="22"/><line x1="15" y1="17" x2="15" y2="22"/><line x1="2" y1="9" x2="7" y2="9"/><line x1="2" y1="15" x2="7" y2="15"/><line x1="17" y1="9" x2="22" y2="9"/><line x1="17" y1="15" x2="22" y2="15"/>',
  data_center: '<rect x="4" y="3" width="16" height="8" rx="1.5"/><rect x="4" y="13" width="16" height="8" rx="1.5"/><circle cx="8" cy="7" r="1" fill="currentColor" stroke="none"/><circle cx="8" cy="17" r="1" fill="currentColor" stroke="none"/>',
  energia: '<polygon points="13,2 4,14 11,14 9,22 18,10 11,10"/>',
  supply_chain: '<circle cx="6" cy="6" r="3"/><circle cx="18" cy="6" r="3"/><circle cx="12" cy="18" r="3"/><line x1="8.6" y1="7.6" x2="10" y2="15.5"/><line x1="15.4" y1="7.6" x2="14" y2="15.5"/><line x1="9" y1="6" x2="15" y2="6"/>',
  cloud_capacity: '<path d="M7 18a4.5 4.5 0 0 1-1-8.9A5 5 0 0 1 16 8a3.8 3.8 0 0 1 1 7.5" /><path d="M7 18h9.5"/>',
}

const COMUNI = {
  className: 'tema-svg',
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: '1.6',
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': true,
}

export function IconaTema({ id, dim = 18 }) {
  return (
    <svg
      {...COMUNI}
      width={dim}
      height={dim}
      dangerouslySetInnerHTML={{ __html: ICONE_TEMA[id] || '' }}
    />
  )
}

export function IconaOsserva({ dim = 18 }) {
  return (
    <svg {...COMUNI} width={dim} height={dim}>
      <path d="M4 17a8 8 0 0 1 16 0" />
      <line x1="12" y1="17" x2="16.5" y2="11.5" />
      <circle cx="12" cy="17" r="1.3" fill="currentColor" stroke="none" />
    </svg>
  )
}
