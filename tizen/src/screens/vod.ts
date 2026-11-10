// Filmler / Diziler: solda kategoriler, sağda afiş ızgarası.
import { Screen, busy, toast } from '../app';
import { t } from '../i18n';
import { back, open } from '../nav';
import { Key } from '../platform';
import { Category, Media, Section } from '../providers/types';
import { session } from '../session';
import { ICONS, h, poster } from '../ui/dom';
import { TopBar } from '../ui/topbar';
import { VGrid } from '../ui/vgrid';
import { VList } from '../ui/vlist';

const ALL = '';
const COLS = 6;
const CELL_W = 236;
const ROW_H = 420;

export function vodScreen(section: Section): Screen {
  let zone: 'cats' | 'grid' = 'cats';
  let loadToken = 0;
  let loadTimer = 0;
  let firstShow = true;

  const count = h('div', 'topbar-account');
  const bar = new TopBar(t(section === 'movie' ? 'tile_movies' : 'tile_series'), count);

  const catList = new VList<Category>('cats', 76, 900, (c) =>
    h('div', 'cat-row', h('span', 'cat-name', c.name)),
  (c) => scheduleLoad(c.id));

  const grid = new VGrid<Media>('posters', COLS, CELL_W, ROW_H, 940, (m) =>
    h('div', 'pcard',
      poster(m.poster, m.name),
      m.rating ? h('div', { class: 'pcard-rating', html: ICONS.star }, m.rating.toFixed(1)) : null,
      h('div', 'pcard-title', m.name),
      h('div', 'pcard-sub', m.year || '')));

  const empty = h('div', 'grid-empty', '');
  const el = h('div', 'screen vod',
    bar.el,
    h('div', 'vod-cats', catList.el),
    h('div', 'vod-grid', grid.el, empty));

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

  async function loadItems(catId: string) {
    const my = ++loadToken;
    empty.textContent = t('loading');
    empty.style.display = '';
    grid.setItems([]);
    busy(true);
    let items: Media[] = [];
    try {
      items = await session.mediaItems(section, catId);
    } catch (e) {
      toast(t('err_load', (e as Error).message), 5000);
    } finally {
      busy(false);
    }
    if (my !== loadToken) return;
    grid.setItems(items);
    empty.textContent = items.length ? '' : t('no_items');
    empty.style.display = items.length ? 'none' : '';
    count.textContent = t('items_n', items.length);
  }

  async function init() {
    busy(true);
    let cats: Category[] = [];
    try {
      cats = await session.mediaCategories(section);
    } catch (e) {
      toast(t('err_load', (e as Error).message), 5000);
    } finally {
      busy(false);
    }
    // "Tümü" büyük listelerde yavaş olabilir; ilk açılışta ilk gerçek kategori seçilir
    const list = [{ id: ALL, name: t('cat_all') }, ...cats];
    catList.setItems(list, cats.length ? 1 : 0);
    setZone('cats');
    loadItems(list[catList.index].id);
  }

  return {
    el,
    onShow() {
      bar.start();
      if (firstShow) {
        firstShow = false;
        init();
      }
    },
    onHide() {
      bar.stop();
    },
    onKey(key: Key): boolean {
      if (zone === 'cats') {
        switch (key) {
          case 'up': catList.move(-1); return true;
          case 'down': catList.move(1); return true;
          case 'rw': catList.page(-1); return true;
          case 'ff': catList.page(1); return true;
          case 'right': case 'ok': setZone('grid'); return true;
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
        case 'ok': if (grid.current) open('detail', grid.current); return true;
        case 'back': setZone('cats'); return true;
      }
      return true;
    },
  };
}
