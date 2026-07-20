import { useEffect, useRef } from 'react'
import { avviaSfondo } from '../sfondo.js'

/* Sfondo del concept (ripreso da kakashi.ventures): campo di glifi su canvas che
   si accendono vicino al cursore, più la vignetta sopra. Il disegno resta in
   sfondo.js in canvas puro — React monta il canvas e ne gestisce il ciclo di vita,
   non entra nel loop di rendering (60fps in stato React sarebbe uno spreco). */
export default function Sfondo() {
  const canvas = useRef(null)

  useEffect(() => avviaSfondo(canvas.current), [])

  return (
    <>
      <canvas id="fx" ref={canvas} aria-hidden="true" />
      <div className="grad" aria-hidden="true" />
    </>
  )
}
