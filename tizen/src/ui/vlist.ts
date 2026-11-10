// Sanal liste: yalnızca görünen satırlar DOM'da tutulur, binlerce kanal akıcı kalır.
import { h } from './dom';

export class VList<T> {
  readonly el: HTMLElement;
  private inner: HTMLElement;
  private rows = new Map<number, HTMLElement>();
  private items: T[] = [];
  private top = 0;
  index = 0;
  active = false;

  constructor(
    cls: string,
    private rowH: number,
    private height: number,
    private render: (item: T, i: number) => HTMLElement,
    private onMove?: (item: T, i: number) => void,
  ) {
    this.inner = h('div', 'vlist-inner');
    this.el = h('div', `vlist ${cls}`, this.inner);
    this.el.style.height = `${height}px`;
  }

  get visible(): number {
    return Math.floor(this.height / this.rowH);
  }

  get current(): T | undefined {
    return this.items[this.index];
  }

  get length(): number {
    return this.items.length;
  }

  /** Ekranda görünen öğeler (ör. yalnızca bunların yayın akışını yüklemek için). */
  visibleItems(): T[] {
    return this.items.slice(this.top, this.top + this.visible + 1);
  }

  setItems(items: T[], index = 0): void {
    this.items = items;
    this.rows.forEach((r) => r.remove());
    this.rows.clear();
    this.inner.style.height = `${items.length * this.rowH}px`;
    this.top = 0;
    this.index = -1;
    this.select(Math.max(0, Math.min(index, items.length - 1)), true);
  }

  /** Görünen satırları yeniden çizer (ör. favori işareti değişince). */
  refresh(): void {
    this.rows.forEach((r) => r.remove());
    this.rows.clear();
    this.draw();
  }

  setActive(on: boolean): void {
    this.active = on;
    this.el.classList.toggle('active', on);
  }

  move(delta: number): boolean {
    if (!this.items.length) return false;
    const next = Math.max(0, Math.min(this.items.length - 1, this.index + delta));
    if (next === this.index) return false;
    this.select(next);
    return true;
  }

  page(dir: 1 | -1): void {
    this.move(dir * (this.visible - 1));
  }

  select(i: number, silent = false): void {
    const prev = this.index;
    this.index = i;
    // Odak her zaman görünür alanda, kenardan bir satır içeride
    const vis = this.visible;
    const margin = vis > 4 ? 1 : 0;
    if (i < this.top + margin) this.top = Math.max(0, i - margin);
    else if (i > this.top + vis - 1 - margin) this.top = Math.min(Math.max(0, this.items.length - vis), i - vis + 1 + margin);
    this.inner.style.transform = `translateY(${-this.top * this.rowH}px)`;
    this.draw();
    const p = this.rows.get(prev);
    if (p) p.classList.remove('focused');
    const c = this.rows.get(i);
    if (c) c.classList.add('focused');
    if (!silent && this.onMove && this.items[i] !== undefined) this.onMove(this.items[i], i);
  }

  private draw(): void {
    const from = Math.max(0, this.top - 2);
    const to = Math.min(this.items.length, this.top + this.visible + 2);
    this.rows.forEach((row, i) => {
      if (i < from || i >= to) {
        row.remove();
        this.rows.delete(i);
      }
    });
    for (let i = from; i < to; i++) {
      if (this.rows.has(i)) continue;
      const row = this.render(this.items[i], i);
      row.classList.add('vrow');
      if (i === this.index) row.classList.add('focused');
      row.style.transform = `translateY(${i * this.rowH + 4}px)`;
      row.style.height = `${this.rowH - 8}px`;
      this.inner.appendChild(row);
      this.rows.set(i, row);
    }
  }
}
