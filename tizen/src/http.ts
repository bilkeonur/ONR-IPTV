import { isTizen } from './platform';

export class HttpError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

/** Tarayıcıda geliştirirken istekler yerel proxy üzerinden gider (CORS). */
const useProxy = !isTizen && /^(localhost|127\.0\.0\.1)$/.test(location.hostname);

export const USER_AGENT = 'ONRIPTV-Tizen/1.0';

export type Headers = Record<string, string>;

export function buildUrl(base: string, params: Record<string, string | number | undefined>): string {
  const q = Object.keys(params)
    .filter((k) => params[k] !== undefined && params[k] !== '')
    .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(String(params[k]))}`)
    .join('&');
  return q ? `${base}${base.indexOf('?') >= 0 ? '&' : '?'}${q}` : base;
}

/** gzip ile sıkıştırılmış yanıtları (ör. .xml.gz rehber dosyaları) açar; tarayıcı desteklemiyorsa null. */
async function gunzip(buf: ArrayBuffer): Promise<ArrayBuffer | null> {
  const DS = (window as unknown as { DecompressionStream?: new (f: string) => TransformStream }).DecompressionStream;
  if (!DS) return null;
  const stream = new Blob([buf]).stream().pipeThrough(new DS('gzip'));
  return new Response(stream).arrayBuffer();
}

export async function getText(url: string, timeoutMs = 30000, headers?: Headers): Promise<string> {
  let target = url;
  let h: Headers | undefined = headers;
  if (useProxy) {
    // Proxy, X-Fwd-* başlıklarını hedefe asıl adlarıyla iletir (Cookie gibi tarayıcının yasakladıkları dahil)
    target = `/__proxy?url=${encodeURIComponent(url)}`;
    h = { 'X-UA': (headers && headers['User-Agent']) || USER_AGENT };
    if (headers) Object.keys(headers).forEach((k) => { h![`X-Fwd-${k}`] = headers[k]; });
  }
  const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
  const timer = setTimeout(() => ctrl && ctrl.abort(), timeoutMs);
  let res: Response;
  let buf: ArrayBuffer;
  try {
    res = await fetch(target, { signal: ctrl ? ctrl.signal : undefined, headers: h, credentials: 'omit' });
    if (!res.ok) throw new HttpError(res.status, `HTTP ${res.status}`);
    buf = await res.arrayBuffer();
  } catch (e) {
    if (e instanceof HttpError) throw e;
    throw new HttpError(0, (e as Error).name === 'AbortError' ? 'timeout' : String((e as Error).message || e));
  } finally {
    clearTimeout(timer);
  }
  const head = new Uint8Array(buf, 0, Math.min(2, buf.byteLength));
  if (head[0] === 0x1f && head[1] === 0x8b) {
    const out = await gunzip(buf);
    if (!out) throw new HttpError(0, 'gzip');
    buf = out;
  }
  return new TextDecoder('utf-8').decode(buf);
}

export async function getJson<T = unknown>(url: string, timeoutMs = 30000, headers?: Headers): Promise<T | null> {
  const text = (await getText(url, timeoutMs, headers)).trim();
  if (!text) return null;
  return JSON.parse(text) as T;
}
