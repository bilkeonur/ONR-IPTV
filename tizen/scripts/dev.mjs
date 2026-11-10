// Tarayıcıda geliştirme: derler, değişiklikleri izler, http://localhost:5173 adresinde sunar.
// /__proxy?url=... tarayıcının CORS engelini aşmak içindir (TV'de config.xml izni bunu sağlar).
// Browser development server with a CORS proxy (on the TV, config.xml grants cross-origin access).
import * as esbuild from 'esbuild';
import { createServer } from 'node:http';
import { readFileSync, existsSync, watch } from 'node:fs';
import { extname, join, normalize } from 'node:path';
import { OUT, ROOT, buildOptions, copyStatic } from './build.mjs';

const PORT = Number(process.env.PORT || 5173);
const TYPES = {
  '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8', '.png': 'image/png', '.svg': 'image/svg+xml',
  '.json': 'application/json', '.xml': 'application/xml',
};

copyStatic();
const ctx = await esbuild.context(buildOptions(true));
await ctx.watch();
watch(join(ROOT, 'static'), { recursive: true }, () => copyStatic());

async function proxy(req, res, target) {
  try {
    const r = await fetch(target, {
      headers: { 'User-Agent': req.headers['x-ua'] || 'ONRIPTV-Tizen' },
      redirect: 'follow',
      signal: AbortSignal.timeout(180000),
    });
    const body = Buffer.from(await r.arrayBuffer());
    res.writeHead(r.status, {
      'Content-Type': r.headers.get('content-type') || 'application/octet-stream',
      'Access-Control-Allow-Origin': '*',
    });
    res.end(body);
  } catch (e) {
    res.writeHead(502, { 'Content-Type': 'text/plain' });
    res.end(String(e));
  }
}

createServer((req, res) => {
  const url = new URL(req.url, `http://localhost:${PORT}`);
  if (url.pathname === '/__proxy') return proxy(req, res, url.searchParams.get('url'));
  let path = normalize(join(OUT, decodeURIComponent(url.pathname)));
  if (!path.startsWith(OUT)) { res.writeHead(403); return res.end(); }
  if (url.pathname === '/' ) path = join(OUT, 'index.html');
  if (!existsSync(path)) { res.writeHead(404); return res.end('not found'); }
  res.writeHead(200, { 'Content-Type': TYPES[extname(path)] || 'application/octet-stream', 'Cache-Control': 'no-store' });
  res.end(readFileSync(path));
}).listen(PORT, () => console.log(`\n  ONR IPTV (Tizen) → http://localhost:${PORT}\n`));
