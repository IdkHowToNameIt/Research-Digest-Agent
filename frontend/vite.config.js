// defineConfig da 'vitest/config' e non da 'vite': e' quello che riconosce la
// chiave `test` qui sotto (Vitest 3+).
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// Build dell'interfaccia. Il backend (src/consegna/sito.py) copia il contenuto di
// `dist/` nella publish-dir accanto ai JSON generati dal run.
//
// base: './' — i riferimenti agli asset restano RELATIVI. Il sito deve poter stare
// anche sotto un sottopercorso (es. GitHub Pages su /repo/): con la base assoluta
// di default il browser cercherebbe /assets/... e troverebbe 404.
//
// Il cache-busting degli asset non serve piu' a mano: Vite mette un hash del
// contenuto nel nome del file. I JSON dei dati sono un caso diverso — nomi fissi e
// contenuto che cambia a ogni run — e continuano a usare `conVersione()` in src/dati.js.
export default defineConfig({
  plugins: [react()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './src/test/setup.js',
  },
})
