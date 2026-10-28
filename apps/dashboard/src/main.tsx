import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/cormorant-garamond/400.css';
import '@fontsource/cormorant-garamond/600.css';
import '@fontsource/lora/400.css';
import '@fontsource/lora/600.css';
import '../../pwa/src/theme.css';
import './dash.css';
import { Dashboard } from './Dashboard';

createRoot(document.getElementById('root')!).render(<StrictMode><Dashboard /></StrictMode>);
