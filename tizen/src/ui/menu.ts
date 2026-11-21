// Seçenek menüsü: ekranın ortasında bir liste (sıralama, dil, favori, kilit gibi işlemler için).
import { Screen, close, push } from '../app';
import { Key } from '../platform';
import { h } from './dom';

export interface MenuItem {
  label: string;
  /** Sağda soluk yazı (ör. adet) */
  note?: string;
  /** Seçili seçenek işareti */
  checked?: boolean;
  danger?: boolean;
  /** Menü kapandıktan sonra çalışır */
  run?: () => void;
}

const VISIBLE = 9;

export function showMenu(title: string, items: MenuItem[], start?: number, body?: string): void {
  let index = start !== undefined ? start : Math.max(0, items.findIndex((i) => i.checked));
  let topRow = 0;
  const list = h('div', 'menu-list');
  const rows = items.map((it) =>
    h('div', `menu-row${it.danger ? ' danger' : ''}${it.checked ? ' checked' : ''}`,
      h('span', 'menu-check', it.checked ? '●' : ''),
      h('span', 'menu-label', it.label),
      it.note ? h('span', 'menu-note', it.note) : null));
  const more = h('div', 'menu-more', '');
  const box = h('div', 'menu-box', h('div', 'menu-title', title), body ? h('div', 'menu-body', body) : null, list, more);
  const el = h('div', 'modal', box);

  function paint() {
    if (index < topRow) topRow = index;
    if (index >= topRow + VISIBLE) topRow = index - VISIBLE + 1;
    list.innerHTML = '';
    rows.slice(topRow, topRow + VISIBLE).forEach((r, i) => {
      r.classList.toggle('focused', topRow + i === index);
      list.appendChild(r);
    });
    more.textContent = items.length > VISIBLE ? `${index + 1} / ${items.length}` : '';
  }
  paint();

  const screen: Screen = {
    el,
    overlay: true,
    onKey(key: Key): boolean {
      if (key === 'up') index = (index - 1 + items.length) % items.length;
      else if (key === 'down') index = (index + 1) % items.length;
      else if (key === 'back' || key === 'left' || key === 'yellow') { close(screen); return true; }
      else if (key === 'ok') {
        const it = items[index];
        close(screen);
        if (it && it.run) it.run();
        return true;
      }
      paint();
      return true;
    },
  };
  rows.forEach((r, i) => r.addEventListener('click', () => { index = i; screen.onKey('ok'); }));
  push(screen);
}

/** Bilgi penceresi: başlık, açıklama ve tek düğme. */
export function showInfo(title: string, body: string, button: string): void {
  showMenu(title, [{ label: button }], 0, body);
}

/** Kısa onay penceresi: "Evet" seçilirse run çalışır. */
export function confirm(title: string, yes: string, no: string, run: () => void): void {
  showMenu(title, [{ label: yes, danger: true, run }, { label: no }], 1);
}
