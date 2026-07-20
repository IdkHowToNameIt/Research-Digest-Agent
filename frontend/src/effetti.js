import { useEffect } from 'react'

/* Effetti visivi comuni alle viste: comparsa allo scroll e leggero tilt 3D delle
   card. Restano basati su query del DOM come nell'originale — sono decorazioni
   che attraversano molti elementi, e legarle a un ref per card renderebbe i
   componenti più rumorosi senza guadagno.

   `chiave` rimonta gli osservatori quando cambia la vista: senza, le card
   generate dopo un cambio di pagina resterebbero invisibili (opacity 0). */
export function useEffetti(chiave) {
  useEffect(() => {
    const io = new IntersectionObserver(
      (voci) => voci.forEach((v) => {
        if (v.isIntersecting) {
          v.target.classList.add('in')
          io.unobserve(v.target)
        }
      }),
      { threshold: 0.12 },
    )
    document.querySelectorAll('.reveal').forEach((el) => io.observe(el))

    const conTilt = Array.from(document.querySelectorAll('[data-tilt]'))
    const muovi = (card) => (e) => {
      const r = card.getBoundingClientRect()
      const rx = ((e.clientY - r.top) / r.height - 0.5) * -6
      const ry = ((e.clientX - r.left) / r.width - 0.5) * 6
      card.style.transform =
        `perspective(800px) rotateX(${rx}deg) rotateY(${ry}deg) translateY(-4px)`
    }
    const esci = (card) => () => { card.style.transform = '' }
    const agganci = conTilt.map((card) => {
      const onMove = muovi(card)
      const onLeave = esci(card)
      card.addEventListener('mousemove', onMove)
      card.addEventListener('mouseleave', onLeave)
      return { card, onMove, onLeave }
    })

    return () => {
      io.disconnect()
      // senza questa pulizia ogni cambio vista lascerebbe attaccati i listener
      // delle card smontate: l'originale li sovrascriveva con onmousemove=, qui
      // sono addEventListener e vanno tolti a mano.
      agganci.forEach(({ card, onMove, onLeave }) => {
        card.removeEventListener('mousemove', onMove)
        card.removeEventListener('mouseleave', onLeave)
      })
    }
  }, [chiave])
}
