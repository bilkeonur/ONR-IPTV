import { HttpError, buildUrl, getJson } from '../http';
import { t } from '../i18n';
import {
  AccountInfo, Category, Channel, Episode, Media, MediaInfo, Program, Provider, ProviderError, Season, Section,
  b64, emptyInfo, normalizeUrl, yearFrom,
} from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Obj = Record<string, any>;

const str = (v: unknown): string => (v === null || v === undefined ? '' : String(v));
const int = (v: unknown): number => {
  const n = parseInt(str(v), 10);
  return isNaN(n) ? 0 : n;
};
const num = (v: unknown): number => {
  const n = parseFloat(str(v));
  return isNaN(n) ? 0 : n;
};
const first = (v: unknown): string => (Array.isArray(v) ? str(v[0]) : str(v));

/** get.php?username=..&password=.. biçimindeki M3U linkinden Xtream bilgilerini çıkarır. */
export function parseXtreamLink(url: string): { server: string; username: string; password: string } | null {
  const m = /^(https?:\/\/[^/?#]+)[^?]*\?(.*)$/i.exec(normalizeUrl(url));
  if (!m) return null;
  const q: Record<string, string> = {};
  for (const part of m[2].split('&')) {
    const [k, v = ''] = part.split('=');
    try { q[decodeURIComponent(k)] = decodeURIComponent(v.replace(/\+/g, ' ')); } catch { /* bozuk */ }
  }
  return q.username && q.password ? { server: m[1], username: q.username, password: q.password } : null;
}

const ACTIONS: Record<Section, [string, string]> = {
  movie: ['get_vod_categories', 'get_vod_streams'],
  series: ['get_series_categories', 'get_series'],
};

function rating(d: Obj): number {
  let r = num(d.rating);
  if (!r && d.rating_5based) r = num(d.rating_5based) * 2;
  return Math.min(10, r);
}

function toList(raw: any): Obj[] {
  if (Array.isArray(raw)) return raw;
  if (raw && typeof raw === 'object') return Object.values(raw);
  return [];
}

export class XtreamProvider implements Provider {
  readonly kind = 'xtream' as const;
  private base: string;

  constructor(url: string, private username: string, private password: string, public liveExt: 'ts' | 'm3u8' = 'ts') {
    this.base = normalizeUrl(url).replace(/\/+$/, '').replace(/\/(player_api|get|panel_api|xmltv)\.php.*$/i, '');
  }

  private async api(params: Record<string, string | number> = {}, timeoutMs = 30000): Promise<any> {
    const url = buildUrl(`${this.base}/player_api.php`, { username: this.username, password: this.password, ...params });
    try {
      return await getJson(url, timeoutMs);
    } catch (e) {
      if (e instanceof HttpError) {
        if (e.status === 401 || e.status === 403) throw new ProviderError(t('err_unauthorized'));
        if (e.status > 0) throw new ProviderError(t('err_http', e.status));
        throw new ProviderError(t('err_connect', e.message));
      }
      throw new ProviderError(t('err_not_xtream'));
    }
  }

  async authenticate(): Promise<AccountInfo> {
    const data = (await this.api({}, 20000)) as Obj | null;
    if (!data || typeof data !== 'object' || !data.user_info) throw new ProviderError(t('err_not_xtream'));
    const ui = data.user_info as Obj;
    if (str(ui.auth) === '0') throw new ProviderError(t('err_unauthorized'));
    return {
      status: str(ui.status),
      expires: str(ui.exp_date),
      maxConnections: str(ui.max_connections),
      activeConnections: str(ui.active_cons),
    };
  }

  private async categories(action: string): Promise<Category[]> {
    const data = await this.api({ action });
    if (!Array.isArray(data)) return [];
    return data.map((c: Obj) => ({ id: str(c.category_id), name: str(c.category_name) || '?' }));
  }

  liveCategories(): Promise<Category[]> {
    return this.categories('get_live_categories');
  }

  async liveChannels(): Promise<Channel[]> {
    const list = toList(await this.api({ action: 'get_live_streams' }, 180000));
    return list.map((d) => ({
      id: str(d.stream_id),
      num: int(d.num),
      name: str(d.name).trim() || '?',
      logo: str(d.stream_icon),
      categoryId: str(d.category_id) || first(d.category_ids),
      epgId: str(d.epg_channel_id),
    }));
  }

  streamUrl(ch: Channel): string {
    return `${this.base}/live/${this.username}/${this.password}/${ch.id}.${this.liveExt}`;
  }

  async shortEpg(ch: Channel): Promise<Program[]> {
    let data: Obj | null;
    try {
      data = await this.api({ action: 'get_short_epg', stream_id: ch.id, limit: 4 }, 10000);
    } catch {
      return [];
    }
    const listings = data && Array.isArray(data.epg_listings) ? (data.epg_listings as Obj[]) : [];
    return listings
      .map((p) => ({
        title: b64(str(p.title)),
        desc: b64(str(p.description)),
        start: int(p.start_timestamp),
        end: int(p.stop_timestamp),
      }))
      .filter((p) => p.start > 0)
      .sort((a, b) => a.start - b.start);
  }

  mediaCategories(section: Section): Promise<Category[]> {
    return this.categories(ACTIONS[section][0]);
  }

  async mediaItems(section: Section, categoryId: string): Promise<Media[]> {
    const params: Record<string, string> = { action: ACTIONS[section][1] };
    if (categoryId) params.category_id = categoryId;
    const list = toList(await this.api(params, 180000));
    if (section === 'movie') {
      return list.map((d) => {
        const name = str(d.name || d.title).trim() || '?';
        return {
          kind: 'movie' as const,
          id: str(d.stream_id),
          name,
          poster: str(d.stream_icon),
          categoryId: str(d.category_id) || first(d.category_ids),
          rating: rating(d),
          year: str(d.year) || yearFrom(name),
          ext: str(d.container_extension) || 'mp4',
          added: int(d.added),
        };
      });
    }
    return list.map((d) => ({
      kind: 'series' as const,
      id: str(d.series_id),
      name: str(d.name).trim() || '?',
      poster: str(d.cover),
      categoryId: str(d.category_id) || first(d.category_ids),
      rating: rating(d),
      year: yearFrom(str(d.releaseDate || d.release_date || d.year)),
      added: int(d.last_modified),
      plot: str(d.plot),
      backdrop: first(d.backdrop_path),
    }));
  }

  async mediaInfo(m: Media): Promise<MediaInfo | null> {
    if (m.kind === 'series') return (await this.seasons(m)).info;
    let data: Obj | null;
    try {
      data = await this.api({ action: 'get_vod_info', vod_id: m.id });
    } catch {
      return null;
    }
    const i = data && (data.info as Obj);
    if (!i || typeof i !== 'object') return null;
    return {
      plot: str(i.plot || i.description),
      cast: str(i.cast || i.actors),
      director: str(i.director),
      genre: str(i.genre),
      release: str(i.releasedate || i.release_date),
      duration: str(i.duration),
      rating: str(i.rating),
      backdrop: first(i.backdrop_path),
      poster: str(i.movie_image || i.cover_big),
    };
  }

  async seasons(m: Media): Promise<{ info: MediaInfo | null; seasons: Season[] }> {
    const data = (await this.api({ action: 'get_series_info', series_id: m.id })) as Obj | null;
    if (!data || typeof data !== 'object') return { info: null, seasons: [] };
    const i = (data.info || {}) as Obj;
    const info: MediaInfo = {
      ...emptyInfo(),
      plot: str(i.plot),
      cast: str(i.cast),
      director: str(i.director),
      genre: str(i.genre),
      release: str(i.releaseDate || i.release_date),
      rating: str(i.rating),
      backdrop: first(i.backdrop_path),
      poster: str(i.cover),
    };
    // Bölümler sezon -> liste sözlüğü; bazı paneller düz liste döndürür
    const grouped: Record<string, Obj[]> = {};
    const eps = data.episodes;
    if (Array.isArray(eps)) {
      for (const e of eps) {
        for (const x of Array.isArray(e) ? e : [e]) {
          const s = str(x.season) || '1';
          (grouped[s] = grouped[s] || []).push(x);
        }
      }
    } else if (eps && typeof eps === 'object') {
      for (const k of Object.keys(eps)) grouped[k] = toList(eps[k]);
    }
    const seasons: Season[] = Object.keys(grouped).map((k) => {
      const season = int(k) || 1;
      const episodes: Episode[] = grouped[k].map((e) => {
        const ei = (e.info || {}) as Obj;
        return {
          id: str(e.id),
          title: str(e.title) || t('episode_n', str(e.episode_num)),
          season,
          episode: int(e.episode_num),
          ext: str(e.container_extension) || 'mp4',
          plot: str(ei.plot),
          duration: str(ei.duration),
          image: str(ei.movie_image),
        };
      }).sort((a, b) => a.episode - b.episode);
      return { num: season, episodes };
    }).sort((a, b) => a.num - b.num);
    return { info, seasons };
  }

  movieUrl(m: Media): string {
    return `${this.base}/movie/${this.username}/${this.password}/${m.id}.${m.ext || 'mp4'}`;
  }

  episodeUrl(e: Episode): string {
    return `${this.base}/series/${this.username}/${this.password}/${e.id}.${e.ext || 'mp4'}`;
  }
}
