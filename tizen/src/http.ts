import { isTizen } from './platform';

export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Tarayıcıda geliştirirken istekler yerel proxy üzerinden gider (CORS). */
const useProxy = !isTizen && /^(localhost|127\.0\.0\.1)$/.test(location.hostname);

export const USER_AGENT = 'ONRIPTV-Tizen/1.0';

export function buildUrl(base: string, params: Record<string, string | number | undefined>): string {
  const q = Object.keys(params)
    .filter((k) => params[k] !== undefined && params[k] !== '')
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(params[k]))}`)
    .join('&');
  return q ? `${base}${base.indexOf('?') >= 0 ? '&' : '?'}${q}` : base;
}

export async function getText(url: string, timeoutMs = 30000): Promise<string> {
  const target = useProxy ? `/__proxy?url=${encodeURIComponent(url)}` : url;
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timer = setTimeout(() => ctrl && ctrl.abort(), timeoutMs);
  let res: Response;
  try {
    res = await fetch(target, { signal: ctrl ? ctrl.signal : undefined, headers: useProxy ? { 'X-UA': USER_AGENT } : undefined });
  } catch (e) {
    throw new HttpError(0, (e as Error).name === 'AbortError' ? 'timeout' : String((e as Error).message || e));
  } finally {
    clearTimeout(timer);
  }
  if (!res.ok) throw new HttpError(res.status, `HTTP ${res.status}`);
  return res.text();
}

export async function getJson<T = unknown>(url: string, timeoutMs = 30000): Promise<T | null> {
  const text = (await getText(url, timeoutMs)).trim();
  if (!text) return null;
  return JSON.parse(text) as T;
}
