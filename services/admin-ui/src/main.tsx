import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Debug logging for deployment verification
console.log('🚀 ADMIN_PORTAL_DEBUG: App starting - VERSION 2.1.4 - Removed TopBar refresh button');
console.log('🚀 ADMIN_PORTAL_DEBUG: Grant DUST feature added, refresh buttons removed');
console.log('🚀 ADMIN_PORTAL_DEBUG: Build time:', new Date().toISOString());

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
