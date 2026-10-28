import { serve } from '@hono/node-server';
import { app } from './app';
import { cfg, health } from './config';

serve({ fetch: app.fetch, port: cfg.port }, info => {
  console.log(`Abuk server on :${info.port}`);
  for (const [k, v] of Object.entries(health())) if (!v.configured) console.log(`  ${k}: not configured (missing ${v.missing.join(', ')})`);
});
