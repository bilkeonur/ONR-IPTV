// Uygulamayı build/www klasörüne derler (Tizen paketinin içeriği).
// Builds the app into build/www (the content of the Tizen package).
import * as esbuild from 'esbuild';
import { cpSync, mkdirSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

export const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const pkg = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
export const OUT = join(ROOT, 'build', 'www');

export const buildOptions = (dev = false) => ({
  entryPoints: [join(ROOT, 'src', 'main.ts')],
  bundle: true,
  // Tizen uygulamaları file:// üzerinden açılır; ES modülü yerine klasik script.
  format: 'iife',
  // 2020 sonrası Samsung TV'ler (Tizen 5.5+, Chromium 69+)
  target: ['chrome69'],
  outfile: join(OUT, 'app.js'),
  sourcemap: dev ? 'inline' : false,
  minify: !dev,
  define: { __DEV__: JSON.stringify(dev), __VERSION__: JSON.stringify(pkg.version) },
  logLevel: 'info',
});

export function copyStatic() {
  mkdirSync(OUT, { recursive: true });
  cpSync(join(ROOT, 'static'), OUT, { recursive: true });
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  rmSync(OUT, { recursive: true, force: true });
  copyStatic();
  await esbuild.build(buildOptions(false));
}
