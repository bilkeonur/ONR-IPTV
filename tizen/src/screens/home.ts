// Ana ekran: büyük bölüm kutucukları ve "İzlemeye devam et" sırası.
import { Screen, toast } from '../app';
import { currentLang, StrKey, t } from '../i18n';
import { open } from '../nav';
import { Key, exitApp } from '../platform';
import { session } from '../session';
import { Progress, store } from '../store';
import { ICONS, h, icon, poster } from '../ui/dom';
import { TopBar } from '../ui/topbar';

type TileId = 'live' | 'movie' | 'series' | 'settings';

const TILES: { id: TileId; title: StrKey; sub?: StrKey }[] = [
  { id: 'live', title: 'tile_live', sub: 'sub_live' },
  { id: 'movie', title: 'tile_movies', sub: 'sub_movies' },
  { id: 'series', title: 'tile_series', sub: 'sub_series' },
  { id: 'settings', title: 'tile_settings' },
];

export function homeScreen(): Screen {
  let zone: 'tiles' | 'row' = 'tiles';
  let tileIdx = 0;
  let rowIdx = 0;
  let items: Progress[] = [];
  let backArmed = 0;
  // OK basılı tutma: kısa basış açar, uzun basış listeden kaldırır
  let okDown = false;
  let okHeld = false;
  let okTimer = 0;

  const account = h('div', 'topbar-account');
  const bar = new TopBar('', account);

  const tiles = TILES.map((x) =>
    h('div', `tile tile-${x.id}`,
      icon(x.id as keyof typeof ICONS, 'tile-icon'),
      h('div', 'tile-text',
        h('div', 'tile-title', t(x.title)),
        x.sub ? h('div', 'tile-sub', t(x.sub)) : null)));

  const rowTitle = h('div', 'row-title', t('continue_watching'), h('span', 'row-hint', t('hold_to_remove')));
  const rowInner = h('div', 'hrow-inner');
  const row = h('div', 'hrow', rowInner);
  const rowWrap = h('div', 'home-row', rowTitle, row);

  const el = h('div', 'screen home',
    bar.el,
    h('div', 'tiles', tiles),
    rowWrap);

  function card(p: Progress): HTMLElement {
    const pct = p.dur > 0 ? Math.min(100, (p.pos / p.dur) * 100) : 0;
    const sub = p.episode ? `${t('season_n', p.episode.season)} · ${t('episode_n', p.episode.episode)}` : p.media.year;
    return h('div', 'ccard',
      poster(p.media.backdrop || p.media.poster, p.media.name, 'ccard-img'),
      h('div', 'ccard-text', h('div', 'ccard-title', p.media.name), h('div', 'ccard-sub', sub || '')),
      h('div', 'bar', h('div', { class: 'bar-fill', style: `width:${pct}%` })));
  }

  function fillRow() {
    items = store.progressList(session.pid).slice(0, 20);
    rowInner.innerHTML = '';
    items.forEach((p) => rowInner.appendChild(card(p)));
    rowWrap.style.display = items.length ? '' : 'none';
    rowIdx = Math.min(rowIdx, Math.max(0, items.length - 1));
    if (!items.length && zone === 'row') zone = 'tiles';
  }

  function fillAccount() {
    const p = session.profile;
    const a = session.account;
    let text = p ? p.name : '';
    if (a && a.expires && a.expires !== '0' && a.expires !== 'null') {
      const d = new Date(parseInt(a.expires, 10) * 1000).toLocaleDateString(currentLang() === 'tr' ? 'tr-TR' : 'en-GB');
      text += `  ·  ${t('expires_on', d)}`;
    }
    account.textContent = text;
  }

  function paint() {
    tiles.forEach((x, i) => x.classList.toggle('focused', zone === 'tiles' && i === tileIdx));
    const cards = rowInner.children;
    for (let i = 0; i < cards.length; i++) cards[i].classList.toggle('focused', zone === 'row' && i === rowIdx);
    // Seçili kart görünür kalsın
    const shift = Math.max(0, rowIdx - 3) * 400;
    rowInner.style.transform = `translateX(${-shift}px)`;
  }

  function activate(id: TileId) {
    if (id === 'live') open('live');
    else if (id === 'settings') open('settings');
    else open('vod', id);
  }

  function removeCurrent() {
    const p = items[rowIdx];
    if (!p) return;
    store.removeProgress(session.pid, p.key);
    toast(t('removed_from_list'));
    fillRow();
    paint();
  }

  function openProgress(p: Progress) {
    if (p.media.kind === 'movie') open('play', { media: p.media, startAt: p.pos });
    else open('detail', p.media);
  }

  return {
    el,
    onShow() {
      bar.start();
      fillAccount();
      fillRow();
      paint();
    },
    onHide() {
      bar.stop();
      clearTimeout(okTimer);
      okDown = false;
    },
    onKeyUp(key: Key) {
      if (key !== 'ok' || !okDown) return;
      okDown = false;
      clearTimeout(okTimer);
      const cards = rowInner.children;
      for (let i = 0; i < cards.length; i++) cards[i].classList.remove('holding');
      if (!okHeld && zone === 'row' && items[rowIdx]) openProgress(items[rowIdx]);
    },
    onKey(key: Key): boolean {
      if (zone === 'tiles') {
        if (key === 'left' || key === 'right') {
          tileIdx = Math.max(0, Math.min(tiles.length - 1, tileIdx + (key === 'left' ? -1 : 1)));
        } else if (key === 'down' && items.length) {
          zone = 'row';
        } else if (key === 'ok') {
          activate(TILES[tileIdx].id);
          return true;
        }
      } else {
        if (key === 'left' || key === 'right') {
          rowIdx = Math.max(0, Math.min(items.length - 1, rowIdx + (key === 'left' ? -1 : 1)));
        } else if (key === 'up') {
          zone = 'tiles';
        } else if (key === 'ok' && items[rowIdx]) {
          // Tuş basılıyken gelen tekrarları yok say
          if (!okDown) {
            okDown = true;
            okHeld = false;
            const card = rowInner.children[rowIdx] as HTMLElement | undefined;
            if (card) card.classList.add('holding');
            okTimer = window.setTimeout(() => {
              okHeld = true;
              removeCurrent();
            }, 800);
          }
          return true;
        } else if (key === 'red') {
          removeCurrent();
          return true;
        }
      }
      if (key === 'back') {
        if (zone === 'row') zone = 'tiles';
        else if (Date.now() - backArmed < 2500) exitApp();
        else {
          backArmed = Date.now();
          toast(t('press_back_exit'), 2500);
        }
      }
      paint();
      return true;
    },
  };
}
