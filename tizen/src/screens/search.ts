// Genel arama: kanallar, filmler ve diziler tek ekranda (Türkçe karakter duyarsız).
import { Screen, isEditing } from '../app';
import { StrKey, t } from '../i18n';
import { search } from '../lib';
import { back, open } from '../nav';
import { Key } from '../platform';
import { AnySection, Channel, Media, Section } from '../providers/types';
import { session } from '../session';
import { h, logo } from '../ui/dom';
import { askPin } from '../ui/pin';
import { TopBar } from '../ui/topbar';
import { posterCard } from './vod';

interface Row {
  section: AnySection;
  title: StrKey;
  items: (Channel | Media)[];
  source: (Channel | Media)[] | null;
  state: 'idle' | 'loading' | 'ready' | 'error';
  el: HTMLElement;
  inner: HTMLElement;
  head: HTMLElement;
  index: number;
}

const LIMIT = 40;
const CH_W = 300;
const POSTER_W = 236;

export function searchScreen(arg: { scope?: AnySection; onChannel?: (ch: Channel) => void } | void): Screen {
  const scope = arg && arg.scope;
  const onChannel = arg && arg.onChannel;
  const sections: AnySection[] = scope ? [scope] : ['live', 'movie', 'series'];
  const titles: Record<AnySection, StrKey> = { live: 'tile_live', movie: 'tile_movies', series: 'tile_series' };
  let zone = -1; // -1: arama kutusu, 0..: sonuç satırı
  let query = '';
  let timer = 0;
  let firstShow = true;

  const bar = new TopBar(scope ? `${t('search')} · ${t(titles[scope])}` : t('search'));
  const input = h('input', { type: 'text', placeholder: t('search_hint'), autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false' });
  const field = h('label', 'field search-field', h('span', 'field-label', t('search')), input);
  const status = h('div', 'search-status', t('search_intro'));
  const rowsBox = h('div', 'search-rows');
  const el = h('div', 'screen search', bar.el, h('div', 'search-head', field), status, h('div', 'search-clip', rowsBox));

  const rows: Row[] = sections.map((section) => {
    const head = h('div', 'row-title', '');
    const inner = h('div', 'hrow-inner');
    const box = h('div', `hrow ${section === 'live' ? 'chrow' : 'prow'}`, inner);
    return { section, title: titles[section], items: [], source: null, state: 'idle', el: h('div', 'search-row', head, box), inner, head, index: 0 };
  });
  rows.forEach((r) => rowsBox.appendChild(r.el));

  const visibleRows = () => rows.filter((r) => r.items.length);

  async function loadSource(r: Row) {
    if (r.state !== 'idle') return;
    r.state = 'loading';
    paintRows();
    try {
      if (r.section === 'live') {
        await session.loadLive();
        // Gizli ve yetişkin kategoriler aramada hiç çıkmaz
        const excl = session.excludedCats('live', session.categories);
        session.adultCats(session.categories).forEach((id) => excl.add(id));
        r.source = session.channels.filter((c) => !excl.has(c.categoryId) && !session.isAdult('live', c));
      } else {
        const sec = r.section as Section;
        const all = await session.searchable(sec);
        const cats = await session.mediaCategories(sec);
        const excl = session.excludedCats(sec, cats);
        session.adultCats(cats).forEach((id) => excl.add(id));
        r.source = all.filter((m) => !excl.has(m.categoryId) && !session.isAdult(sec, m));
      }
      r.state = 'ready';
    } catch {
      r.state = 'error';
    }
    run();
  }

  function card(r: Row, it: Channel | Media): HTMLElement {
    if (r.section === 'live') {
      const ch = it as Channel;
      return h('div', 'scard', logo(ch.logo, ch.name, 'logo big'),
        h('div', 'scard-title', ch.name), h('div', 'scard-sub', String(ch.num || '')));
    }
    return posterCard(it as Media);
  }

  function run() {
    const q = query.trim();
    rows.forEach((r) => {
      r.items = q.length >= 2 && r.source ? search(r.source, q, LIMIT) : [];
      r.index = 0;
      r.inner.innerHTML = '';
      r.items.forEach((it) => r.inner.appendChild(card(r, it)));
    });
    paintRows();
    if (zone >= visibleRows().length) zone = visibleRows().length - 1;
    paint();
  }

  function paintRows() {
    const q = query.trim();
    let total = 0;
    let loadingAny = false;
    rows.forEach((r) => {
      total += r.items.length;
      if (r.state === 'loading') loadingAny = true;
      r.el.style.display = r.items.length ? '' : 'none';
      let note = '';
      if (r.section !== 'live' && session.isPaged(r.section as Section)) note = t('search_paged_note');
      r.head.textContent = '';
      r.head.appendChild(document.createTextNode(`${t(r.title)}  `));
      r.head.appendChild(h('span', 'row-hint', `${r.items.length}${note ? `  ·  ${note}` : ''}`));
    });
    if (q.length < 2) status.textContent = t('search_intro');
    else if (!total) status.textContent = loadingAny ? t('loading') : t('search_none', q);
    else status.textContent = loadingAny ? t('loading') : '';
    status.style.display = status.textContent ? '' : 'none';
  }

  function paint() {
    field.classList.toggle('focused', zone === -1);
    const vis = visibleRows();
    rows.forEach((r) => {
      const active = vis.indexOf(r) === zone;
      const cards = r.inner.children;
      for (let i = 0; i < cards.length; i++) cards[i].classList.toggle('focused', active && i === r.index);
      const w = r.section === 'live' ? CH_W + 20 : POSTER_W;
      r.inner.style.transform = `translateX(${-Math.max(0, r.index - 3) * w}px)`;
      r.el.classList.toggle('active', active);
    });
    // Odaklı satır görünür kalsın
    const focusedRow = vis[zone];
    rowsBox.style.transform = focusedRow && zone > 0 ? `translateY(${-focusedRow.el.offsetTop}px)` : '';
  }

  function schedule() {
    clearTimeout(timer);
    timer = window.setTimeout(() => {
      query = input.value;
      run();
    }, 350);
  }

  async function pick(r: Row) {
    const it = r.items[r.index];
    if (!it) return;
    if (r.section === 'live') {
      const ch = it as Channel;
      if (onChannel) {
        back();
        onChannel(ch);
      } else open('live', { channelId: ch.id });
      return;
    }
    const m = it as Media;
    if (session.isItemLocked(r.section, m) && !(await askPin())) return;
    open('detail', m);
  }

  input.addEventListener('input', schedule);
  input.addEventListener('focus', () => { zone = -1; paint(); });

  function startEdit() {
    input.focus();
    const v = input.value;
    input.setSelectionRange(v.length, v.length);
  }

  return {
    el,
    onShow() {
      bar.start();
      if (firstShow) {
        firstShow = false;
        rows.forEach((r) => loadSource(r));
        paintRows();
        paint();
        // Ekran klavyesi hemen açılsın
        setTimeout(startEdit, 50);
      } else {
        // Ayrıntıdan dönüş: işaretleri tazele
        run();
      }
    },
    onHide() {
      bar.stop();
      if (isEditing()) input.blur();
    },
    onKey(key: Key): boolean {
      const vis = visibleRows();
      if (isEditing()) {
        if (key === 'ok' || key === 'done' || key === 'down' || key === 'cancel') {
          input.blur();
          clearTimeout(timer);
          query = input.value;
          run();
          if (key !== 'cancel' && visibleRows().length) zone = 0;
          paint();
          return true;
        }
        if (key === 'back') { input.blur(); return true; }
        return false;
      }
      if (zone === -1) {
        if (key === 'ok') { startEdit(); return true; }
        if (key === 'down' && vis.length) zone = 0;
        else if (key === 'back') { back(); return true; }
        paint();
        return true;
      }
      const r = vis[zone];
      if (!r) { zone = -1; paint(); return true; }
      switch (key) {
        case 'left': r.index = Math.max(0, r.index - 1); break;
        case 'right': r.index = Math.min(r.items.length - 1, r.index + 1); break;
        case 'up': zone--; break;
        case 'down': if (zone < vis.length - 1) zone++; break;
        case 'ok': pick(r); return true;
        case 'back': zone = -1; break;
        case 'blue': zone = -1; paint(); startEdit(); return true;
      }
      paint();
      return true;
    },
  };
}
