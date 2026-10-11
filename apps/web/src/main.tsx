import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
import './styles/index.scss'
import { settleDesign } from './theme/appearance'

const root = document.getElementById('root')

if (!root) {
  throw new Error('No se encontró el contenedor raíz de V.')
}

// Con Material 3 elegido se espera a que estén sus colores antes de pintar la primera vez.
void settleDesign().then(() => {
  createRoot(root).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
})
