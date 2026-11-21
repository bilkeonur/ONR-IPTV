// Filmler / Diziler: solda kategoriler, sağda afiş ızgarası.
import { Screen, busy, toast } from '../app';
import { t } from '../i18n';
import { ADULT_RE, langOf, languages, sortItems } from '../lib';
import { back, open } from '../nav';
import { Key } from '../platform';
import { Category, Media, Section } from '../providers/types';
import { session } from '../session';
import { SortMode, store } from '../store';
import { ICONS, h, poster } from '../ui/dom';
import { MenuItem, confirm, showMenu } from '../ui/menu';
import { askPin } from '../ui/pin';
import { TopBar } from '../ui/topbar';
import { VGrid } from '../ui/vgrid';
import { VList } from '../ui/vlist';
import { sortLabel } from './live';

const SEARCH = '__search';
const ALL = '';
const FAV = '__fav';
const RECENT = '__recent';
const COLS = 6;
const CELL_W = 236;
const ROW_H = 450;
const VOD_SORTS: SortMode[] = ['default', 'new', 'az', 'za', 'rating', 'year'];

interface CatRow extends Category { locked?: boolean; special?: boolean }

/** Afiş kartı (arama ekranı da kullanır). */
export function posterCard(m: Media): HTMLElement {
  const section = m.kind;
  const watched = section === 'movie' && session.isWatched(`movie:${m.id}`);
  return h('div', 'pcard',
    poster(m.poster, m.name),
    m.rating ? h('div', { class: 'pcard-rating', html: ICONS.star }, m.rating.toFixed(1)) : null,
    h('div', 'pcard-badges',
      session.isFavorite(section, m.id) ? h('span', 'badge fav', '★') : null,
      session.isItemLocked(section, m) ? h('span', 'badge', '🔒') : null,
      watched ? h('span', 'badge seen', '✓') : null),
    h('div', 'pcard-title', m.name),
    h('div', 'pcard-sub', m.year || ''));
}

export function vodScreen(section: Section): Screen {
  let zone: 'cats' | 'grid' = 'cats';
  let loadToken = 0;
  let loadTimer = 0;
  let firstShow = true;
  let cats: CatRow[] = [];
  let raw: Media[] = [];
  const settings = store.settings();
  let sort = settings.sort[section];
  let lang = settings.langFilter[section];
  // Sayfalı bölümlerde (Stalker) yüklenen sayfa bilgisi
  let page = 0;
  let pages = 1;
  let loadingMore = false;

  const count = h('div', 'topbar-account');
  const bar = new TopBar(t(section === 'movie' ? 'tile_movies' : 'tile_series'), count);

  const catList = new VList<CatRow>('cats', 78, 936, (c) =>
    h('div', 'cat-row', h('span', 'cat-name', c.locked ? '🔒 ' : '', c.special && c.id === FAV ? '★ ' : '', c.name)),
  (c) => scheduleLoad(c.id));

  const grid = new VGrid<Media>('posters', COLS, CELL_W, ROW_H, 920, posterCard, (_m, i) => {
    if (i >= grid.length - COLS * 2) loadMore();
  });

  const empty = h('div', 'grid-empty', '');
  const el = h('div', 'screen vod',
    bar.el,
    h('div', 'vod-cats', catList.el),
    h('div', 'vod-grid', grid.el, empty));
  const searchLabel = t(section === 'movie' ? 'search_movies' : 'search_series');

  const currentCat = (): CatRow | undefined => cats[catList.index];
  const catLocked = (c: CatRow | undefined) => !!c && !!c.locked && !session.unlocked;

  function setZone(z: 'cats' | 'grid') {
    if (z === 'grid' && !grid.length) return;
    zone = z;
    catList.setActive(z === 'cats');
    grid.setActive(z === 'grid');
    el.classList.toggle('grid-focus', z === 'grid');
  }

  function scheduleLoad(catId: string) {
    clearTimeout(loadTimer);
    loadTimer = window.setTimeout(() => loadItems(catId), 300);
  }

  /** Dil ve sıralama uygulanmış liste */
  function view(items: Media[], catId: string): Media[] {
    if (catId === FAV || catId === RECENT) return items;
    let list = items;
    if (lang) {
      const names = session.catNames(section);
      list = list.filter((m) => langOf(m, names) === lang);
    }
    return sortItems(list, sort);
  }

  function show(keepIndex = false) {
    const c = currentCat();
    const catId = c ? c.id : ALL;
    const items = view(raw, catId);
    grid.setItems(items, keepIndex ? grid.index : 0);
    const msg = catId === FAV ? t('fav_empty') : catId === RECENT ? t('recent_empty') : t('no_items');
    empty.textContent = items.length ? '' : msg;
    empty.style.display = items.length ? 'none' : '';
    count.textContent = `${t('items_n', items.length)}${lang ? `  ·  ${lang}` : ''}`;
    if (!items.length && zone === 'grid') setZone('cats');
  }

  async function loadItems(catId: string) {
    const my = ++loadToken;
    const c = cats.find((x) => x.id === catId);
    page = 0;
    pages = 1;
    if (catId === SEARCH) {
      raw = [];
      grid.setItems([]);
      empty.textContent = t('search_press_ok');
      empty.style.display = '';
      count.textContent = '';
      return;
    }
    if (catLocked(c)) {
      raw = [];
      grid.setItems([]);
      empty.textContent = t('locked_press_ok');
      empty.style.display = '';
      count.textContent = '';
      return;
    }
    if (catId === FAV || catId === RECENT) {
      raw = catId === FAV ? session.favoriteMedia(section) : session.recentMedia(section);
      show();
      return;
    }
    empty.textContent = t('loading');
    empty.style.display = '';
    grid.setItems([]);
    busy(true);
    let items: Media[] = [];
    try {
      if (session.isPaged(section)) {
        const r = await session.mediaPage(section, catId, 1);
        items = r.items;
        page = 1;
        pages = r.pages;
      } else {
        items = await session.mediaItems(section, catId);
        if (catId === ALL) {
          const excl = session.excludedCats(section, await session.mediaCategories(section));
          if (excl.size) items = items.filter((m) => !excl.has(m.categoryId));
        }
      }
    } catch (e) {
      toast(t('err_load', (e as Error).message), 5000);
    } finally {
      busy(false);
    }
    if (my !== loadToken) return;
    raw = items;
    show();
  }

  async function loadMore() {
    if (!session.isPaged(section) || loadingMore || page >= pages) return;
    const c = currentCat();
    if (!c || c.special) return;
    const my = loadToken;
    loadingMore = true;
    try {
      const r = await session.mediaPage(section, c.id, page + 1);
      if (my !== loadToken) return;
      page++;
      pages = r.pages;
      raw = raw.concat(r.items);
      show(true);
    } catch { /* sonra yeniden denenir */ } finally {
      loadingMore = false;
    }
  }

  async function buildCats(selectId?: string) {
    let list: Category[] = [];
    try {
      list = await session.mediaCategories(section);
    } catch (e) {
      toast(t('err_load', (e as Error).message), 5000);
    }
    const hidden = session.hidden(section);
    cats = [
      { id: SEARCH, name: `🔍  ${searchLabel}`, special: true },
      { id: ALL, name: t('cat_all'), special: true },
      { id: FAV, name: t('cat_favorites'), special: true },
      { id: RECENT, name: t('cat_recent'), special: true },
      ...list.filter((c) => !hidden.has(c.id)).map((c) => ({ ...c, locked: session.isCatLocked(section, c) })),
    ];
    // "Tümü" büyük listelerde yavaş olabilir; ilk açılışta ilk gerçek kategori seçilir
    let idx = selectId !== undefined ? cats.findIndex((c) => c.id === selectId) : -1;
    // İlk açılışta yetişkin olmayan ilk gerçek kategori seçilir
    if (idx < 0) idx = cats.findIndex((c) => !c.special && !c.locked && !ADULT_RE.test(c.name));
    if (idx < 0) idx = 1;
    catList.setItems(cats, idx);
  }

  async function init() {
    busy(true);
    await buildCats();
    busy(false);
    setZone('cats');
    loadItems(cats[catList.index].id);
  }

  async function enterGrid() {
    const c = currentCat();
    if (c && c.id === SEARCH) { open('search', { scope: section }); return; }
    if (catLocked(c)) {
      if (!(await askPin())) return;
      await loadItems(c!.id);
    }
    setZone('grid');
  }

  async function openItem(m: Media) {
    if (session.isItemLocked(section, m) && !(await askPin())) return;
    open('detail', m);
  }

  function refresh() {
    grid.redraw();
  }

  async function toggleLock(m: Media) {
    if (!session.pinSet()) { toast(t('pin_required_first')); return; }
    if (!(await askPin())) return;
    toast(session.toggleItemLock(section, m.id) ? t('locked_item', m.name) : t('unlocked_item', m.name));
    refresh();
  }

  function toggleFav(m: Media) {
    toast(session.toggleFavorite(section, m) ? t('fav_added') : t('fav_removed'));
    const c = currentCat();
    if (c && c.id === FAV) loadItems(FAV);
    else refresh();
  }

  function saveSetting(fn: (s: ReturnType<typeof store.settings>) => void) {
    const s = store.settings();
    fn(s);
    store.saveSettings(s);
  }

  function sortMenu() {
    showMenu(t('sort'), VOD_SORTS.map((v) => ({
      label: t(sortLabel(v)), checked: sort === v,
      run: () => { sort = v; saveSetting((s) => { s.sort[section] = v; }); show(); },
    })));
  }

  function langMenu() {
    const langs = languages(raw.length ? raw : [], session.catNames(section));
    if (langs.length < 2 && !lang) { toast(t('no_languages')); return; }
    const set = (code: string) => { lang = code; saveSetting((s) => { s.langFilter[section] = code; }); show(); };
    const items: MenuItem[] = [{ label: t('lang_all'), checked: !lang, run: () => set('') }];
    langs.forEach(([code, n]) => items.push({ label: code, note: String(n), checked: lang === code, run: () => set(code) }));
    showMenu(t('content_lang'), items);
  }

  function optionsMenu() {
    const m = zone === 'grid' ? grid.current : undefined;
    const c = currentCat();
    const items: MenuItem[] = [];
    if (m) {
      items.push({ label: t('details'), run: () => openItem(m) });
      items.push({ label: session.isFavorite(section, m.id) ? t('fav_remove') : t('fav_add'), run: () => toggleFav(m) });
      if (c && c.id === RECENT) items.push({ label: t('recent_remove'), run: () => { session.removeHistory(section, m.id); loadItems(RECENT); } });
    }
    items.push({ label: searchLabel, run: () => open('search', { scope: section }) });
    items.push({ label: `${t('sort')}: ${t(sortLabel(sort))}`, run: sortMenu });
    items.push({ label: `${t('content_lang')}: ${lang || t('lang_all')}`, run: langMenu });
    if (c && c.id === RECENT && raw.length) {
      items.push({
        label: t('recent_clear'), danger: true,
        run: () => confirm(t('recent_clear_q'), t('yes'), t('no'), () => { session.clearHistory(section); loadItems(RECENT); }),
      });
    }
    if (m) items.push({ label: session.isItemSelfLocked(section, m.id) ? t('unlock') : t('lock_pin'), run: () => toggleLock(m) });
    showMenu(t('options'), items, 0);
  }

  return {
    el,
    onShow() {
      bar.start();
      if (firstShow) {
        firstShow = false;
        init();
      } else {
        // Ayrıntı ekranından dönüş: favori / izlendi işaretleri ve "son izlenen" güncellensin
        const c = currentCat();
        if (c && c.special && c.id !== ALL && c.id !== SEARCH) {
          raw = c.id === FAV ? session.favoriteMedia(section) : session.recentMedia(section);
          show(true);
        } else refresh();
      }
    },
    onHide() {
      bar.stop();
    },
    onKey(key: Key): boolean {
      if (key === 'yellow' || key === 'okhold') {
        const c = currentCat();
        if (!(zone === 'cats' && c && c.id === SEARCH)) optionsMenu();
        return true;
      }
      if (key === 'blue') { open('search', { scope: section }); return true; }
      if (key === 'green' && zone === 'grid' && grid.current) { toggleFav(grid.current); return true; }
      if (zone === 'cats') {
        switch (key) {
          case 'up': catList.move(-1); return true;
          case 'down': catList.move(1); return true;
          case 'rw': catList.page(-1); return true;
          case 'ff': catList.page(1); return true;
          case 'right': case 'ok': enterGrid(); return true;
          case 'back': back(); return true;
        }
        return true;
      }
      switch (key) {
        case 'up': grid.move(0, -1); return true;
        case 'down': grid.move(0, 1); return true;
        case 'left': if (!grid.move(-1, 0)) setZone('cats'); return true;
        case 'right': grid.move(1, 0); return true;
        case 'rw': grid.move(0, -2); return true;
        case 'ff': grid.move(0, 2); return true;
        case 'ok': if (grid.current) openItem(grid.current); return true;
        case 'back': setZone('cats'); return true;
      }
      return true;
    },
  };
}
