// TV'nin yerel depolaması. Hesap bilgileri yalnızca cihazda kalır.
import { AnySection, Channel, Episode, Media } from './providers/types';

export type ProfileType = 'xtream' | 'm3u' | 'stalker';

export interface Profile {
  id: string;
  type: ProfileType;
  name: string;
  url: string;
  username: string;
  password: string;
  /** M3U: isteğe bağlı XMLTV rehber adresi */
  epgUrl?: string;
  /** Stalker: MAC adresi */
  mac?: string;
}

export type SortMode = 'default' | 'num' | 'az' | 'za' | 'new' | 'rating' | 'year';

export interface Settings {
  lang: 'tr' | 'en' | '';
  liveFormat: 'ts' | 'm3u8';
  autoReconnect: boolean;
  showEpgInList: boolean;
  /** Ebeveyn kilidi PIN'i ('' = kapalı) */
  pin: string;
  lockAdult: boolean;
  sort: Record<AnySection, SortMode>;
  /** İçerik dili filtresi (ör. 'TR'); '' = tümü */
  langFilter: Record<AnySection, string>;
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

/** "Son izlenen" listesindeki kayıt. */
export interface HistoryEntry {
  kind: AnySection;
  id: string;
  ch?: Channel;
  media?: Media;
  at: number;
}

/** Profil başına favoriler, son izlenenler ve izlendi işaretleri. */
export interface UserData {
  fav: Record<AnySection, string[]>;
  /** Favorinin kısa kaydı: liste yüklenmeden (ya da başka kategorideyken) de gösterilebilsin */
  favMeta: { live: Record<string, Channel>; movie: Record<string, Media>; series: Record<string, Media> };
  history: HistoryEntry[];
  /** izleme anahtarı (movie:<id> | ep:<id>) -> bitirildiği zaman */
  watched: Record<string, number>;
}

/** Profil başına kategori gizleme ve kilitleme. */
export interface ProfileSettings {
  hidden: Record<AnySection, string[]>;
  locks: Record<AnySection, { cats: string[]; items: string[] }>;
}

const P = 'onriptv.';
const MAX_PROGRESS = 60;
const MAX_HISTORY = 60;
const SECTIONS: AnySection[] = ['live', 'movie', 'series'];

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

function remove(key: string): void {
  try { localStorage.removeItem(P + key); } catch { /* yok */ }
}

const per = <T>(f: () => T): Record<AnySection, T> => ({ live: f(), movie: f(), series: f() });

/** Kayda yalnızca gereken alanlar (bölüm listesi gibi büyük veriler değil). */
export function slim(m: Media): Media {
  return {
    kind: m.kind, id: m.id, name: m.name, poster: m.poster, categoryId: m.categoryId,
    rating: m.rating, year: m.year, ext: m.ext, url: m.url, backdrop: m.backdrop, cmd: m.cmd,
  };
}

export function slimChannel(c: Channel): Channel {
  return {
    id: c.id, num: c.num, name: c.name, logo: c.logo, categoryId: c.categoryId,
    url: c.url, epgId: c.epgId, archive: c.archive, cmd: c.cmd,
  };
}

const DEFAULT_SETTINGS: Settings = {
  lang: '',
  liveFormat: 'ts',
  autoReconnect: true,
  showEpgInList: true,
  pin: '',
  lockAdult: false,
  sort: { live: 'default', movie: 'default', series: 'default' },
  langFilter: { live: '', movie: '', series: '' },
};

export const store = {
  // ---- Profiller
  profiles(): Profile[] {
    const list = read<Profile[] | null>('profiles', null);
    if (list) return list;
    // Eski sürüm: tek profil
    const old = read<Profile | null>('profile', null);
    if (old) {
      write('profiles', [old]);
      write('active', old.id);
      remove('profile');
      return [old];
    }
    return [];
  },
  profile(): Profile | null {
    const list = this.profiles();
    const id = read<string>('active', '');
    return list.find((p) => p.id === id) || list[0] || null;
  },
  setActive(id: string): void {
    write('active', id);
  },
  upsertProfile(p: Profile): void {
    const list = this.profiles();
    const i = list.findIndex((x) => x.id === p.id);
    if (i >= 0) list[i] = p;
    else list.push(p);
    write('profiles', list);
  },
  removeProfile(id: string): void {
    write('profiles', this.profiles().filter((p) => p.id !== id));
    if (read<string>('active', '') === id) remove('active');
    ['user', 'pset', 'last', 'progress', 'eppos', 'fav'].forEach((k) => remove(`${k}.${id}`));
  },

  // ---- Ayarlar
  settings(): Settings {
    const s = read<Partial<Settings>>('settings', {});
    return {
      ...DEFAULT_SETTINGS,
      ...s,
      sort: { ...DEFAULT_SETTINGS.sort, ...(s.sort || {}) },
      langFilter: { ...DEFAULT_SETTINGS.langFilter, ...(s.langFilter || {}) },
    };
  },
  saveSettings(s: Settings): void {
    write('settings', s);
  },

  // ---- Profil başına kullanıcı verisi
  user(pid: string): UserData {
    const u = read<Partial<UserData>>(`user.${pid}`, {});
    const data: UserData = {
      fav: { ...per<string[]>(() => []), ...(u.fav || {}) },
      favMeta: { live: {}, movie: {}, series: {}, ...(u.favMeta || {}) },
      history: u.history || [],
      watched: u.watched || {},
    };
    // Eski sürüm: yalnızca canlı kanal favorileri
    const oldFav = read<string[] | null>(`fav.${pid}`, null);
    if (oldFav) {
      data.fav.live = Array.from(new Set(data.fav.live.concat(oldFav)));
      remove(`fav.${pid}`);
      this.saveUser(pid, data);
    }
    return data;
  },
  saveUser(pid: string, u: UserData): void {
    u.history = u.history.slice(0, MAX_HISTORY);
    const keys = Object.keys(u.watched);
    if (keys.length > 1500) {
      keys.sort((a, b) => u.watched[a] - u.watched[b]).slice(0, keys.length - 1500).forEach((k) => delete u.watched[k]);
    }
    write(`user.${pid}`, u);
  },

  profileSettings(pid: string): ProfileSettings {
    const s = read<Partial<ProfileSettings>>(`pset.${pid}`, {});
    return {
      hidden: { ...per<string[]>(() => []), ...(s.hidden || {}) },
      locks: { ...per(() => ({ cats: [] as string[], items: [] as string[] })), ...(s.locks || {}) },
    };
  },
  saveProfileSettings(pid: string, s: ProfileSettings): void {
    write(`pset.${pid}`, s);
  },


  // ---- İzleme konumları
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
  /** true dönerse içerik sonuna kadar izlendi (izlendi işareti konmalı). */
  saveProgress(pid: string, media: Media, episode: Episode | undefined, pos: number, dur: number): boolean {
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
    return done;
  },
  removeProgress(pid: string, key: string): void {
    write(`progress.${pid}`, this.progressList(pid).filter((p) => p.key !== key));
  },
};

export { SECTIONS };
