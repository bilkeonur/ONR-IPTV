// Canlı TV: yayın hep tam ekran; OK ile videonun üstünde kanal listesi paneli açılır.
import { Screen, busy, toast } from '../app';
import { t } from '../i18n';
import { langOf, languages, sortItems } from '../lib';
import { back, open } from '../nav';
import { Key } from '../platform';
import { FULL, PlayerState, player } from '../player';
import { Category, Channel, Program } from '../providers/types';
import { session } from '../session';
import { SortMode, store } from '../store';
import { h, hhmm, icon, logo } from '../ui/dom';
import { MenuItem, confirm, showMenu } from '../ui/menu';
import { askPin } from '../ui/pin';
import { playerMenu, resetSubtitles } from '../ui/playeropts';
import { VList } from '../ui/vlist';
import { cachedEpg, nowNext, progress, requestEpg } from './epg';
import { showSchedule } from './guide';

const SEARCH = '__search';
const ALL = '__all';
const FAV = '__fav';
const RECENT = '__recent';
const OTHER = '__other';

type Mode = 'list' | 'full';
type Zone = 'cats' | 'chans';

interface CatRow extends Category { count: number; locked?: boolean }

export const LIVE_SORTS: SortMode[] = ['default', 'num', 'az', 'za', 'new'];

export function liveScreen(arg: { channelId?: string } | void): Screen {
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
  let retryTimer = 0;
  let retries = 0;
  let playToken = 0;
  let firstShow = true;
  const settings = store.settings();
  let sort = settings.sort.live;
  let lang = settings.langFilter.live;
  const showEpg = settings.showEpgInList;

  // ---- Kategoriler
  const catList = new VList<CatRow>('cats', 79, 948, (c) =>
    h('div', 'cat-row', h('span', 'cat-name', c.locked ? '🔒 ' : '', c.name), h('span', 'cat-count', c.count >= 0 ? String(c.count) : '')),
  (c) => fillChannels(c.id));

  // ---- Kanallar
  const chanList = new VList<Channel>('chans', 105, 945, (ch) => {
    const { now } = showEpg ? nowNext(cachedEpg(ch)) : { now: undefined };
    const locked = session.isItemLocked('live', ch);
    return h('div', { class: `chan-row${current && current.id === ch.id ? ' playing' : ''}`, 'data-ch': ch.id },
      h('span', 'chan-num', String(ch.num || '')),
      logo(ch.logo, ch.name),
      h('div', 'chan-main',
        h('div', 'chan-name', locked ? '🔒 ' : '', ch.name, session.isFavorite('live', ch.id) ? h('span', 'chan-fav', ' ★') : null,
          ch.archive ? h('span', 'chan-archive', ' ⟲') : null),
        h('div', 'chan-prog', now ? now.title : ''),
        showEpg ? h('div', 'bar thin', h('div', { class: 'bar-fill', style: `width:${now ? progress(now) : 0}%` })) : null));
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
  const subs = h('div', 'subtitle');

  const el = h('div', 'screen live', status, subs, panel, detail, osd, numBox);

  // ---- Listeler
  const known = () => new Set(session.categories.map((c) => c.id));

  function baseChannels(catId: string): Channel[] {
    if (catId === FAV) return session.favoriteChannels();
    if (catId === RECENT) return session.recentChannels();
    if (catId === OTHER) {
      const k = known();
      return session.channels.filter((c) => !k.has(c.categoryId));
    }
    if (catId === ALL) {
      const excl = session.excludedCats('live', session.categories);
      return excl.size ? session.channels.filter((c) => !excl.has(c.categoryId)) : session.channels;
    }
    return session.channels.filter((c) => c.categoryId === catId);
  }

  function channelsOf(catId: string): Channel[] {
    let list = baseChannels(catId);
    if (catId === FAV || catId === RECENT) return list;
    if (lang) {
      const names = session.catNames('live');
      list = list.filter((c) => langOf(c, names) === lang);
    }
    return sortItems(list, sort);
  }

  function buildCats() {
    const counts: Record<string, number> = {};
    session.channels.forEach((c) => { counts[c.categoryId] = (counts[c.categoryId] || 0) + 1; });
    const hidden = session.hidden('live');
    cats = [
      { id: SEARCH, name: `🔍  ${t('search_channels')}`, count: -1 },
      { id: ALL, name: t('cat_all_channels'), count: baseChannels(ALL).length },
      { id: FAV, name: t('cat_favorites'), count: session.user.fav.live.length },
      { id: RECENT, name: t('cat_recent'), count: session.recentChannels().length },
      ...session.categories.filter((c) => counts[c.id] && !hidden.has(c.id))
        .map((c) => ({ ...c, count: counts[c.id], locked: session.isCatLocked('live', c) })),
    ];
    const orphans = baseChannels(OTHER).length;
    if (orphans && session.categories.length) cats.push({ id: OTHER, name: t('cat_other'), count: orphans });
  }

  function catLocked(catId: string): boolean {
    const c = cats.find((x) => x.id === catId);
    return !!c && !!c.locked && !session.unlocked;
  }

  function fillChannels(catId: string, selectId?: string) {
    if (catId === SEARCH) {
      chanTitle.textContent = t('search_channels');
      chanList.setItems([]);
      chanList.el.classList.add('empty');
      chanList.el.setAttribute('data-empty', t('search_press_ok'));
      showDetail(null);
      return;
    }
    const cat = cats.find((c) => c.id === catId);
    const locked = catLocked(catId);
    const list = locked ? [] : channelsOf(catId);
    chanTitle.textContent = `${cat ? cat.name : ''}  ·  ${t('channels_n', list.length)}${lang ? `  ·  ${lang}` : ''}`;
    const idx = selectId ? Math.max(0, list.findIndex((c) => c.id === selectId)) : 0;
    chanList.setItems(list, idx);
    chanList.el.classList.toggle('empty', !list.length);
    chanList.el.setAttribute('data-empty', locked ? t('locked_press_ok')
      : catId === FAV ? t('fav_empty') : catId === RECENT ? t('recent_empty') : t('no_channels'));
    showDetail(chanList.current || null);
    scheduleEpg();
  }

  function refill() {
    const cat = cats[catList.index];
    const sel = chanList.current;
    buildCats();
    catList.setItems(cats, Math.max(0, cats.findIndex((c) => cat && c.id === cat.id)));
    fillChannels(cats[catList.index].id, sel ? sel.id : undefined);
  }

  // ---- Yayın akışı
  function scheduleEpg() {
    if (!showEpg && mode === 'list') return;
    clearTimeout(epgTimer);
    epgTimer = window.setTimeout(() => {
      requestEpg(showEpg ? chanList.visibleItems() : chanList.current ? [chanList.current] : [], (ch) => {
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
    if (!progs) return h('div', 'muted', t('loading'));
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
    if (session.isItemLocked('live', ch) && !session.unlocked) detail.appendChild(h('div', 'muted', `🔒 ${t('locked')}`));
    else detail.appendChild(epgBlock(ch, true));
  }

  function showOsd(autoHide = true) {
    if (!current) return;
    osd.innerHTML = '';
    osd.appendChild(h('div', 'osd-inner',
      logo(current.logo, current.name, 'logo big'),
      h('div', 'osd-main',
        h('div', 'osd-title', h('span', 'osd-num', String(current.num || '')), current.name,
          session.isFavorite('live', current.id) ? h('span', 'chan-fav', ' ★') : null),
        epgBlock(current, false)),
));
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
  }

  function setZone(z: Zone) {
    zone = z;
    el.classList.toggle('cats-open', z === 'cats');
    catList.setActive(z === 'cats');
    chanList.setActive(z === 'chans');
  }

  async function enterChannels() {
    const cat = cats[catList.index];
    if (cat && cat.id === SEARCH) { openSearch(); return; }
    if (cat && catLocked(cat.id)) {
      if (!(await askPin())) return;
      fillChannels(cat.id);
    }
    setZone('chans');
  }

  // ---- Oynatma
  async function play(ch: Channel, full = false): Promise<boolean> {
    if (!session.provider) return false;
    if (session.isItemLocked('live', ch) && !(await askPin())) return false;
    const my = ++playToken;
    current = ch;
    retries = 0;
    clearTimeout(retryTimer);
    chanList.refresh();
    session.addHistory('live', ch);
    resetSubtitles();
    if (full) {
      setMode('full');
      showOsd();
    }
    let url: string;
    try {
      url = await session.provider.streamUrl(ch);
    } catch (e) {
      if (my === playToken) onPlayerState('error');
      toast((e as Error).message);
      return true;
    }
    if (my !== playToken) return true;
    player.play(url, FULL);
    if (!cachedEpg(ch)) requestEpg([ch], () => mode === 'full' && current === ch && showOsd());
    return true;
  }

  function onPlayerState(s: PlayerState) {
    if (s === 'playing') retries = 0;
    if (s === 'error' && current && store.settings().autoReconnect && retries < 3) {
      // Yayın koparsa birkaç kez yeniden dene
      retries++;
      status.className = 'video-status loading';
      status.textContent = '';
      const ch = current;
      clearTimeout(retryTimer);
      retryTimer = window.setTimeout(() => {
        if (current !== ch || !session.provider) return;
        session.provider.streamUrl(ch).then((u) => { if (current === ch) player.play(u, FULL); }).catch(() => onPlayerState('error'));
      }, 2000 * retries);
      return;
    }
    status.className = `video-status ${s}`;
    status.textContent = s === 'error' ? t('err_play') : '';
    if (s === 'paused') status.appendChild(icon('pause', 'state-icon'));
    if (s !== 'playing' && s !== 'paused') subs.textContent = '';
  }

  /** Tam ekranda OK ve oynat/duraklat tuşları: yayını durdurur ya da sürdürür. */
  function togglePause() {
    if (player.state === 'error' && current) { play(current); return; }
    player.togglePause();
    if (mode === 'full') showOsd(player.state !== 'paused');
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

  function selectChannel(id: string, full: boolean) {
    const cat = cats[catList.index];
    let i = cat && !catLocked(cat.id) ? channelsOf(cat.id).findIndex((c) => c.id === id) : -1;
    if (i < 0) {
      catList.select(Math.max(0, cats.findIndex((c) => c.id === ALL)), true);
      fillChannels(ALL, id);
      i = chanList.current && chanList.current.id === id ? chanList.index : -1;
    } else chanList.select(i, true);
    const ch = i >= 0 ? chanList.current : session.channels.find((c) => c.id === id);
    if (ch) play(ch, full);
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
      const inCat = cat && !catLocked(cat.id) ? channelsOf(cat.id).find((c) => c.num === n) : undefined;
      const ch = inCat || session.channels.find((c) => c.num === n);
      if (ch) selectChannel(ch.id, true);
    }, 1500);
  }

  function target(): Channel | null {
    return mode === 'full' ? current : chanList.current || null;
  }

  function toggleFav(ch: Channel | null = target()) {
    if (!ch) return;
    toast(session.toggleFavorite('live', ch) ? t('fav_added') : t('fav_removed'));
    const favCat = cats.find((c) => c.id === FAV);
    if (favCat) favCat.count = session.user.fav.live.length;
    catList.refresh();
    if (cats[catList.index] && cats[catList.index].id === FAV) fillChannels(FAV, ch.id);
    else chanList.refresh();
    if (mode === 'full') showOsd();
  }

  async function toggleLock(ch: Channel) {
    if (!session.pinSet()) { toast(t('pin_required_first')); return; }
    if (!(await askPin())) return;
    toast(session.toggleItemLock('live', ch.id) ? t('locked_item', ch.name) : t('unlocked_item', ch.name));
    chanList.refresh();
    showDetail(chanList.current || null);
  }

  function guide() {
    const cat = cats[catList.index];
    if (!cat || catLocked(cat.id) || cat.id === SEARCH) return;
    open('guide', {
      channels: channelsOf(cat.id),
      label: cat.name,
      onPlay: (ch) => selectChannel(ch.id, true),
      onCatchup: (ch, p) => playCatchup(ch, p),
    });
  }

  function sortMenu() {
    showMenu(t('sort'), LIVE_SORTS.map((v) => ({
      label: t(sortLabel(v)),
      checked: sort === v,
      run: () => {
        sort = v;
        const s = store.settings();
        s.sort.live = v;
        store.saveSettings(s);
        refill();
      },
    })));
  }

  function langMenu() {
    const langs = languages(session.channels, session.catNames('live'));
    if (langs.length < 2) { toast(t('no_languages')); return; }
    const items: MenuItem[] = [{ label: t('lang_all'), checked: !lang, run: () => setLangFilter('') }];
    langs.forEach(([code, n]) => items.push({ label: code, note: String(n), checked: lang === code, run: () => setLangFilter(code) }));
    showMenu(t('content_lang'), items);
  }

  function setLangFilter(code: string) {
    lang = code;
    const s = store.settings();
    s.langFilter.live = code;
    store.saveSettings(s);
    refill();
  }

  function optionsMenu() {
    const ch = target();
    const cat = cats[catList.index];
    const items: MenuItem[] = [];
    if (ch) {
      items.push({ label: session.isFavorite('live', ch.id) ? t('fav_remove') : t('fav_add'), run: () => toggleFav(ch) });
      items.push({ label: t('schedule'), run: () => showSchedule(ch, (c, p) => playCatchup(c, p), () => selectChannel(ch.id, true)) });
    }
    if (mode === 'list') {
      items.push({ label: t('tv_guide'), run: guide });
      items.push({ label: t('search_channels'), run: () => openSearch() });
      items.push({ label: `${t('sort')}: ${t(sortLabel(sort))}`, run: sortMenu });
      items.push({ label: `${t('content_lang')}: ${lang || t('lang_all')}`, run: langMenu });
      if (cat && cat.id === RECENT && ch) {
        items.push({ label: t('recent_remove'), run: () => { session.removeHistory('live', ch.id); refill(); } });
        items.push({
          label: t('recent_clear'), danger: true,
          run: () => confirm(t('recent_clear_q'), t('yes'), t('no'), () => { session.clearHistory('live'); refill(); }),
        });
      }
    }
    if (ch) items.push({ label: session.isItemSelfLocked('live', ch.id) ? t('unlock') : t('lock_pin'), run: () => toggleLock(ch) });
    if (mode === 'full') playerMenu(items);
    else showMenu(t('options'), items, 0);
  }

  function openSearch() {
    // Yalnızca kanallarda arar; seçilen kanal bu ekranda açılır
    open('search', { scope: 'live', onChannel: (ch) => selectChannel(ch.id, true) });
  }

  function playCatchup(ch: Channel, p: Program) {
    if (!session.provider) return;
    const url = session.provider.catchupUrl(ch, p);
    if (!url) return;
    open('play', {
      media: { kind: 'movie', id: `catchup:${ch.id}`, name: ch.name, poster: ch.logo, categoryId: '', rating: 0, year: '' },
      catchup: { ch, prog: p, url },
    });
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
    // Her açılışta "Tüm kanallar"daki yetişkin olmayan ilk kanal arkada başlar
    const ci = Math.max(0, cats.findIndex((c) => c.id === ALL));
    const first = channelsOf(ALL).find((c) => !session.isAdult('live', c) && !session.isItemLocked('live', c));
    catList.setItems(cats, ci);
    fillChannels(ALL, first ? first.id : undefined);
    setMode('list');
    loading = false;
    if (arg && arg.channelId) selectChannel(arg.channelId, true);
    else if (first) play(first);
  }

  return {
    el,
    onShow() {
      unsub = player.onState(onPlayerState);
      player.onSubtitle((text) => { subs.textContent = text; });
      if (firstShow) {
        firstShow = false;
        load();
      } else {
        // Arama, rehber ya da catch-up'tan dönüş: listeyi tazele, kanalı yeniden aç
        refill();
        if (current) {
          const ch = current;
          current = null;
          play(ch);
        }
      }
    },
    onHide() {
      if (unsub) unsub();
      player.onSubtitle(null);
      clearTimeout(retryTimer);
      playToken++;
      player.stop();
      subs.textContent = '';
    },
    onDestroy() {
      current = null;
    },
    onKey(key: Key): boolean {
      if (loading && key !== 'back') return true;
      if (key.length === 1 && key >= '0' && key <= '9') { digit(key); return true; }
      if (key === 'green') { toggleFav(); return true; }
      if (key === 'yellow' || key === 'okhold') {
        if (mode === 'list' && zone === 'cats') return true;
        optionsMenu();
        return true;
      }
      if (key === 'blue') { openSearch(); return true; }
      if (key === 'red') {
        if (mode === 'full' && current) showSchedule(current, (c, p) => playCatchup(c, p), () => undefined);
        else guide();
        return true;
      }
      if (key === 'playpause' || key === 'play' || key === 'pause') { togglePause(); return true; }

      if (mode === 'full') {
        switch (key) {
          case 'up': case 'chup': zap(-1); return true;
          case 'down': case 'chdown': zap(1); return true;
          case 'info': showOsd(); return true;
          case 'ok': togglePause(); return true;
          case 'left': setMode('list'); return true;
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
        case 'right': if (zone === 'cats') enterChannels(); return true;
        case 'info': {
          const ch = chanList.current;
          if (ch) showSchedule(ch, (c, p) => playCatchup(c, p), () => selectChannel(ch.id, true));
          return true;
        }
        case 'ok':
          if (zone === 'cats') { enterChannels(); return true; }
          if (chanList.current) {
            const ch = chanList.current;
            if (!current || current.id !== ch.id || player.state === 'error') play(ch, true);
            else {
              setMode('full');
              showOsd();
            }
          } else if (catLocked(cats[catList.index] ? cats[catList.index].id : '')) enterChannels();
          return true;
        case 'back':
          // Tam ekran → kanal listesi → kategoriler → ana ekran
          if (zone === 'chans') setZone('cats');
          else back();
          return true;
      }
      return false;
    },
  };
}

export function sortLabel(v: SortMode): 'sort_default' | 'sort_num' | 'sort_az' | 'sort_za' | 'sort_new' | 'sort_rating' | 'sort_year' {
  return `sort_${v === 'default' ? 'default' : v}` as 'sort_default';
}
