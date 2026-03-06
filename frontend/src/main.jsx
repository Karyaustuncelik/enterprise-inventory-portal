import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

window.addEventListener('error', (event) => {
  console.error('Global error:', event.error || event.message);
  const rootEl = document.getElementById('root');
  if (rootEl && !rootEl.dataset.hasError) {
    rootEl.dataset.hasError = 'true';
    rootEl.innerHTML = `<pre style="padding:16px; white-space:pre-wrap; color:#e1000f;">${event.message || 'Error'}\n${(event.error && event.error.stack) || ''}</pre>`;
  }
});

window.addEventListener('unhandledrejection', (event) => {
  console.error('Unhandled promise rejection:', event.reason);
  const rootEl = document.getElementById('root');
  if (rootEl && !rootEl.dataset.hasError) {
    rootEl.dataset.hasError = 'true';
    rootEl.innerHTML = `<pre style="padding:16px; white-space:pre-wrap; color:#e1000f;">${event.reason || 'Promise rejection'}</pre>`;
  }
});

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
