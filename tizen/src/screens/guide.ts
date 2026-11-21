// TV rehberi: solda kanallar, üstte saat şeridi, programlar zaman eksenine göre kutular.
// Ayrıca tek kanalın yayın akışı penceresi (showSchedule).
import { Screen, busy, toast, topScreen } from '../app';
import { currentLang, t } from '../i18n';
import { back } from '../nav';
import { Key } from '../platform';
import { Channel, Program } from '../providers/types';
import { session } from '../session';
import { h, hhmm, logo, nowSec } from '../ui/dom';
import { MenuItem, showInfo, showMenu } from '../ui/menu';
import { TopBar } from '../ui/topbar';
import { cachedTable, epgTable } from './epg';

const ROW_H = 96;
const ROWS = 7;
const PPM = 12; // dakika başına piksel
const SPAN = 120 * 60; // görünen süre (saniye)
const COL_W = 360;
const BEFORE = 3 * 3600;
const AFTER = 24 * 3600;

function dayLabel(sec: number): string {
  const d = new Date(sec * 1000);
  return d.toLocaleDateString(currentLang() === 'tr' ? 'tr-TR' : 'en-GB', { weekday: 'short', day: 'numeric', month: 'short' });
}

/** Programın ayrıntısı; şu ankiyse kanala, arşivliyse geçmiş yayına geçer. */
function programAction(ch: Channel, p: Program, onPlay: () => void, onCatchup: (ch: Channel, p: Program) => void): void {
  const now = nowSec();
  if (p.start <= now && now < p.end) { onPlay(); return; }
  if (p.end <= now && session.provider && session.provider.catchupUrl(ch, p)) { onCatchup(ch, p); return; }
  const when = `${dayLabel(p.start)} ${hhmm(p.start)} – ${hhmm(p.end)}`;
  let body = `${ch.name} · ${when}`;
  if (p.desc) body += `\n\n${p.desc.slice(0, 600)}`;
  if (p.end <= now) body += `\n\n${t('no_archive')}`;
  showInfo(p.title || t('no_epg'), body, t('close'));
}

/** Bir kanalın dünden yarına yayın akışı (catch-up destekli). */
export function showSchedule(ch: Channel, onCatchup: (ch: Channel, p: Program) => void, onPlay: () => void): void {
  const run = (progs: Program[]) => {
    if (!progs.length) { toast(t('no_epg')); return; }
    const now = nowSec();
    let start = 0;
    let lastDay = '';
    const canArchive = !!session.provider && ch.archive;
    const items: MenuItem[] = progs.map((p, i) => {
      const day = dayLabel(p.start);
      const live = p.start <= now && now < p.end;
      if (live) start = i;
      const arch = canArchive && p.end <= now && !!session.provider!.catchupUrl(ch, p);
      const note = [day !== lastDay ? day : '', live ? `● ${t('now')}` : arch ? `⟲ ${t('archive')}` : ''].filter(Boolean).join('  ');
      lastDay = day;
      return { label: `${hhmm(p.start)}   ${p.title}`, note, checked: live, run: () => programAction(ch, p, onPlay, onCatchup) };
    });
    showMenu(`${ch.name} · ${t('schedule')}`, items, start);
  };
  const c = cachedTable(ch);
  if (c) { run(c); return; }
  const owner = topScreen();
  busy(true);
  epgTable(ch).then((p) => {
    busy(false);
    if (topScreen() === owner) run(p);
  });
}

export function guideScreen(arg: { channels: Channel[]; label: string; onPlay?: (ch: Channel) => void; onCatchup?: (ch: Channel, p: Program) => void }): Screen {
  const channels = arg.channels;
  const t0 = Math.floor((nowSec() - BEFORE) / 1800) * 1800;
  const tEnd = t0 + BEFORE + AFTER;
  let winStart = Math.max(t0, Math.floor((nowSec() - 1800) / 1800) * 1800);
  let row = 0;
  let topRow = 0;
  let focusTime = nowSec();
  let gen = 0;
  const loadingSet = new Set<string>();

  const bar = new TopBar(t('tv_guide'), h('div', 'topbar-account', `${arg.label}  ·  ${t('channels_n', channels.length)}`));
  const ruler = h('div', 'guide-ruler');
  const body = h('div', 'guide-body');
  const nowLine = h('div', 'guide-now');
  const info = h('div', 'guide-info');
  const el = h('div', 'screen guide', bar.el, h('div', 'guide-grid', ruler, body, nowLine), info);

  const x = (sec: number) => COL_W + (sec - winStart) / 60 * PPM;

  function progsOf(ch: Channel): Program[] | null {
    return cachedTable(ch);
  }

  /** Satırdaki odaklı program: focusTime'ı içeren ya da ona en yakın olan. */
  function focusedProg(ch: Channel): Program | undefined {
    const progs = progsOf(ch) || [];
    return progs.find((p) => p.start <= focusTime && focusTime < p.end)
      || progs.find((p) => p.start >= focusTime) || progs[progs.length - 1];
  }

  function request() {
    const my = gen;
    channels.slice(topRow, topRow + ROWS).forEach((ch) => {
      if (progsOf(ch) || loadingSet.has(ch.id)) return;
      loadingSet.add(ch.id);
      epgTable(ch).then(() => {
        loadingSet.delete(ch.id);
        if (my === gen) draw();
      });
    });
  }

  function drawRuler() {
    ruler.innerHTML = '';
    ruler.appendChild(h('div', 'guide-day', dayLabel(Math.max(winStart, focusTime))));
    for (let s = winStart; s < winStart + SPAN; s += 1800) {
      const tick = h('div', 'guide-tick', hhmm(s));
      tick.style.left = `${x(s)}px`;
      ruler.appendChild(tick);
    }
    const n = nowSec();
    nowLine.style.display = n >= winStart && n < winStart + SPAN ? '' : 'none';
    nowLine.style.left = `${x(n)}px`;
  }

  function draw() {
    if (row < topRow) topRow = row;
    if (row >= topRow + ROWS) topRow = row - ROWS + 1;
    drawRuler();
    body.innerHTML = '';
    const winEnd = winStart + SPAN;
    const now = nowSec();
    channels.slice(topRow, topRow + ROWS).forEach((ch, i) => {
      const r = topRow + i;
      const line = h('div', `guide-row${r === row ? ' current' : ''}`);
      line.appendChild(h('div', 'guide-ch', logo(ch.logo, ch.name), h('span', 'guide-ch-name', ch.name)));
      const progs = progsOf(ch);
      const focused = r === row ? focusedProg(ch) : undefined;
      if (!progs) line.appendChild(h('div', 'guide-empty', t('loading')));
      else if (!progs.length) line.appendChild(h('div', 'guide-empty', t('no_epg')));
      else {
        progs.forEach((p) => {
          if (p.end <= winStart || p.start >= winEnd) return;
          const l = Math.max(x(p.start), COL_W);
          const w = Math.min(x(p.end), COL_W + SPAN / 60 * PPM) - l;
          const live = p.start <= now && now < p.end;
          const past = p.end <= now;
          const arch = past && ch.archive && !!session.provider && !!session.provider.catchupUrl(ch, p);
          const cell = h('div', `guide-prog${live ? ' live' : ''}${past ? ' past' : ''}${p === focused ? ' focused' : ''}`,
            h('div', 'guide-prog-title', arch ? '⟲ ' : '', p.title),
            h('div', 'guide-prog-time', `${hhmm(p.start)} – ${hhmm(p.end)}`));
          cell.style.left = `${l}px`;
          cell.style.width = `${Math.max(4, w - 6)}px`;
          line.appendChild(cell);
        });
      }
      line.style.top = `${i * ROW_H}px`;
      body.appendChild(line);
    });
    const ch = channels[row];
    const p = ch ? focusedProg(ch) : undefined;
    info.innerHTML = '';
    if (ch && p) {
      info.appendChild(h('div', 'guide-info-title', p.title));
      info.appendChild(h('div', 'guide-info-time', `${ch.name} · ${dayLabel(p.start)} ${hhmm(p.start)} – ${hhmm(p.end)}`));
      if (p.desc) info.appendChild(h('div', 'guide-info-desc', p.desc));
    }
    request();
  }

  /** Odak zamanını görünür pencerede tutar. */
  function keepVisible() {
    if (focusTime < winStart) winStart = Math.max(t0, Math.floor(focusTime / 1800) * 1800);
    if (focusTime >= winStart + SPAN - 600) winStart = Math.min(tEnd - SPAN, Math.floor((focusTime - SPAN + 1800) / 1800) * 1800);
  }

  function moveProg(dir: 1 | -1) {
    const ch = channels[row];
    const progs = ch ? progsOf(ch) || [] : [];
    const cur = ch ? focusedProg(ch) : undefined;
    const i = cur ? progs.indexOf(cur) : -1;
    const next = progs[i + dir];
    if (next) focusTime = Math.max(t0, next.start) + 1;
    else focusTime = Math.max(t0, Math.min(tEnd - 1, focusTime + dir * 1800));
    keepVisible();
    draw();
  }

  function shiftTime(sec: number) {
    focusTime = Math.max(t0, Math.min(tEnd - 1, focusTime + sec));
    keepVisible();
    draw();
  }

  function goNow() {
    focusTime = nowSec();
    winStart = Math.max(t0, Math.floor((focusTime - 1800) / 1800) * 1800);
    draw();
  }

  function activate() {
    const ch = channels[row];
    if (!ch) return;
    const p = focusedProg(ch);
    const play = () => {
      back();
      if (arg.onPlay) arg.onPlay(ch);
    };
    if (!p) { play(); return; }
    programAction(ch, p, play, (c, pr) => { if (arg.onCatchup) arg.onCatchup(c, pr); });
  }

  return {
    el,
    onShow() {
      bar.start();
      gen++;
      draw();
    },
    onHide() {
      bar.stop();
    },
    onKey(key: Key): boolean {
      switch (key) {
        case 'up': if (row > 0) { row--; draw(); } return true;
        case 'down': if (row < channels.length - 1) { row++; draw(); } return true;
        case 'chup': row = Math.max(0, row - ROWS); draw(); return true;
        case 'chdown': row = Math.min(channels.length - 1, row + ROWS); draw(); return true;
        case 'left': moveProg(-1); return true;
        case 'right': moveProg(1); return true;
        case 'rw': shiftTime(-2 * 3600); return true;
        case 'ff': shiftTime(2 * 3600); return true;
        case 'yellow': case 'okhold': goNow(); return true;
        case 'ok': activate(); return true;
        case 'back': case 'red': back(); return true;
      }
      return true;
    },
  };
}
