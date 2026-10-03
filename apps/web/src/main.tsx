import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { App } from './App'
import './styles/index.scss'

const root = document.getElementById('root')

if (!root) {
  throw new Error('No se encontró el contenedor raíz de VOZ.')
}

createRoot(root).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
