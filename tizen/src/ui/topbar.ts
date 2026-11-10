// Ekranların üstündeki ince çubuk: logo, ekran başlığı ve saat.
import { h } from './dom';

export class TopBar {
  readonly el: HTMLElement;
  private clock = h('div', 'clock');
  private timer = 0;

  constructor(title = '', extra?: HTMLElement) {
    this.el = h('div', 'topbar',
      h('div', 'brand', h('span', 'brand-mark', 'ONR'), ' IPTV'),
      title ? h('div', 'topbar-title', title) : null,
      h('div', 'topbar-space'),
      extra || null,
      this.clock);
    this.tick();
  }

  start(): void {
    this.tick();
    clearInterval(this.timer);
    this.timer = window.setInterval(() => this.tick(), 15000);
  }

  stop(): void {
    clearInterval(this.timer);
  }

  private tick(): void {
    const d = new Date();
    this.clock.textContent = `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
  }
}
