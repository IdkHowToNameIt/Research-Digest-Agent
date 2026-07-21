/* Rotta nell'URL, per non perdere la vista al refresh.
 *
 * Si usa l'HASH e non il path: il sito è statico e senza rewrite lato server un
 * indirizzo tipo /tema/chip darebbe 404 proprio nel caso che vogliamo coprire —
 * il ricaricamento della pagina. Con l'hash il server serve sempre index.html.
 *
 *   #/                      home
 *   #/tema/<id>             cronologia di un tema
 *   #/tema/<id>/<data>      digest di un giorno
 *   #/dashboard             "Sotto il cofano"
 */

export const HOME = { tipo: 'home' }

/** Interpreta l'hash. Qualunque cosa non riconosciuta ricade sulla home:
 *  l'URL è modificabile a mano, non può portare l'app in uno stato illegale. */
export function daHash(hash) {
  const parti = String(hash || '')
    .replace(/^#\/?/, '')
    .split('/')
    .filter(Boolean)
    .map((p) => {
      try { return decodeURIComponent(p) } catch { return p }
    })

  if (parti[0] === 'dashboard') return { tipo: 'dashboard' }
  if (parti[0] === 'tema' && parti[1]) {
    return parti[2]
      ? { tipo: 'gruppo', temaId: parti[1], data: parti[2] }
      : { tipo: 'tema', temaId: parti[1] }
  }
  return HOME
}

/** Serializza la vista. Inverso di `daHash` per ogni vista raggiungibile. */
export function aHash(vista) {
  const v = vista || HOME
  if (v.tipo === 'dashboard') return '#/dashboard'
  if (v.tipo === 'tema' && v.temaId) {
    return '#/tema/' + encodeURIComponent(v.temaId)
  }
  if (v.tipo === 'gruppo' && v.temaId) {
    return '#/tema/' + encodeURIComponent(v.temaId) + '/' + encodeURIComponent(v.data || '')
  }
  return '#/'
}
