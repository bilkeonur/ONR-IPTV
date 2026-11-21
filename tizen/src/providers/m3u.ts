import { HttpError, getText } from '../http';
import { t } from '../i18n';
import {
  AccountInfo, Category, Channel, Episode, Media, MediaInfo, Program, Provider, ProviderError, Season, Section,
  normalizeUrl, yearFrom,
} from './types';

const ATTR_RE = /([\w-]+)="([^"]*)"/g;
const EP_RE = /^(.*?)[\s._\-|]*S(\d{1,2})[\s._\-]*E(\d{1,4})/i;
const VOD_EXT = /\.(mp4|mkv|avi|mov|wmv|m4v|flv|webm|mpg|mpeg)$/i;

interface Entry {
  name: string;
  url: string;
  attrs: Record<string, string>;
  group: string;
  section: 'live' | Section;
}

function attrs(s: string): Record<string, string> {
  const out: Record<string, string> = {};
  let m: RegExpExecArray | null;
  ATTR_RE.lastIndex = 0;
  while ((m = ATTR_RE.exec(s))) out[m[1]] = m[2];
  return out;
}

function classify(url: string, group: string): Entry['section'] {
  const u = url.split('?')[0].toLowerCase();
  const g = group.toLowerCase();
  if (u.indexOf('/series/') >= 0) return 'series';
  if (u.indexOf('/movie/') >= 0) return 'movie';
  if (VOD_EXT.test(u)) return /dizi|series|sezon|season/.test(g) ? 'series' : 'movie';
  return 'live';
}

/** #EXTM3U satırındaki url-tvg / x-tvg-url rehber adresi */
export function headerEpgUrl(text: string): string {
  const first = text.slice(0, 2000).split(/\r?\n/).find((l) => l.trim().startsWith('#EXTM3U'));
  if (!first) return '';
  const a = attrs(first);
  return (a['url-tvg'] || a['x-tvg-url'] || '').split(',')[0].trim();
}

export function parseM3u(text: string, otherGroup: string): Entry[] {
  const out: Entry[] = [];
  let info: { name: string; attrs: Record<string, string> } | null = null;
  let groupOverride = '';
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line) continue;
    if (line.startsWith('#EXTINF')) {
      const body = line.slice(8);
      // Ad, tırnak dışındaki ilk virgülden sonra gelir
      let inQ = false;
      let split = -1;
      for (let i = 0; i < body.length; i++) {
        const ch = body[i];
        if (ch === '"') inQ = !inQ;
        else if (ch === ',' && !inQ) { split = i; break; }
      }
      const a = attrs(split >= 0 ? body.slice(0, split) : body);
      const name = split >= 0 ? body.slice(split + 1).trim() : '';
      info = { name: name || a['tvg-name'] || '', attrs: a };
      groupOverride = '';
    } else if (line.startsWith('#EXTGRP:')) {
      groupOverride = line.slice(8).trim();
    } else if (!line.startsWith('#')) {
      const fallbackName = line.split('?')[0].split('/').pop() || line;
      const a = info ? info.attrs : {};
      const group = a['group-title'] || groupOverride || otherGroup;
      out.push({ name: (info && info.name) || fallbackName, url: line, attrs: a, group, section: classify(line, group) });
      info = null;
      groupOverride = '';
    }
  }
  return out;
}

const extOf = (url: string): string => {
  const m = /\.([a-z0-9]{2,4})$/i.exec(url.split('?')[0]);
  return m ? m[1] : 'mp4';
};

// ---- XMLTV rehberi
const unxml = (s: string): string => s
  .replace(/<!\[CDATA\[([\s\S]*?)\]\]>/g, '$1')
  .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&apos;/g, "'")
  .replace(/&#(\d+);/g, (_m, n) => String.fromCharCode(parseInt(n, 10)))
  .replace(/&amp;/g, '&').trim();

/** "20240501200000 +0300" → epoch saniye */
export function xmltvTime(s: string): number {
  const m = /^(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})?\s*([+-]\d{4})?/.exec((s || '').trim());
  if (!m) return 0;
  let t = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +(m[6] || 0)) / 1000;
  if (m[7]) {
    const sign = m[7][0] === '+' ? 1 : -1;
    t -= sign * (parseInt(m[7].slice(1, 3), 10) * 3600 + parseInt(m[7].slice(3, 5), 10) * 60);
  }
  return t;
}

/** Kanal kimliği (ve küçük harfli adı) → programlar. Yalnızca yakın zamandakiler tutulur. */
export function parseXmltv(text: string): Record<string, Program[]> {
  const now = Date.now() / 1000;
  const lo = now - 6 * 3600;
  const hi = now + 36 * 3600;
  const names: Record<string, string> = {};
  const progs: Record<string, Program[]> = {};
  const chRe = /<channel\s+id="([^"]*)"[^>]*>([\s\S]*?)<\/channel>/g;
  let m: RegExpExecArray | null;
  while ((m = chRe.exec(text))) {
    const dn = /<display-name[^>]*>([\s\S]*?)<\/display-name>/.exec(m[2]);
    if (dn) names[unxml(dn[1]).toLowerCase()] = m[1];
  }
  const pRe = /<programme\s([^>]*)>([\s\S]*?)<\/programme>/g;
  while ((m = pRe.exec(text))) {
    const a = attrs(m[1]);
    const start = xmltvTime(a.start);
    const end = xmltvTime(a.stop);
    if (!(end > lo && start < hi)) continue;
    const title = /<title[^>]*>([\s\S]*?)<\/title>/.exec(m[2]);
    const desc = /<desc[^>]*>([\s\S]*?)<\/desc>/.exec(m[2]);
    const ch = a.channel || '';
    (progs[ch] = progs[ch] || []).push({ title: title ? unxml(title[1]) : '', desc: desc ? unxml(desc[1]) : '', start, end });
  }
  const out: Record<string, Program[]> = {};
  Object.keys(progs).forEach((id) => {
    const list = progs[id].sort((x, y) => x.start - y.start);
    out[id] = list;
    out[id.toLowerCase()] = list;
  });
  Object.keys(names).forEach((nm) => {
    if (progs[names[nm]] && !out[nm]) out[nm] = progs[names[nm]];
  });
  return out;
}

export class M3uProvider implements Provider {
  readonly kind = 'm3u' as const;
  readonly paged: Section[] = [];
  private entries: Entry[] | null = null;
  private url: string;
  private seriesCache: Media[] | null = null;
  private epgUrl: string;
  private epg: Promise<Record<string, Program[]>> | null = null;

  constructor(url: string, epgUrl = '') {
    this.url = normalizeUrl(url);
    this.epgUrl = epgUrl.trim();
  }

  private async load(): Promise<Entry[]> {
    if (this.entries) return this.entries;
    let text: string;
    try {
      text = await getText(this.url, 180000);
    } catch (e) {
      const err = e as HttpError;
      if (err.status === 401 || err.status === 403) throw new ProviderError(t('err_unauthorized'));
      if (err.status > 0) throw new ProviderError(t('err_http', err.status));
      throw new ProviderError(t('err_connect', err.message));
    }
    text = text.replace(/^﻿/, '');
    if (text.indexOf('#EXTINF') < 0 && text.indexOf('#EXTM3U') < 0) throw new ProviderError(t('err_not_m3u'));
    this.entries = parseM3u(text, t('cat_other'));
    if (!this.epgUrl) this.epgUrl = headerEpgUrl(text);
    return this.entries;
  }

  async authenticate(): Promise<AccountInfo | null> {
    await this.load();
    return null;
  }

  private async groups(section: Entry['section']): Promise<Category[]> {
    const seen: Record<string, true> = {};
    const cats: Category[] = [];
    for (const e of await this.load()) {
      if (e.section === section && !seen[e.group]) {
        seen[e.group] = true;
        cats.push({ id: e.group, name: e.group });
      }
    }
    return cats;
  }

  liveCategories(): Promise<Category[]> {
    return this.groups('live');
  }

  async liveChannels(): Promise<Channel[]> {
    const live = (await this.load()).filter((e) => e.section === 'live');
    return live.map((e, i) => ({
      id: `l${i}`,
      num: parseInt(e.attrs['tvg-chno'], 10) || i + 1,
      name: e.name,
      logo: e.attrs['tvg-logo'] || '',
      categoryId: e.group,
      url: e.url,
      epgId: e.attrs['tvg-id'] || e.attrs['tvg-name'] || e.name,
      archive: !!(e.attrs.catchup || e.attrs.timeshift),
    }));
  }

  async streamUrl(ch: Channel): Promise<string> {
    return ch.url || '';
  }

  private loadEpg(): Promise<Record<string, Program[]>> {
    if (!this.epg) {
      this.epg = this.epgUrl
        ? getText(normalizeUrl(this.epgUrl), 180000).then(parseXmltv).catch(() => ({}))
        : Promise.resolve({});
    }
    return this.epg;
  }

  private async programs(ch: Channel): Promise<Program[]> {
    await this.load();
    if (!this.epgUrl) return [];
    const epg = await this.loadEpg();
    const id = ch.epgId || '';
    return epg[id] || epg[id.toLowerCase()] || epg[ch.name.toLowerCase()] || [];
  }

  async shortEpg(ch: Channel): Promise<Program[]> {
    const now = Date.now() / 1000;
    return (await this.programs(ch)).filter((p) => p.end > now).slice(0, 4);
  }

  async epgTable(ch: Channel): Promise<Program[]> {
    const now = Date.now() / 1000;
    return (await this.programs(ch)).filter((p) => p.end > now - 3 * 3600 && p.start < now + 86400);
  }

  catchupUrl(): string {
    return '';
  }

  mediaCategories(section: Section): Promise<Category[]> {
    return this.groups(section);
  }

  /** M3U dizileri: "Ad S01E02" biçimindeki bölümler ada göre gruplanır. */
  private async allSeries(): Promise<Media[]> {
    if (this.seriesCache) return this.seriesCache;
    const by: Record<string, Media> = {};
    const list: Media[] = [];
    (await this.load()).forEach((e, i) => {
      if (e.section !== 'series') return;
      const m = EP_RE.exec(e.name);
      const show = (m ? m[1] : e.name).trim() || e.name;
      const key = `${e.group}|${show.toLowerCase()}`;
      let s = by[key];
      if (!s) {
        s = by[key] = {
          kind: 'series', id: `s${list.length}`, name: show, poster: e.attrs['tvg-logo'] || '',
          categoryId: e.group, rating: 0, year: yearFrom(show), episodes: [],
        };
        list.push(s);
      }
      (s.episodes as Episode[]).push({
        id: `e${i}`, title: e.name, season: m ? parseInt(m[2], 10) : 1, episode: m ? parseInt(m[3], 10) : s.episodes!.length + 1,
        ext: extOf(e.url), url: e.url, image: e.attrs['tvg-logo'] || '',
      });
    });
    this.seriesCache = list;
    return list;
  }

  async mediaItems(section: Section, categoryId: string): Promise<Media[]> {
    if (section === 'series') {
      const all = await this.allSeries();
      return categoryId ? all.filter((s) => s.categoryId === categoryId) : all;
    }
    const out: Media[] = [];
    (await this.load()).forEach((e, i) => {
      if (e.section !== 'movie' || (categoryId && e.group !== categoryId)) return;
      out.push({
        kind: 'movie', id: `m${i}`, name: e.name, poster: e.attrs['tvg-logo'] || '', categoryId: e.group,
        rating: 0, year: yearFrom(e.name), ext: extOf(e.url), url: e.url,
      });
    });
    return out;
  }

  async mediaInfo(): Promise<MediaInfo | null> {
    return null;
  }

  async seasons(m: Media): Promise<{ info: MediaInfo | null; seasons: Season[] }> {
    const by: Record<number, Episode[]> = {};
    for (const e of m.episodes || []) (by[e.season] = by[e.season] || []).push(e);
    const seasons = Object.keys(by).map((k) => ({
      num: parseInt(k, 10),
      episodes: by[parseInt(k, 10)].sort((a, b) => a.episode - b.episode),
    })).sort((a, b) => a.num - b.num);
    return { info: null, seasons };
  }

  async movieUrl(m: Media): Promise<string> {
    return m.url || '';
  }

  async episodeUrl(e: Episode): Promise<string> {
    return e.url || '';
  }
}
