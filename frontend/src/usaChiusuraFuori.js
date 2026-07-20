import { useEffect, useRef } from 'react'

/* Chiude un pannello a comparsa quando si clicca fuori o si preme Esc.
   Serve al calendario del filtro periodo e al popover "Scarica" del digest:
   stesso comportamento, una sola implementazione.

   `riferimenti` sono gli elementi che NON devono chiudere: il pannello stesso e
   il bottone che lo apre. Senza escludere il bottone, il click che apre verrebbe
   subito riletto come click fuori e il pannello non si aprirebbe mai.

   L'array arriva nuovo a ogni render, quindi NON può stare tra le dipendenze
   dell'effetto: finirebbe per staccare e riattaccare i listener di continuo. Si
   tiene in un ref, che l'effetto legge senza dipenderne. */
export function usaChiusuraFuori(aperto, riferimenti, chiudi) {
  const refs = useRef(riferimenti)
  refs.current = riferimenti

  const suChiudi = useRef(chiudi)
  suChiudi.current = chiudi

  useEffect(() => {
    if (!aperto) return undefined

    const suClick = (e) => {
      const dentro = refs.current.some((r) => r.current && r.current.contains(e.target))
      if (!dentro) suChiudi.current()
    }
    const suTasto = (e) => { if (e.key === 'Escape') suChiudi.current() }

    document.addEventListener('mousedown', suClick)
    document.addEventListener('keydown', suTasto)
    return () => {
      document.removeEventListener('mousedown', suClick)
      document.removeEventListener('keydown', suTasto)
    }
  }, [aperto])
}
