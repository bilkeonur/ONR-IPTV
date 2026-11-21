// Kategori gizleme / kilitleme: listeden işaretlenir, Geri ile kaydedilir.
import { Screen, busy, toast } from '../app';
import { t } from '../i18n';
import { ADULT_RE } from '../lib';
import { back } from '../nav';
import { Key } from '../platform';
import { AnySection, Category, Section } from '../providers/types';
import { session } from '../session';
import { store } from '../store';
import { h } from '../ui/dom';
import { TopBar } from '../ui/topbar';
import { VList } from '../ui/vlist';

export function catPickerScreen(arg: { section: AnySection; mode: 'hide' | 'lock' }): Screen {
  const { section, mode } = arg;
  const selected = new Set(mode === 'hide' ? session.pset.hidden[section] : session.pset.locks[section].cats);
  const initial = Array.from(selected).sort().join('|');
  let cats: Category[] = [];
  const adultAuto = mode === 'lock' && store.settings().lockAdult;

  const title = `${t(mode === 'hide' ? 'hide_cats' : 'lock_cats')} · ${t(section === 'live' ? 'tile_live' : section === 'movie' ? 'tile_movies' : 'tile_series')}`;
  const countEl = h('div', 'topbar-account');
  const bar = new TopBar(title, countEl);

  const list = new VList<Category>('picker', 84, 840, (c) => {
    const on = selected.has(c.id);
    const auto = adultAuto && ADULT_RE.test(c.name);
    return h('div', `cat-row pick-row${on ? ' on' : ''}`,
      h('span', 'pick-box', on || auto ? (mode === 'hide' ? '✕' : '🔒') : ''),
      h('span', 'cat-name', c.name),
      auto && !on ? h('span', 'cat-count', t('adult_auto')) : null);
  });
  list.setActive(true);

  const help = h('div', 'picker-help', t(mode === 'hide' ? 'hide_help' : 'lock_help'));
  const el = h('div', 'screen picker', bar.el, h('div', 'picker-body', list.el, help));

  const updateCount = () => { countEl.textContent = t('selected_n', selected.size); };

  async function load() {
    busy(true);
    try {
      if (section === 'live') {
        await session.loadLive();
        cats = session.categories;
      } else cats = await session.mediaCategories(section as Section);
    } catch (e) {
      toast(t('err_load', (e as Error).message), 5000);
    } finally {
      busy(false);
    }
    list.setItems(cats);
    list.el.classList.toggle('empty', !cats.length);
    list.el.setAttribute('data-empty', t('no_items'));
    updateCount();
  }

  function saveAndBack() {
    const ids = Array.from(selected);
    if (ids.sort().join('|') !== initial) {
      if (mode === 'hide') session.setHidden(section, ids);
      else session.setLockedCats(section, ids);
      toast(t('saved'));
    }
    back();
  }

  return {
    el,
    onShow() {
      bar.start();
      if (!cats.length) load();
    },
    onHide() { bar.stop(); },
    onKey(key: Key): boolean {
      switch (key) {
        case 'up': list.move(-1); return true;
        case 'down': list.move(1); return true;
        case 'rw': case 'chup': list.page(-1); return true;
        case 'ff': case 'chdown': list.page(1); return true;
        case 'ok': {
          const c = list.current;
          if (!c) return true;
          if (selected.has(c.id)) selected.delete(c.id);
          else selected.add(c.id);
          list.refresh();
          updateCount();
          return true;
        }
        case 'yellow': case 'okhold':
          // Tümünü temizle
          selected.clear();
          list.refresh();
          updateCount();
          return true;
        case 'back': saveAndBack(); return true;
      }
      return true;
    },
  };
}
