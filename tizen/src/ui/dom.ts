type Child = Node | string | null | undefined | false;

export function h<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  props: { [key: string]: unknown } | string = {},
  ...children: (Child | Child[])[]
): HTMLElementTagNameMap[K] {
  const el = document.createElement(tag);
  const p = typeof props === 'string' ? { class: props } : props;
  for (const k of Object.keys(p)) {
    const v = p[k];
    if (v === undefined || v === null || v === false) continue;
    if (k === 'class') el.className = String(v);
    else if (k === 'text') el.textContent = String(v);
    else if (k === 'html') el.innerHTML = String(v);
    else if (k.startsWith('on') && typeof v === 'function') (el as unknown as Record<string, unknown>)[k.toLowerCase()] = v;
    else el.setAttribute(k, String(v));
  }
  const add = (c: Child | Child[]) => {
    if (Array.isArray(c)) c.forEach(add);
    else if (c !== null && c !== undefined && c !== false) el.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  };
  children.forEach(add);
  return el;
}

const initialsOf = (name: string): string =>
  name.replace(/[^\p{L}\p{N} ]/gu, '').trim().split(/\s+/).slice(0, 2).map((w) => w[0] || '').join('').toUpperCase();

/** Kanal logosu; yüklenemezse adın baş harfleri gösterilir. */
export function logo(src: string, name: string, cls = 'logo'): HTMLElement {
  const box = h('div', cls);
  const initials = h('span', 'initials', initialsOf(name));
  box.appendChild(initials);
  if (src) {
    const img = h('img', { alt: '' });
    img.onload = () => { initials.style.display = 'none'; };
    img.onerror = () => img.remove();
    img.src = src;
    box.appendChild(img);
  }
  return box;
}

/** Film/dizi afişi; görsel yoksa adı yazan renkli bir kart. */
export function poster(src: string, name: string, cls = 'poster-img'): HTMLElement {
  const box = h('div', cls);
  const ph = h('div', 'poster-ph', h('span', '', name));
  let hue = 0;
  for (let i = 0; i < name.length; i++) hue = (hue * 31 + name.charCodeAt(i)) % 360;
  ph.style.background = `linear-gradient(160deg, hsl(${hue},35%,26%), hsl(${(hue + 40) % 360},30%,14%))`;
  box.appendChild(ph);
  if (src) {
    const img = h('img', { alt: '' });
    img.onload = () => { ph.style.display = 'none'; };
    img.onerror = () => img.remove();
    img.src = src;
    box.appendChild(img);
  }
  return box;
}

export function hhmm(sec: number): string {
  const d = new Date(sec * 1000);
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** 3725 → "1:02:05", 125 → "2:05" */
export function duration(sec: number): string {
  const s = Math.max(0, Math.floor(sec));
  const hh = Math.floor(s / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const p = (n: number) => String(n).padStart(2, '0');
  return hh ? `${hh}:${p(mm)}:${p(ss)}` : `${mm}:${p(ss)}`;
}

export const nowSec = (): number => Math.floor(Date.now() / 1000);

/** Basit çizgi simgeler (currentColor). */
export const ICONS = {
  live: '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="5" y="12" width="38" height="26" rx="4"/><path d="M17 4l7 8 7-8M16 44h16"/></svg>',
  movie: '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="8" width="36" height="32" rx="4"/><path d="M14 8v32M34 8v32M6 18h8M6 30h8M34 18h8M34 30h8"/></svg>',
  series: '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="14" width="30" height="24" rx="3"/><path d="M10 9h28a4 4 0 0 1 4 4v19"/><path d="M16 21l9 5-9 5z" fill="currentColor"/></svg>',
  settings: '<svg viewBox="0 0 48 48" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><circle cx="24" cy="24" r="6"/><path d="M24 4v6M24 38v6M4 24h6M38 24h6M9.9 9.9l4.2 4.2M33.9 33.9l4.2 4.2M9.9 38.1l4.2-4.2M33.9 14.1l4.2-4.2"/></svg>',
  play: '<svg viewBox="0 0 48 48"><path d="M14 8l28 16-28 16z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 48 48"><path d="M12 8h8v32h-8zM28 8h8v32h-8z" fill="currentColor"/></svg>',
  star: '<svg viewBox="0 0 24 24"><path d="M12 2l3 6.9 7.5.7-5.7 5 1.7 7.4L12 18.3 5.5 22l1.7-7.4-5.7-5 7.5-.7z" fill="currentColor"/></svg>',
};

export function icon(name: keyof typeof ICONS, cls = 'icon'): HTMLElement {
  return h('span', { class: cls, html: ICONS[name] });
}
