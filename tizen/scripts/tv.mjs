// Paketle ve TV'ye kur. Tizen Studio (CLI) ve bir Samsung sertifika profili gerekir.
//
//   npm run package                 → build/ONRIPTV.wgt
//   npm run tv -- 192.168.1.50      → paketle, TV'ye bağlan, kur ve başlat
//
// Ortam değişkenleri: TIZEN_STUDIO (varsayılan C:\tizen-studio), TIZEN_PROFILE (varsayılan onriptv)
import * as esbuild from 'esbuild';
import { execFileSync } from 'node:child_process';
import { existsSync, readdirSync, renameSync, rmSync } from 'node:fs';
import { join } from 'node:path';
import { OUT, ROOT, buildOptions, copyStatic } from './build.mjs';

const STUDIO = process.env.TIZEN_STUDIO || (process.platform === 'win32' ? 'C:\\tizen-studio' : `${process.env.HOME}/tizen-studio`);
const PROFILE = process.env.TIZEN_PROFILE || 'onriptv';
const APP_ID = 'OnrIptvTv1.ONRIPTV';
const win = process.platform === 'win32';
const TIZEN = join(STUDIO, 'tools', 'ide', 'bin', win ? 'tizen.bat' : 'tizen');
const SDB = join(STUDIO, 'tools', win ? 'sdb.exe' : 'sdb');
const BUILD = join(ROOT, 'build');
const WGT = join(BUILD, 'ONRIPTV.wgt');

// Tizen CLI, os.name'i yerel ayarla büyük harfe çeviriyor: Türkçe sistemde "WİNDOWS" olup
// Windows'u tanımıyor ve sertifika şifresini çözemiyor (NullPointerException). JVM'i İngilizce çalıştır.
const ENV = { ...process.env, JAVA_TOOL_OPTIONS: '-Duser.language=en -Duser.country=US' };

function run(cmd, args) {
  console.log(`> ${cmd} ${args.join(' ')}`);
  // .bat dosyaları Windows'ta kabuk üzerinden çalışır
  return execFileSync(cmd, args, { stdio: 'pipe', encoding: 'utf8', env: ENV, shell: cmd.endsWith('.bat') })
    .split(/\r?\n/).filter((l) => !l.startsWith('Picked up JAVA_TOOL_OPTIONS')).join('\n').trim();
}

if (!existsSync(TIZEN)) {
  console.error(`Tizen CLI bulunamadı: ${TIZEN}\nTizen Studio'yu kurun ya da TIZEN_STUDIO değişkenini ayarlayın (bkz. tizen/README.md).`);
  process.exit(1);
}

// 1) Derle
rmSync(OUT, { recursive: true, force: true });
copyStatic();
await esbuild.build(buildOptions(false));

// 2) İmzala ve paketle
for (const f of readdirSync(BUILD)) if (f.endsWith('.wgt')) rmSync(join(BUILD, f));
const out = run(TIZEN, ['package', '-t', 'wgt', '-s', PROFILE, '-o', BUILD, '--', OUT]);
console.log(out);
const made = readdirSync(BUILD).find((f) => f.endsWith('.wgt'));
if (!made) {
  console.error('Paket oluşturulamadı. Sertifika profilini kontrol edin (Tizen Studio → Certificate Manager).');
  process.exit(1);
}
if (join(BUILD, made) !== WGT) renameSync(join(BUILD, made), WGT);
console.log(`\nPaket hazır: ${WGT}`);

// 3) İstenirse TV'ye kur
const ip = process.argv[2];
if (ip) {
  const target = ip.indexOf(':') >= 0 ? ip : `${ip}:26101`;
  console.log(run(SDB, ['connect', target]));
  console.log(run(TIZEN, ['install', '-n', 'ONRIPTV.wgt', '-s', target, '--', BUILD]));
  console.log(run(TIZEN, ['run', '-p', APP_ID, '-s', target]));
  console.log('\nTV\'de ONR IPTV açılmış olmalı.');
}
