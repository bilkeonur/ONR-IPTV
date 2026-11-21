// Video oynatıcı: TV'de Samsung AVPlay (donanım çözücü), tarayıcıda HTML5 <video>.
// AVPlay görüntüyü web katmanının ALTINDAKİ video düzlemine çizer; bu yüzden
// videonun görüneceği alan sayfada saydam bırakılmalıdır.
/* eslint-disable @typescript-eslint/no-explicit-any */
import { hasAvplay } from './platform';

export interface Rect { x: number; y: number; w: number; h: number }
export const FULL: Rect = { x: 0, y: 0, w: 1920, h: 1080 };

export type PlayerState = 'idle' | 'loading' | 'playing' | 'paused' | 'error' | 'ended';
type Listener = (state: PlayerState) => void;

export interface Track {
  type: 'audio' | 'text';
  index: number;
  label: string;
  selected: boolean;
}

/** Görüntü oranı: otomatik (kenar boşluklu) ya da ekrana uzat */
export type Aspect = 'auto' | 'stretch';

type SubListener = (text: string, durationMs: number) => void;

function langLabel(code: string, fallback: string): string {
  const c = (code || '').trim();
  if (!c || c === 'und') return fallback;
  try {
    const DN = (Intl as unknown as { DisplayNames?: new (l: string[], o: object) => { of(c: string): string } }).DisplayNames;
    if (DN) return new DN([document.documentElement.lang || 'en'], { type: 'language' }).of(c) || c;
  } catch { /* desteklenmiyor */ }
  return c.toUpperCase();
}

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
  tracks(): Track[];
  selectTrack(type: 'audio' | 'text', index: number): void;
  setSubtitles(on: boolean): void;
  setAspect(a: Aspect): void;
  onSubtitle: SubListener | null;
}

class AvplayBackend implements Backend {
  private av = (window as any).webapis.avplay;
  private el = document.getElementById('avplayer') as HTMLElement;
  private token = 0;
  private aspect: Aspect = 'auto';
  onSubtitle: SubListener | null = null;

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
        onsubtitlechange: (dur: number, text: string) => { if (alive() && this.onSubtitle) this.onSubtitle(String(text || ''), Number(dur) || 0); },
      });
      this.av.setDisplayRect(rect.x, rect.y, rect.w, rect.h);
      this.applyAspect();
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

  tracks(): Track[] {
    const out: Track[] = [];
    let current: any[] = [];
    try { current = this.av.getCurrentStreamInfo() || []; } catch { /* yok */ }
    const sel = (type: string, index: number) => current.some((c) => c.type === type && Number(c.index) === index);
    let all: any[] = [];
    try { all = this.av.getTotalTrackInfo() || []; } catch { return out; }
    let na = 0;
    let nt = 0;
    for (const tr of all) {
      if (tr.type !== 'AUDIO' && tr.type !== 'TEXT') continue;
      let info: any = {};
      try { info = JSON.parse(tr.extra_info || '{}'); } catch { /* bozuk */ }
      const index = Number(tr.index);
      if (tr.type === 'AUDIO') {
        na++;
        let label = langLabel(info.language, `#${na}`);
        if (info.channels) label += ` · ${info.channels}ch`;
        out.push({ type: 'audio', index, label, selected: sel('AUDIO', index) });
      } else {
        nt++;
        out.push({ type: 'text', index, label: langLabel(info.track_lang || info.language, `#${nt}`), selected: sel('TEXT', index) });
      }
    }
    return out;
  }

  selectTrack(type: 'audio' | 'text', index: number): void {
    try { this.av.setSelectTrack(type === 'audio' ? 'AUDIO' : 'TEXT', index); } catch { /* yok */ }
    if (type === 'text') this.setSubtitles(true);
  }

  setSubtitles(on: boolean): void {
    try { this.av.setSilentSubtitle(!on); } catch { /* yok */ }
    if (!on && this.onSubtitle) this.onSubtitle('', 0);
  }

  private applyAspect(): void {
    try {
      this.av.setDisplayMethod(this.aspect === 'stretch' ? 'PLAYER_DISPLAY_MODE_FULL_SCREEN' : 'PLAYER_DISPLAY_MODE_LETTER_BOX');
    } catch { /* yok */ }
  }

  setAspect(a: Aspect): void {
    this.aspect = a;
    this.applyAspect();
  }
}

class Html5Backend implements Backend {
  private v = document.getElementById('html5player') as HTMLVideoElement;
  private token = 0;
  onSubtitle: SubListener | null = null;

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

  tracks(): Track[] {
    const out: Track[] = [];
    const at = (this.v as any).audioTracks;
    if (at) for (let i = 0; i < at.length; i++) out.push({ type: 'audio', index: i, label: langLabel(at[i].language, at[i].label || `#${i + 1}`), selected: !!at[i].enabled });
    const tt = this.v.textTracks;
    for (let i = 0; i < tt.length; i++) out.push({ type: 'text', index: i, label: langLabel(tt[i].language, tt[i].label || `#${i + 1}`), selected: tt[i].mode === 'showing' });
    return out;
  }

  selectTrack(type: 'audio' | 'text', index: number): void {
    if (type === 'audio') {
      const at = (this.v as any).audioTracks;
      if (at) for (let i = 0; i < at.length; i++) at[i].enabled = i === index;
    } else {
      const tt = this.v.textTracks;
      for (let i = 0; i < tt.length; i++) tt[i].mode = i === index ? 'showing' : 'disabled';
    }
  }

  setSubtitles(on: boolean): void {
    if (on) return;
    const tt = this.v.textTracks;
    for (let i = 0; i < tt.length; i++) tt[i].mode = 'disabled';
  }

  setAspect(a: Aspect): void {
    this.v.style.objectFit = a === 'stretch' ? 'fill' : 'contain';
  }
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
  tracks(): Track[] { return this.backend.tracks(); }
  selectTrack(type: 'audio' | 'text', index: number): void { this.backend.selectTrack(type, index); }
  setSubtitles(on: boolean): void { this.backend.setSubtitles(on); }

  aspect: Aspect = 'auto';
  setAspect(a: Aspect): void {
    this.aspect = a;
    this.backend.setAspect(a);
  }

  /** Altyazı metni (AVPlay altyazıları kendisi çizmez; ekran bunu gösterir). */
  onSubtitle(fn: SubListener | null): void {
    this.backend.onSubtitle = fn;
  }

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
