// Sanal afiş ızgarası: yalnızca görünen satırlar DOM'da tutulur.
import { h } from './dom';

export class VGrid<T> {
  readonly el: HTMLElement;
  private inner: HTMLElement;
  private cells = new Map<number, HTMLElement>();
  private items: T[] = [];
  private topRow = 0;
  index = 0;

  constructor(
    cls: string,
    private cols: number,
    private cellW: number,
    private rowH: number,
    private height: number,
    private render: (item: T, i: number) => HTMLElement,
    private onMove?: (item: T, i: number) => void,
  ) {
    this.inner = h('div', 'vgrid-inner');
    this.el = h('div', `vgrid ${cls}`, this.inner);
    this.el.style.height = `${height}px`;
  }

  get length(): number { return this.items.length; }
  get current(): T | undefined { return this.items[this.index]; }
  get col(): number { return this.index % this.cols; }
  private get visRows(): number { return Math.max(1, Math.floor(this.height / this.rowH)); }

  setItems(items: T[], index = 0): void {
    this.items = items;
    this.cells.forEach((c) => c.remove());
    this.cells.clear();
    this.topRow = 0;
    this.index = -1;
    this.inner.style.height = `${Math.ceil(items.length / this.cols) * this.rowH}px`;
    this.select(Math.max(0, Math.min(index, items.length - 1)), true);
  }

  setActive(on: boolean): void {
    this.el.classList.toggle('active', on);
  }

  /** Kenara gelindiyse false döner (çağıran odağı başka yere taşır). */
  move(dx: number, dy: number): boolean {
    if (!this.items.length) return false;
    let i = this.index;
    if (dx) {
      const c = this.col + dx;
      if (c < 0 || c >= this.cols) return false;
      i += dx;
      if (i >= this.items.length) return false;
    }
    if (dy) {
      i += dy * this.cols;
      if (i < 0) return false;
      if (i >= this.items.length) {
        // Son satır eksikse son öğeye in
        const lastRow = Math.floor((this.items.length - 1) / this.cols);
        if (Math.floor(this.index / this.cols) >= lastRow) return false;
        i = this.items.length - 1;
      }
    }
    this.select(i);
    return true;
  }

  select(i: number, silent = false): void {
    const prev = this.index;
    this.index = i;
    const row = Math.floor(Math.max(0, i) / this.cols);
    if (row < this.topRow) this.topRow = row;
    else if (row > this.topRow + this.visRows - 1) this.topRow = row - this.visRows + 1;
    this.inner.style.transform = `translateY(${-this.topRow * this.rowH}px)`;
    this.draw();
    const p = this.cells.get(prev);
    if (p) p.classList.remove('focused');
    const c = this.cells.get(i);
    if (c) c.classList.add('focused');
    if (!silent && this.onMove && this.items[i] !== undefined) this.onMove(this.items[i], i);
  }

  private draw(): void {
    const from = Math.max(0, (this.topRow - 1) * this.cols);
    const to = Math.min(this.items.length, (this.topRow + this.visRows + 2) * this.cols);
    this.cells.forEach((c, i) => {
      if (i < from || i >= to) {
        c.remove();
        this.cells.delete(i);
      }
    });
    for (let i = from; i < to; i++) {
      if (this.cells.has(i)) continue;
      const c = this.render(this.items[i], i);
      c.classList.add('vcell');
      if (i === this.index) c.classList.add('focused');
      c.style.transform = `translate(${(i % this.cols) * this.cellW}px, ${Math.floor(i / this.cols) * this.rowH}px)`;
      this.inner.appendChild(c);
      this.cells.set(i, c);
    }
  }
}
