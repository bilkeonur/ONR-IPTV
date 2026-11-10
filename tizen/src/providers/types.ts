export interface Category {
  id: string;
  name: string;
}

export interface Channel {
  id: string;
  num: number;
  name: string;
  logo: string;
  categoryId: string;
  /** M3U kaynaklarında doğrudan yayın adresi */
  url?: string;
  epgId?: string;
}

/** Film ya da dizi. */
export interface Media {
  kind: 'movie' | 'series';
  id: string;
  name: string;
  poster: string;
  categoryId: string;
  rating: number; // 0-10
  year: string;
  ext?: string;
  url?: string;
  added?: number;
  plot?: string;
  backdrop?: string;
  /** M3U dizilerinde bölümler önceden bilinir */
  episodes?: Episode[];
}

export interface Episode {
  id: string;
  title: string;
  season: number;
  episode: number;
  ext: string;
  url?: string;
  plot?: string;
  duration?: string;
  image?: string;
}

export interface MediaInfo {
  plot: string;
  cast: string;
  director: string;
  genre: string;
  release: string;
  duration: string;
  rating: string;
  backdrop: string;
  poster: string;
}

export interface Season {
  num: number;
  episodes: Episode[];
}

export interface Program {
  title: string;
  desc: string;
  start: number; // epoch saniye
  end: number;
}

export interface AccountInfo {
  status: string;
  expires: string; // epoch saniye ya da boş (sınırsız)
  maxConnections: string;
  activeConnections: string;
}

export type Section = 'movie' | 'series';

export interface Provider {
  readonly kind: 'xtream' | 'm3u';
  authenticate(): Promise<AccountInfo | null>;
  liveCategories(): Promise<Category[]>;
  liveChannels(): Promise<Channel[]>;
  streamUrl(ch: Channel): string;
  shortEpg(ch: Channel): Promise<Program[]>;

  mediaCategories(section: Section): Promise<Category[]>;
  /** categoryId boşsa tüm içerik */
  mediaItems(section: Section, categoryId: string): Promise<Media[]>;
  mediaInfo(m: Media): Promise<MediaInfo | null>;
  seasons(m: Media): Promise<{ info: MediaInfo | null; seasons: Season[] }>;
  movieUrl(m: Media): string;
  episodeUrl(e: Episode): string;
}

export class ProviderError extends Error {}

export function normalizeUrl(url: string): string {
  const u = url.trim();
  if (!u) return u;
  return /^[a-z][a-z0-9+.-]*:\/\//i.test(u) ? u : `http://${u}`;
}

/** UTF-8 metinleri bozmadan base64 çözer (Xtream EPG başlıkları). */
export function b64(s: string): string {
  if (!s) return '';
  try {
    const bin = atob(s);
    const bytes = new Uint8Array(bin.length);
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
    return new TextDecoder('utf-8').decode(bytes);
  } catch {
    return s;
  }
}

export function yearFrom(s: string): string {
  const m = /(19|20)\d{2}/.exec(s || '');
  return m ? m[0] : '';
}

export const emptyInfo = (): MediaInfo => ({
  plot: '', cast: '', director: '', genre: '', release: '', duration: '', rating: '', backdrop: '', poster: '',
});
