import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/cormorant-garamond/400.css';
import '@fontsource/cormorant-garamond/600.css';
import '@fontsource/lora/400.css';
import '@fontsource/lora/600.css';
import '@fontsource/lora/400-italic.css';
import './theme.css';
import { App } from './App';
import { hydrate } from './store';

// The Android app ships its files inside the APK, so only the hosted PWA needs the service worker.
const native = !!(window as { Capacitor?: { isNativePlatform(): boolean } }).Capacitor?.isNativePlatform();
if ('serviceWorker' in navigator && import.meta.env.PROD && !native) navigator.serviceWorker.register('/sw.js').catch(() => {});

hydrate().then(() => createRoot(document.getElementById('root')!).render(<StrictMode><App /></StrictMode>));
