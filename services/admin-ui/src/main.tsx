import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'

// Debug logging for deployment verification
console.log('🚀 ADMIN_PORTAL_DEBUG: App starting - VERSION 2.1.3 with Quick Fill button and Slug display');
console.log('🚀 ADMIN_PORTAL_DEBUG: Commit hash: e83e8ed (cache fix + login shortcut + slug display)');
console.log('🚀 ADMIN_PORTAL_DEBUG: Build time:', new Date().toISOString());

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
