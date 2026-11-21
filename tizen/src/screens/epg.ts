// Yayın akışı önbellekleri ve sıralı yükleme (aynı anda en fazla 3 istek).
import { Channel, Program } from '../providers/types';
import { session } from '../session';
import { nowSec } from '../ui/dom';

const shortCache = new Map<string, { at: number; progs: Program[] }>();
const pending = new Set<string>();
let queue: Channel[] = [];
let running = 0;

export function cachedEpg(ch: Channel): Program[] | null {
  const c = shortCache.get(ch.id);
  return c && Date.now() - c.at < 5 * 60000 ? c.progs : null;
}

export function requestEpg(chans: Channel[], done: (ch: Channel) => void): void {
  queue = chans.filter((c) => !cachedEpg(c) && !pending.has(c.id));
  const pump = () => {
    while (running < 3 && queue.length) {
      const ch = queue.shift() as Channel;
      pending.add(ch.id);
      running++;
      const p = session.provider ? session.provider.shortEpg(ch) : Promise.resolve([]);
      p.catch(() => [] as Program[]).then((progs) => {
        shortCache.set(ch.id, { at: Date.now(), progs });
        pending.delete(ch.id);
        running--;
        done(ch);
        pump();
      });
    }
  };
  pump();
}

// ---- Geniş akış (rehber)
const tableCache = new Map<string, { at: number; progs: Program[] }>();

export function cachedTable(ch: Channel): Program[] | null {
  const c = tableCache.get(ch.id);
  return c && Date.now() - c.at < 15 * 60000 ? c.progs : null;
}

export async function epgTable(ch: Channel): Promise<Program[]> {
  const c = cachedTable(ch);
  if (c) return c;
  let progs: Program[] = [];
  try {
    progs = session.provider ? await session.provider.epgTable(ch) : [];
  } catch { /* boş */ }
  tableCache.set(ch.id, { at: Date.now(), progs });
  return progs;
}

/** Hesap değişince önbellekler boşaltılır. */
export function clearEpg(): void {
  shortCache.clear();
  tableCache.clear();
  queue = [];
}

export function nowNext(progs: Program[] | null): { now?: Program; next?: Program } {
  if (!progs) return {};
  const n = nowSec();
  const i = progs.findIndex((p) => p.start <= n && n < p.end);
  if (i >= 0) return { now: progs[i], next: progs[i + 1] };
  return { next: progs.find((p) => p.start > n) };
}

export const progress = (p: Program): number =>
  Math.max(0, Math.min(100, ((nowSec() - p.start) / Math.max(1, p.end - p.start)) * 100));
