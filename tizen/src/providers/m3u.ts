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

export class M3uProvider implements Provider {
  readonly kind = 'm3u' as const;
  private entries: Entry[] | null = null;
  private url: string;
  private seriesCache: Media[] | null = null;

  constructor(url: string) {
    this.url = normalizeUrl(url);
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
      epgId: e.attrs['tvg-id'] || '',
    }));
  }

  streamUrl(ch: Channel): string {
    return ch.url || '';
  }

  async shortEpg(): Promise<Program[]> {
    return []; // XMLTV desteği sonraki adımda
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

  movieUrl(m: Media): string {
    return m.url || '';
  }

  episodeUrl(e: Episode): string {
    return e.url || '';
  }
}
