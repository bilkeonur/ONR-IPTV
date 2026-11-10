// TV'nin yerel depolaması. Hesap bilgileri yalnızca cihazda kalır.
import { Episode, Media } from './providers/types';

export interface Profile {
  id: string;
  type: 'xtream' | 'm3u';
  name: string;
  url: string;
  username: string;
  password: string;
}

export interface Settings {
  lang: 'tr' | 'en' | '';
  liveFormat: 'ts' | 'm3u8';
}

/** İzleme kaydı: film ya da dizinin son izlenen bölümü. */
export interface Progress {
  key: string; // movie:<id> | series:<id>
  media: Media;
  episode?: Episode;
  pos: number; // saniye
  dur: number;
  at: number; // Date.now()
}

const P = 'onriptv.';
const MAX_PROGRESS = 60;

function read<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(P + key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function write(key: string, value: unknown): void {
  try {
    localStorage.setItem(P + key, JSON.stringify(value));
  } catch { /* depolama dolu ya da kapalı */ }
}

/** Kayda yalnızca gereken alanlar (bölüm listesi gibi büyük veriler değil). */
function slim(m: Media): Media {
  return {
    kind: m.kind, id: m.id, name: m.name, poster: m.poster, categoryId: m.categoryId,
    rating: m.rating, year: m.year, ext: m.ext, url: m.url, backdrop: m.backdrop,
  };
}

export const store = {
  profile(): Profile | null {
    return read<Profile | null>('profile', null);
  },
  setProfile(p: Profile | null): void {
    write('profile', p);
  },
  settings(): Settings {
    return { lang: '', liveFormat: 'ts', ...read<Partial<Settings>>('settings', {}) };
  },
  saveSettings(s: Settings): void {
    write('settings', s);
  },
  /** Profil başına favori kanal kimlikleri. */
  favorites(pid: string): string[] {
    return read<string[]>(`fav.${pid}`, []);
  },
  setFavorites(pid: string, ids: string[]): void {
    write(`fav.${pid}`, ids);
  },
  lastChannel(pid: string): { cat: string; id: string } | null {
    return read(`last.${pid}`, null);
  },
  setLastChannel(pid: string, v: { cat: string; id: string }): void {
    write(`last.${pid}`, v);
  },

  progressList(pid: string): Progress[] {
    return read<Progress[]>(`progress.${pid}`, []);
  },
  progress(pid: string, key: string): Progress | undefined {
    return this.progressList(pid).find((p) => p.key === key);
  },
  /** Bölüm bazında konum (dizilerde her bölüm ayrı). */
  episodePos(pid: string, epId: string): number {
    return read<Record<string, number>>(`eppos.${pid}`, {})[epId] || 0;
  },
  saveProgress(pid: string, media: Media, episode: Episode | undefined, pos: number, dur: number): void {
    const key = `${media.kind}:${media.id}`;
    let list = this.progressList(pid).filter((p) => p.key !== key);
    const done = dur > 0 && pos / dur > 0.95;
    // Film bittiyse listeden çık; dizide son bölüm kaydı kalsın
    if (!(done && media.kind === 'movie')) {
      list.unshift({ key, media: slim(media), episode, pos: done ? 0 : pos, dur, at: Date.now() });
    }
    list = list.slice(0, MAX_PROGRESS);
    write(`progress.${pid}`, list);
    if (episode) {
      const eps = read<Record<string, number>>(`eppos.${pid}`, {});
      if (done) delete eps[episode.id];
      else eps[episode.id] = pos;
      const keys = Object.keys(eps);
      if (keys.length > 400) keys.slice(0, keys.length - 400).forEach((k) => delete eps[k]);
      write(`eppos.${pid}`, eps);
    }
  },
  removeProgress(pid: string, key: string): void {
    write(`progress.${pid}`, this.progressList(pid).filter((p) => p.key !== key));
  },
};
