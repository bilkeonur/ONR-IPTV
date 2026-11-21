// Stalker / Ministra (MAG) portal sağlayıcısı.
// Not: portallar MAC adresini "mac" çerezinden okur. TV'nin web motoru Cookie başlığını
// engellerse el sıkışma başarısız olur; bu durumda hata mesajı gösterilir.
import { Headers, HttpError, buildUrl, getText } from '../http';
import { t } from '../i18n';
import {
  AccountInfo, Category, Channel, Episode, Media, MediaInfo, Page, Program, Provider, ProviderError, Season, Section,
  emptyInfo, normalizeUrl, yearFrom,
} from './types';

/* eslint-disable @typescript-eslint/no-explicit-any */
type Obj = Record<string, any>;

const MAG_UA = 'Mozilla/5.0 (QtEmbedded; U; Linux; C) AppleWebKit/533.3 (KHTML, like Gecko) MAG200 stbapp ver: 2 rev: 250 Safari/533.3';
const TYPES: Record<Section, string> = { movie: 'vod', series: 'series' };

const str = (v: unknown): string => (v === null || v === undefined ? '' : String(v));
const int = (v: unknown, d = 0): number => {
  const n = parseInt(str(v), 10);
  return isNaN(n) ? d : n;
};

export function randomMac(): string {
  const b = () => Math.floor(Math.random() * 256).toString(16).toUpperCase().padStart(2, '0');
  return `00:1A:79:${b()}:${b()}:${b()}`;
}

export const MAC_RE = /^([0-9A-F]{2}:){5}[0-9A-F]{2}$/;

function stripCmd(cmd: string): string {
  const c = (cmd || '').trim();
  for (const p of ['ffmpeg ', 'ffrt ', 'ffrt2 ', 'ffrt3 ', 'auto ']) if (c.indexOf(p) === 0) return c.slice(p.length).trim();
  return c;
}

function ts(s: unknown): number {
  const m = /(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2}):(\d{2})/.exec(str(s));
  return m ? Math.floor(new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]).getTime() / 1000) : 0;
}

/** Basit, tekrarlanabilir onaltılık özet (seri numarası / cihaz kimliği için). */
function hexHash(s: string, len: number): string {
  let out = '';
  let h = 0x811c9dc5;
  while (out.length < len) {
    for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619) >>> 0;
    h = Math.imul(h ^ out.length, 16777619) >>> 0;
    out += h.toString(16).toUpperCase().padStart(8, '0');
  }
  return out.slice(0, len);
}

export class StalkerProvider implements Provider {
  readonly kind = 'stalker' as const;
  readonly paged: Section[] = ['movie', 'series'];
  private portal: string;
  private root: string;
  private mac: string;
  private endpoint = '';
  private token = '';
  private sn: string;
  private deviceId: string;
  private handshaking: Promise<void> | null = null;

  constructor(url: string, mac: string) {
    this.portal = normalizeUrl(url).replace(/\/+$/, '');
    this.mac = (mac || '').toUpperCase().trim();
    const m = /^(https?:\/\/[^/?#]+)/i.exec(this.portal);
    this.root = m ? m[1] : this.portal;
    this.sn = hexHash(this.mac, 13);
    this.deviceId = hexHash(`${this.mac}#id`, 64);
  }

  private headers(): Headers {
    const h: Headers = {
      'User-Agent': MAG_UA,
      'X-User-Agent': 'Model: MAG250; Link: WiFi',
      Referer: `${(this.endpoint || this.root).replace(/\/[^/]*$/, '')}/c/`,
      Cookie: `mac=${encodeURIComponent(this.mac)}; stb_lang=en; timezone=Europe/Istanbul`,
      Accept: '*/*',
    };
    if (this.token) h.Authorization = `Bearer ${this.token}`;
    return h;
  }

  private candidates(): string[] {
    const path = this.portal.slice(this.root.length);
    const c: string[] = [];
    if (/\.php$/i.test(path)) c.push(this.portal);
    if (path.indexOf('stalker_portal') >= 0) c.push(`${this.root}/stalker_portal/server/load.php`);
    c.push(`${this.root}/portal.php`, `${this.root}/server/load.php`, `${this.root}/stalker_portal/server/load.php`, `${this.root}/c/portal.php`);
    return c.filter((x, i) => c.indexOf(x) === i);
  }

  private async raw(params: Record<string, string | number>, timeoutMs = 20000): Promise<{ js: any; text: string }> {
    const url = buildUrl(this.endpoint, { ...params, JsHttpRequest: '1-xml' });
    let text: string;
    try {
      text = (await getText(url, timeoutMs, this.headers())).trim();
    } catch (e) {
      const err = e as HttpError;
      if (err.status > 0) throw new ProviderError(t('err_http', err.status));
      throw new ProviderError(t('err_connect', err.message));
    }
    let js: any;
    try { js = text ? (JSON.parse(text) as Obj).js : undefined; } catch { js = undefined; }
    return { js, text };
  }

  private async req(params: Record<string, string | number>, timeoutMs = 20000, retry = true): Promise<any> {
    if (!this.endpoint) await this.authenticate();
    let r: { js: any; text: string };
    try {
      r = await this.raw(params, timeoutMs);
    } catch (e) {
      if (!retry) throw e;
      await this.handshake();
      return this.req(params, timeoutMs, false);
    }
    if ((r.js === undefined || r.js === null || r.text.indexOf('Authorization failed') >= 0) && retry) {
      await this.handshake();
      return this.req(params, timeoutMs, false);
    }
    return r.js;
  }

  private handshake(): Promise<void> {
    if (!this.handshaking) {
      this.handshaking = this.doHandshake().then(
        () => { this.handshaking = null; },
        (e) => { this.handshaking = null; throw e; });
    }
    return this.handshaking;
  }

  private async doHandshake(): Promise<void> {
    this.token = '';
    let js: Obj | null = null;
    for (let i = 0; i < 2 && !(js && js.token); i++) {
      try { js = (await this.raw({ type: 'stb', action: 'handshake', token: '' }, 15000)).js; } catch { js = null; }
    }
    if (!js || !js.token) throw new ProviderError(t('err_stalker_handshake'));
    this.token = str(js.token);
    try {
      const p = (await this.raw({
        type: 'stb', action: 'get_profile', hd: 1, ver: 'ImageDescription: 0.2.18-r23-250; PORTAL version: 5.6.2; API Version: JS API version: 343',
        num_banks: 2, sn: this.sn, stb_type: 'MAG250', client_type: 'STB', image_version: 218, video_out: 'hdmi',
        device_id: this.deviceId, device_id2: this.deviceId, signature: '', auth_second_step: 1, hw_version: '1.7-BD-00',
        not_valid_token: 0, timestamp: Math.floor(Date.now() / 1000), api_signature: 262, prehash: '',
      }, 15000)).js as Obj | null;
      if (p && p.status && str(p.status) !== '0' && p.block_msg) {
        throw new ProviderError(t('err_portal_msg', str(p.block_msg)));
      }
    } catch (e) {
      if (e instanceof ProviderError) throw e;
    }
  }

  async authenticate(): Promise<AccountInfo> {
    if (!MAC_RE.test(this.mac)) throw new ProviderError(t('err_mac'));
    let last: Error | null = null;
    let ok = false;
    for (const ep of this.candidates()) {
      this.endpoint = ep;
      try {
        await this.handshake();
        ok = true;
        break;
      } catch (e) {
        last = e as Error;
      }
    }
    if (!ok) {
      this.endpoint = '';
      throw last || new ProviderError(t('err_stalker_handshake'));
    }
    const info: AccountInfo = { status: 'Active', expires: '', maxConnections: '', activeConnections: '' };
    try {
      const js = await this.req({ type: 'account_info', action: 'get_main_info' }, 15000, false);
      if (js && typeof js === 'object') info.expires = str(js.end_date || js.phone);
    } catch { /* isteğe bağlı */ }
    return info;
  }

  private logo(u: string): string {
    if (!u) return '';
    if (/^https?:/i.test(u)) return u;
    if (u[0] === '/') return this.root + u;
    return `${this.root}/stalker_portal/misc/logos/320/${u}`;
  }

  // ---- Canlı TV
  async liveCategories(): Promise<Category[]> {
    const js = await this.req({ type: 'itv', action: 'get_genres' });
    return (Array.isArray(js) ? js : [])
      .filter((c: Obj) => c && str(c.id) !== '*')
      .map((c: Obj) => ({ id: str(c.id), name: str(c.title || c.name) || '?' }));
  }

  async liveChannels(): Promise<Channel[]> {
    const js = await this.req({ type: 'itv', action: 'get_all_channels' }, 90000);
    const data: Obj[] = js && Array.isArray(js.data) ? js.data : [];
    return data.map((d) => ({
      id: str(d.id),
      num: int(d.number),
      name: str(d.name) || '?',
      logo: this.logo(str(d.logo)),
      categoryId: str(d.tv_genre_id),
      epgId: str(d.xmltv_id),
      archive: int(d.tv_archive) > 0,
      cmd: str(d.cmd),
    }));
  }

  async streamUrl(ch: Channel): Promise<string> {
    const direct = stripCmd(ch.cmd || '');
    try {
      const js = await this.req({ type: 'itv', action: 'create_link', cmd: ch.cmd || '', series: '', forced_storage: 'undefined', disable_ad: 0, download: 0 });
      return stripCmd(js && js.cmd ? str(js.cmd) : '') || direct;
    } catch (e) {
      if (direct) return direct;
      throw e;
    }
  }

  async shortEpg(ch: Channel): Promise<Program[]> {
    let js: any;
    try {
      js = await this.req({ type: 'itv', action: 'get_short_epg', ch_id: ch.id, size: 4 }, 10000);
    } catch {
      return [];
    }
    return (Array.isArray(js) ? js : [])
      .map((p: Obj) => ({ title: str(p.name), desc: str(p.descr), start: int(p.start_timestamp), end: int(p.stop_timestamp) }))
      .filter((p: Program) => p.start > 0)
      .sort((a: Program, b: Program) => a.start - b.start);
  }

  epgTable(ch: Channel): Promise<Program[]> {
    return this.shortEpg(ch);
  }

  catchupUrl(): string {
    return '';
  }

  // ---- Filmler / diziler (sayfalı)
  async mediaCategories(section: Section): Promise<Category[]> {
    const js = await this.req({ type: TYPES[section], action: 'get_categories' });
    return (Array.isArray(js) ? js : [])
      .filter((c: Obj) => c && str(c.id) !== '*')
      .map((c: Obj) => ({ id: str(c.id), name: str(c.title || c.name) || '?' }));
  }

  async mediaPage(section: Section, categoryId: string, page: number): Promise<Page<Media>> {
    const js = await this.req({
      type: TYPES[section], action: 'get_ordered_list', p: page, sortby: 'added',
      category: categoryId || '*', genre: categoryId || '*',
    }, 30000);
    if (!js || typeof js !== 'object') return { items: [], pages: 1 };
    const total = int(js.total_items);
    const perPage = int(js.max_page_items, 14) || 14;
    const pages = Math.max(1, Math.ceil(total / perPage));
    const items: Media[] = (Array.isArray(js.data) ? js.data : []).map((d: Obj) => {
      const name = str(d.name || d.o_name) || '?';
      const isSeries = section === 'series' || str(d.is_series) === '1';
      return {
        kind: isSeries ? 'series' : 'movie',
        id: str(d.id),
        name,
        poster: this.logo(str(d.screenshot_uri || d.logo)),
        categoryId: categoryId || str(d.category_id),
        rating: Math.min(10, parseFloat(str(d.rating_imdb || d.rating_kinopoisk)) || 0),
        year: str(d.year) || yearFrom(name),
        ext: 'mp4',
        added: ts(d.added),
        plot: str(d.description),
        cmd: str(d.cmd),
        extra: { plot: str(d.description), genre: str(d.genres_str), cast: str(d.actors), director: str(d.director), duration: str(d.time) },
      } as Media;
    });
    return { items, pages };
  }

  async mediaItems(section: Section, categoryId: string): Promise<Media[]> {
    return (await this.mediaPage(section, categoryId, 1)).items;
  }

  async mediaInfo(m: Media): Promise<MediaInfo | null> {
    return { ...emptyInfo(), ...(m.extra || {}) };
  }

  async seasons(m: Media): Promise<{ info: MediaInfo | null; seasons: Season[] }> {
    const list = async (type: string): Promise<Obj[]> => {
      const js = await this.req({ type, action: 'get_ordered_list', movie_id: m.id, season_id: 0, episode_id: 0, p: 1 }, 30000);
      return js && Array.isArray(js.data) ? js.data : [];
    };
    let data = await list('series');
    if (!data.length) data = await list('vod');
    const seasons: Season[] = [];
    data.forEach((s, i) => {
      const snum = int(str(s.season_number || s.name).replace(/\D/g, ''), i + 1) || i + 1;
      const eps: Episode[] = (Array.isArray(s.series) ? s.series : []).map((e: unknown) => {
        const n = int(e);
        return { id: `${str(s.id)}:${n}`, title: t('episode_n', n), season: snum, episode: n, ext: 'mp4', cmd: str(s.cmd) };
      });
      if (eps.length) seasons.push({ num: snum, episodes: eps });
    });
    seasons.sort((a, b) => a.num - b.num);
    return { info: { ...emptyInfo(), ...(m.extra || {}), poster: m.poster }, seasons };
  }

  private async vodLink(cmd: string, series: string): Promise<string> {
    const js = await this.req({ type: 'vod', action: 'create_link', cmd, series, forced_storage: 'undefined', disable_ad: 0, download: 0 });
    const url = stripCmd(js && js.cmd ? str(js.cmd) : '');
    if (!url) throw new ProviderError(t('err_play'));
    return url;
  }

  movieUrl(m: Media): Promise<string> {
    return this.vodLink(m.cmd || '', '');
  }

  episodeUrl(e: Episode): Promise<string> {
    return this.vodLink(e.cmd || '', String(e.episode));
  }
}
