// Canlı TV: yayın hep tam ekran; OK ile videonun üstünde kanal listesi paneli açılır.
import { Screen, busy, toast } from '../app';
import { t } from '../i18n';
import { back } from '../nav';
import { Key } from '../platform';
import { FULL, PlayerState, player } from '../player';
import { Category, Channel, Program } from '../providers/types';
import { session } from '../session';
import { store } from '../store';
import { h, hhmm, logo, nowSec } from '../ui/dom';
import { VList } from '../ui/vlist';

const ALL = '__all';
const FAV = '__fav';
const OTHER = '__other';

type Mode = 'list' | 'full';
type Zone = 'cats' | 'chans';

interface CatRow extends Category { count: number }

// ---- Yayın akışı önbelleği ve sıralı yükleme (aynı anda en fazla 3 istek)
const epgCache = new Map<string, { at: number; progs: Program[] }>();
const pending = new Set<string>();
let queue: Channel[] = [];
let running = 0;

function cachedEpg(ch: Channel): Program[] | null {
  const c = epgCache.get(ch.id);
  return c && Date.now() - c.at < 5 * 60000 ? c.progs : null;
}

function requestEpg(chans: Channel[], done: (ch: Channel) => void): void {
  queue = chans.filter((c) => !cachedEpg(c) && !pending.has(c.id));
  const pump = () => {
    while (running < 3 && queue.length) {
      const ch = queue.shift() as Channel;
      pending.add(ch.id);
      running++;
      const p = session.provider ? session.provider.shortEpg(ch) : Promise.resolve([]);
      p.catch(() => [] as Program[]).then((progs) => {
        epgCache.set(ch.id, { at: Date.now(), progs });
        pending.delete(ch.id);
        running--;
        done(ch);
        pump();
      });
    }
  };
  pump();
}

function nowNext(progs: Program[] | null): { now?: Program; next?: Program } {
  if (!progs) return {};
  const n = nowSec();
  const i = progs.findIndex((p) => p.start <= n && n < p.end);
  if (i >= 0) return { now: progs[i], next: progs[i + 1] };
  return { next: progs.find((p) => p.start > n) };
}

const progress = (p: Program): number =>
  Math.max(0, Math.min(100, ((nowSec() - p.start) / Math.max(1, p.end - p.start)) * 100));

export function liveScreen(): Screen {
  let mode: Mode = 'list';
  let zone: Zone = 'chans';
  let cats: CatRow[] = [];
  let current: Channel | null = null;
  let loading = false;
  let unsub: (() => void) | null = null;
  let osdTimer = 0;
  let epgTimer = 0;
  let digits = '';
  let digitTimer = 0;

  // ---- Kategoriler
  const catList = new VList<CatRow>('cats', 76, 836, (c) =>
    h('div', 'cat-row', h('span', 'cat-name', c.name), h('span', 'cat-count', String(c.count))),
  (c) => fillChannels(c.id));

  // ---- Kanallar
  const chanList = new VList<Channel>('chans', 100, 900, (ch) => {
    const { now } = nowNext(cachedEpg(ch));
    return h('div', { class: `chan-row${current && current.id === ch.id ? ' playing' : ''}`, 'data-ch': ch.id },
      h('span', 'chan-num', String(ch.num || '')),
      logo(ch.logo, ch.name),
      h('div', 'chan-main',
        h('div', 'chan-name', ch.name, session.favorites.has(ch.id) ? h('span', 'chan-fav', ' ★') : null),
        h('div', 'chan-prog', now ? now.title : ''),
        h('div', 'bar thin', h('div', { class: 'bar-fill', style: `width:${now ? progress(now) : 0}%` }))));
  }, (ch) => { showDetail(ch); scheduleEpg(); });

  const catTitle = h('div', 'panel-title', t('categories'));
  const chanTitle = h('div', 'panel-title', '');
  const catCol = h('div', 'panel-col cats-col', catTitle, catList.el);
  const chanCol = h('div', 'panel-col chans-col', chanTitle, chanList.el);
  const panel = h('div', 'chpanel', catCol, chanCol);

  // Seçili kanalın ayrıntısı (panel açıkken sağ altta)
  const detail = h('div', 'chdetail');
  const status = h('div', 'video-status');
  const osd = h('div', 'osd');
  const numBox = h('div', 'num-entry');
  const hint = h('div', 'hint', '');

  const el = h('div', 'screen live', status, panel, detail, osd, numBox, hint);

  // ---- Listeler
  function channelsOf(catId: string): Channel[] {
    if (catId === ALL) return session.channels;
    if (catId === FAV) return session.channels.filter((c) => session.favorites.has(c.id));
    if (catId === OTHER) {
      const known = new Set(session.categories.map((c) => c.id));
      return session.channels.filter((c) => !known.has(c.categoryId));
    }
    return session.channels.filter((c) => c.categoryId === catId);
  }

  function buildCats() {
    const counts: Record<string, number> = {};
    session.channels.forEach((c) => { counts[c.categoryId] = (counts[c.categoryId] || 0) + 1; });
    cats = [
      { id: ALL, name: t('cat_all_channels'), count: session.channels.length },
      { id: FAV, name: t('cat_favorites'), count: session.favorites.size },
      ...session.categories.filter((c) => counts[c.id]).map((c) => ({ ...c, count: counts[c.id] })),
    ];
    const orphans = channelsOf(OTHER).length;
    if (orphans && session.categories.length) cats.push({ id: OTHER, name: t('cat_other'), count: orphans });
  }

  function fillChannels(catId: string, selectId?: string) {
    const list = channelsOf(catId);
    const cat = cats.find((c) => c.id === catId);
    chanTitle.textContent = `${cat ? cat.name : ''}  ·  ${t('channels_n', list.length)}`;
    const idx = selectId ? Math.max(0, list.findIndex((c) => c.id === selectId)) : 0;
    chanList.setItems(list, idx);
    chanList.el.classList.toggle('empty', !list.length);
    chanList.el.setAttribute('data-empty', t('no_channels'));
    showDetail(chanList.current || null);
    scheduleEpg();
  }

  // ---- Yayın akışı
  function scheduleEpg() {
    clearTimeout(epgTimer);
    epgTimer = window.setTimeout(() => {
      requestEpg(chanList.visibleItems(), (ch) => {
        updateRow(ch);
        if (chanList.current === ch) showDetail(ch);
        if (current === ch && osd.classList.contains('show')) showOsd(false);
      });
    }, 250);
  }

  function updateRow(ch: Channel) {
    const row = chanList.el.querySelector(`[data-ch="${CSS.escape(ch.id)}"]`);
    if (!row) return;
    const { now } = nowNext(cachedEpg(ch));
    const prog = row.querySelector('.chan-prog');
    const fill = row.querySelector('.bar-fill') as HTMLElement | null;
    if (prog) prog.textContent = now ? now.title : '';
    if (fill) fill.style.width = `${now ? progress(now) : 0}%`;
  }

  function epgBlock(ch: Channel, withDesc: boolean): HTMLElement {
    const progs = cachedEpg(ch);
    if (!progs) return h('div', 'muted', session.provider && session.provider.kind === 'm3u' ? '' : t('loading'));
    const { now, next } = nowNext(progs);
    if (!now && !next) return h('div', 'muted', t('no_epg'));
    return h('div', 'epg',
      now ? h('div', 'epg-now',
        h('div', 'epg-line', h('span', 'epg-tag', t('now')), h('span', 'epg-time', `${hhmm(now.start)} – ${hhmm(now.end)}`), h('span', 'epg-title', now.title)),
        h('div', 'bar', h('div', { class: 'bar-fill', style: `width:${progress(now)}%` })),
        withDesc && now.desc ? h('div', 'epg-desc', now.desc) : null) : null,
      next ? h('div', 'epg-line next', h('span', 'epg-tag', t('next')), h('span', 'epg-time', hhmm(next.start)), h('span', 'epg-title', next.title)) : null);
  }

  function showDetail(ch: Channel | null) {
    detail.innerHTML = '';
    if (!ch) return;
    detail.appendChild(h('div', 'chdetail-head', logo(ch.logo, ch.name, 'logo big'),
      h('div', 'chdetail-name', h('span', 'osd-num', String(ch.num || '')), ch.name)));
    detail.appendChild(epgBlock(ch, true));
  }

  function showOsd(autoHide = true) {
    if (!current) return;
    osd.innerHTML = '';
    osd.appendChild(h('div', 'osd-inner',
      logo(current.logo, current.name, 'logo big'),
      h('div', 'osd-main',
        h('div', 'osd-title', h('span', 'osd-num', String(current.num || '')), current.name,
          session.favorites.has(current.id) ? h('span', 'chan-fav', ' ★') : null),
        epgBlock(current, false))));
    osd.classList.add('show');
    clearTimeout(osdTimer);
    if (autoHide) osdTimer = window.setTimeout(() => osd.classList.remove('show'), 5000);
  }

  // ---- Görünüm
  function setMode(m: Mode) {
    mode = m;
    el.classList.toggle('list-open', m === 'list');
    setZone('chans');
    if (m === 'list') {
      osd.classList.remove('show');
      showDetail(chanList.current || null);
      scheduleEpg();
    }
    hint.textContent = m === 'list' ? t('hint_list') : '';
  }

  function setZone(z: Zone) {
    zone = z;
    el.classList.toggle('cats-open', z === 'cats');
    catList.setActive(z === 'cats');
    chanList.setActive(z === 'chans');
  }

  // ---- Oynatma
  function play(ch: Channel) {
    if (!session.provider) return;
    current = ch;
    player.play(session.provider.streamUrl(ch), FULL);
    chanList.refresh();
    const cat = cats[catList.index];
    store.setLastChannel(session.pid, { cat: cat ? cat.id : ALL, id: ch.id });
    if (!cachedEpg(ch)) requestEpg([ch], () => mode === 'full' && current === ch && showOsd());
  }

  function onPlayerState(s: PlayerState) {
    status.className = `video-status ${s}`;
    status.textContent = s === 'error' ? t('err_play') : '';
  }

  function zap(delta: number) {
    if (!chanList.length) return;
    let i = chanList.index + delta;
    if (i < 0) i = chanList.length - 1;
    if (i >= chanList.length) i = 0;
    chanList.select(i, true);
    const ch = chanList.current;
    if (ch) {
      play(ch);
      if (mode === 'full') showOsd();
      else showDetail(ch);
    }
  }

  function digit(d: string) {
    digits = (digits + d).slice(-4);
    numBox.textContent = digits;
    numBox.classList.add('show');
    clearTimeout(digitTimer);
    digitTimer = window.setTimeout(() => {
      numBox.classList.remove('show');
      const n = parseInt(digits, 10);
      digits = '';
      const cat = cats[catList.index];
      let i = cat ? channelsOf(cat.id).findIndex((c) => c.num === n) : -1;
      if (i < 0) {
        if (!session.channels.some((c) => c.num === n)) return;
        catList.select(0, true);
        fillChannels(ALL);
        i = session.channels.findIndex((c) => c.num === n);
      }
      chanList.select(i, true);
      const ch = chanList.current;
      if (ch) {
        play(ch);
        setMode('full');
        showOsd();
      }
    }, 1500);
  }

  function toggleFav() {
    const ch = mode === 'full' ? current : chanList.current;
    if (!ch) return;
    toast(session.toggleFavorite(ch) ? t('fav_added') : t('fav_removed'));
    const favCat = cats.find((c) => c.id === FAV);
    if (favCat) favCat.count = session.favorites.size;
    catList.refresh();
    if (cats[catList.index] && cats[catList.index].id === FAV) fillChannels(FAV, ch.id);
    else chanList.refresh();
    if (mode === 'full') showOsd();
  }

  async function load() {
    loading = true;
    busy(true);
    try {
      await session.loadLive();
    } catch (e) {
      toast(t('err_load', (e as Error).message), 6000);
    } finally {
      busy(false);
    }
    buildCats();
    const last = store.lastChannel(session.pid);
    let ci = last ? cats.findIndex((c) => c.id === last.cat) : -1;
    if (ci < 0) ci = 0;
    catList.setItems(cats, ci);
    fillChannels(cats[ci].id, last ? last.id : undefined);
    const ch = chanList.current;
    setMode('list');
    // Son izlenen kanal arkada hemen başlasın
    if (last && ch && ch.id === last.id) play(ch);
    loading = false;
  }

  return {
    el,
    onShow() {
      unsub = player.onState(onPlayerState);
      load();
    },
    onHide() {
      if (unsub) unsub();
      player.stop();
      current = null;
    },
    onKey(key: Key): boolean {
      if (loading && key !== 'back') return true;
      if (key.length === 1 && key >= '0' && key <= '9') { digit(key); return true; }
      if (key === 'green') { toggleFav(); return true; }
      if (key === 'playpause' || key === 'play' || key === 'pause') { player.togglePause(); return true; }

      if (mode === 'full') {
        switch (key) {
          case 'up': case 'chup': zap(-1); return true;
          case 'down': case 'chdown': zap(1); return true;
          case 'info': showOsd(); return true;
          case 'ok': case 'left': setMode('list'); return true;
          case 'back': setMode('list'); return true;
          default: return true;
        }
      }

      // Liste açık
      if (key === 'chup' || key === 'chdown') { zap(key === 'chup' ? -1 : 1); return true; }
      const list = zone === 'cats' ? catList : chanList;
      switch (key) {
        case 'up': list.move(-1); return true;
        case 'down': list.move(1); return true;
        case 'rw': list.page(-1); return true;
        case 'ff': list.page(1); return true;
        case 'left': if (zone === 'chans') setZone('cats'); return true;
        case 'right': if (zone === 'cats') setZone('chans'); return true;
        case 'ok':
          if (zone === 'cats') { setZone('chans'); return true; }
          if (chanList.current) {
            if (!current || current.id !== chanList.current.id || player.state === 'error') play(chanList.current);
            setMode('full');
            showOsd();
          }
          return true;
        case 'back':
          // Tam ekran → liste → ana ekran
          if (zone === 'cats') setZone('chans');
          else back();
          return true;
      }
      return false;
    },
  };
}
