// Video oynatıcı: TV'de Samsung AVPlay (donanım çözücü), tarayıcıda HTML5 <video>.
// AVPlay görüntüyü web katmanının ALTINDAKİ video düzlemine çizer; bu yüzden
// videonun görüneceği alan sayfada saydam bırakılmalıdır.
/* eslint-disable @typescript-eslint/no-explicit-any */
import { hasAvplay } from './platform';

export interface Rect { x: number; y: number; w: number; h: number }
export const FULL: Rect = { x: 0, y: 0, w: 1920, h: 1080 };

export type PlayerState = 'idle' | 'loading' | 'playing' | 'paused' | 'error' | 'ended';
type Listener = (state: PlayerState) => void;

interface Backend {
  open(url: string, rect: Rect, startAt: number, onState: Listener): void;
  setRect(rect: Rect): void;
  stop(): void;
  pause(): void;
  resume(): void;
  /** saniye */
  time(): number;
  duration(): number;
  seek(sec: number): void;
}

class AvplayBackend implements Backend {
  private av = (window as any).webapis.avplay;
  private el = document.getElementById('avplayer') as HTMLElement;
  private token = 0;

  private place(r: Rect) {
    Object.assign(this.el.style, { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px` });
  }

  open(url: string, rect: Rect, startAt: number, onState: Listener): void {
    const my = ++this.token;
    const alive = () => my === this.token;
    this.close();
    this.place(rect);
    try {
      this.av.open(url);
      this.av.setListener({
        onbufferingstart: () => alive() && onState('loading'),
        onbufferingcomplete: () => alive() && onState('playing'),
        onstreamcompleted: () => alive() && onState('ended'),
        onerror: () => alive() && onState('error'),
      });
      this.av.setDisplayRect(rect.x, rect.y, rect.w, rect.h);
      this.av.setDisplayMethod('PLAYER_DISPLAY_MODE_LETTER_BOX');
      try { this.av.setTimeoutForBuffering(15); } catch { /* eski model */ }
      onState('loading');
      this.av.prepareAsync(
        () => {
          if (!alive()) return;
          try {
            if (startAt > 0) this.av.seekTo(Math.floor(startAt * 1000), () => undefined, () => undefined);
            this.av.play();
            onState('playing');
          } catch {
            onState('error');
          }
        },
        () => alive() && onState('error'),
      );
    } catch {
      onState('error');
    }
  }

  setRect(r: Rect): void {
    this.place(r);
    try { this.av.setDisplayRect(r.x, r.y, r.w, r.h); } catch { /* henüz açılmadı */ }
  }

  private close() {
    try {
      const s = this.av.getState();
      if (s !== 'NONE' && s !== 'IDLE') this.av.stop();
      this.av.close();
    } catch { /* zaten kapalı */ }
  }

  stop(): void {
    this.token++;
    this.close();
  }

  pause(): void {
    try { this.av.pause(); } catch { /* yok */ }
  }

  resume(): void {
    try { this.av.play(); } catch { /* yok */ }
  }

  time(): number {
    try { return (this.av.getCurrentTime() || 0) / 1000; } catch { return 0; }
  }

  duration(): number {
    try { return (this.av.getDuration() || 0) / 1000; } catch { return 0; }
  }

  seek(sec: number): void {
    try { this.av.seekTo(Math.max(0, Math.floor(sec * 1000)), () => undefined, () => undefined); } catch { /* yok */ }
  }
}

class Html5Backend implements Backend {
  private v = document.getElementById('html5player') as HTMLVideoElement;
  private token = 0;

  open(url: string, rect: Rect, startAt: number, onState: Listener): void {
    const my = ++this.token;
    const fire = (s: PlayerState) => () => my === this.token && onState(s);
    this.setRect(rect);
    this.v.onwaiting = fire('loading');
    this.v.onplaying = fire('playing');
    this.v.onpause = () => my === this.token && !this.v.ended && !this.v.error && onState('paused');
    this.v.onended = fire('ended');
    this.v.onerror = fire('error');
    this.v.onloadedmetadata = () => { if (my === this.token && startAt > 0) this.v.currentTime = startAt; };
    this.v.style.display = 'block';
    this.v.src = url;
    onState('loading');
    this.v.play().catch(() => { /* onerror bildirir */ });
  }

  setRect(r: Rect): void {
    Object.assign(this.v.style, { left: `${r.x}px`, top: `${r.y}px`, width: `${r.w}px`, height: `${r.h}px` });
  }

  stop(): void {
    this.token++;
    this.v.pause();
    this.v.removeAttribute('src');
    this.v.load();
    this.v.style.display = 'none';
  }

  pause(): void { this.v.pause(); }
  resume(): void { this.v.play().catch(() => undefined); }
  time(): number { return this.v.currentTime || 0; }
  duration(): number { return isFinite(this.v.duration) ? this.v.duration : 0; }
  seek(sec: number): void { this.v.currentTime = Math.max(0, sec); }
}

class Player {
  private backend: Backend = hasAvplay ? new AvplayBackend() : new Html5Backend();
  private listeners: Listener[] = [];
  state: PlayerState = 'idle';
  url = '';
  rect: Rect = FULL;

  onState(fn: Listener): () => void {
    this.listeners.push(fn);
    return () => { this.listeners = this.listeners.filter((l) => l !== fn); };
  }

  private set(s: PlayerState) {
    this.state = s;
    this.listeners.forEach((l) => l(s));
  }

  play(url: string, rect: Rect = FULL, startAt = 0): void {
    this.url = url;
    this.rect = rect;
    this.backend.open(url, rect, startAt, (s) => this.set(s));
  }

  setRect(rect: Rect): void {
    this.rect = rect;
    this.backend.setRect(rect);
  }

  stop(): void {
    this.url = '';
    this.suspended = null;
    this.backend.stop();
    this.set('idle');
  }

  togglePause(): void {
    if (this.state === 'playing' || this.state === 'loading') {
      this.backend.pause();
      this.set('paused');
    } else if (this.state === 'paused') {
      this.backend.resume();
      this.set('playing');
    }
  }

  time(): number { return this.backend.time(); }
  duration(): number { return this.backend.duration(); }
  seek(sec: number): void { this.backend.seek(sec); }

  /** Uygulama arka plana geçince yayını kapatıp dönünce kaldığı yerden yeniden açar. */
  private suspended: { url: string; rect: Rect; at: number } | null = null;
  suspend(): void {
    if (!this.url) return;
    this.suspended = { url: this.url, rect: this.rect, at: this.time() };
    this.backend.stop();
  }
  restore(): void {
    if (this.suspended) {
      const s = this.suspended;
      this.suspended = null;
      this.play(s.url, s.rect, s.at);
    }
  }
}

export const player = new Player();
