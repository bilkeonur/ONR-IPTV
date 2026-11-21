// Arama, sıralama, içerik dili ve yetişkin içerik algılama (masaüstü sürümle aynı kurallar).
import { SortMode } from './store';

export const ADULT_RE = /(xxx|adult|\+18|18\+|yetişkin|porn|erotik|for adults)/i;

const TR: Record<string, string> = { ı: 'i', İ: 'i', ş: 's', Ş: 's', ğ: 'g', Ğ: 'g', ü: 'u', Ü: 'u', ö: 'o', Ö: 'o', ç: 'c', Ç: 'c' };

/** Türkçe karakter, aksan ve büyük/küçük harf duyarsız metin. */
export function fold(s: string): string {
  const t = (s || '').replace(/[ıİşŞğĞüÜöÖçÇ]/g, (c) => TR[c]).toLowerCase();
  return t.normalize ? t.normalize('NFKD').replace(/[̀-ͯ]/g, '') : t;
}

const foldCache = new WeakMap<object, string>();
export function folded(o: { name: string }): string {
  let f = foldCache.get(o);
  if (f === undefined) {
    f = fold(o.name);
    foldCache.set(o, f);
  }
  return f;
}

// İçerik dili: ad ya da kategori başındaki "TR:", "|DE|", "[EN]", "FR -" gibi etiketler
const LANG_TAG_RE = /^\s*[[(|]?\s*([A-Za-z]{2,3})\s*(?:[\])|:▎┃•\-–]|\s\|)/;
const LANG_CODES = new Set(('TR EN UK US GB DE FR IT ES NL AR PT PL RU AL GR RO BG SE NO DK FI IN PK IR KU AZ BE CH AT HU CZ ' +
  'SK HR RS BA MK SI UA IL JP KR CN BR MX LAT CA AU IE AF EX KZ GE AM LB SY IQ EG MA DZ TN SA AE QA').split(' '));
const LANG_ALIAS: Record<string, string> = {
  UK: 'EN', US: 'EN', GB: 'EN', AU: 'EN', IE: 'EN', CA: 'EN', AT: 'DE', CH: 'DE', BE: 'FR', BR: 'PT', MX: 'ES', LAT: 'ES',
};
const LANG_WORDS: [RegExp, string][] = [
  [/\b(t[uü]rk|turkish|turkiye|türkiye)/i, 'TR'],
  [/\b(english|ingilizce)\b/i, 'EN'],
  [/\b(german|deutsch|almanca)\b/i, 'DE'],
  [/\b(french|fran[cç]ais|frans[ıi]zca)\b/i, 'FR'],
  [/\b(arabic|arap[cç]a)\b/i, 'AR'],
  [/\b(spanish|espa[nñ]ol)\b/i, 'ES'],
  [/\b(italian|italiano)\b/i, 'IT'],
];

export function langTag(name: string): string {
  if (!name) return '';
  const m = LANG_TAG_RE.exec(name);
  if (m) {
    const code = m[1].toUpperCase();
    if (LANG_CODES.has(code)) return LANG_ALIAS[code] || code;
  }
  for (const [rx, code] of LANG_WORDS) if (rx.test(name)) return code;
  return '';
}

/** Öğenin dili: önce adından, yoksa kategorisinin adından. */
export function langOf(item: { name: string; categoryId: string }, catNames: Record<string, string>): string {
  return langTag(item.name) || langTag(catNames[item.categoryId] || '');
}

/** [(kod, adet)] — en çok içeriği olan dil önce. */
export function languages(items: { name: string; categoryId: string }[], catNames: Record<string, string>): [string, number][] {
  const counts: Record<string, number> = {};
  for (const it of items) {
    const c = langOf(it, catNames);
    if (c) counts[c] = (counts[c] || 0) + 1;
  }
  return Object.keys(counts).map((k) => [k, counts[k]] as [string, number]).sort((a, b) => b[1] - a[1]);
}

interface Sortable { name: string; num?: number; added?: number; rating?: number; year?: string }

export function sortItems<T extends Sortable>(items: T[], mode: SortMode): T[] {
  const byName = (a: T, b: T) => folded(a).localeCompare(folded(b));
  const list = items.slice();
  switch (mode) {
    case 'az': return list.sort(byName);
    case 'za': return list.sort((a, b) => byName(b, a));
    case 'new': return list.sort((a, b) => (b.added || 0) - (a.added || 0));
    case 'rating': return list.sort((a, b) => (b.rating || 0) - (a.rating || 0));
    case 'year': return list.sort((a, b) => (b.year || '0').localeCompare(a.year || '0'));
    case 'num': return list.sort((a, b) => (a.num || 1e9) - (b.num || 1e9));
    default: return list;
  }
}

/** Genel arama: başta eşleşenler önce. */
export function search<T extends { name: string }>(items: T[], query: string, limit: number): T[] {
  const q = fold(query.trim());
  if (!q) return [];
  const out = items.filter((i) => folded(i).indexOf(q) >= 0);
  out.sort((a, b) => {
    const sa = folded(a).indexOf(q) === 0 ? 0 : 1;
    const sb = folded(b).indexOf(q) === 0 ? 0 : 1;
    return sa - sb || a.name.length - b.name.length;
  });
  return out.slice(0, limit);
}
