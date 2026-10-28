import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './theme.css';
import { App } from './App';
import { hydrate } from './store';

if ('serviceWorker' in navigator && import.meta.env.PROD) navigator.serviceWorker.register('/sw.js').catch(() => {});

hydrate().then(() => createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>));
