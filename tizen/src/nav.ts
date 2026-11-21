// Ekranlar arası geçiş (döngüsel import olmasın diye kayıtla).
import { Screen, pop, push, reset } from './app';
import { AnySection, Channel, Episode, Media, Program } from './providers/types';
import { Profile } from './store';

export interface Routes {
  /** Profil ekleme/düzenleme; ilk kurulumda argümansız */
  login: { profile?: Profile; cancelable?: boolean } | void;
  home: void;
  /** Belirli bir kanalı açmak için kimliği */
  live: { channelId?: string } | void;
  settings: void;
  profiles: void;
  vod: 'movie' | 'series';
  detail: Media;
  play: PlayRequest;
  /** Arama; scope verilirse yalnızca o bölümde. onChannel: kanal seçilince (arama kapanır) */
  search: { scope?: AnySection; onChannel?: (ch: Channel) => void } | void;
  /** onPlay: şu anki programa OK basılınca (rehber kapanır, kanal açılır) */
  guide: { channels: Channel[]; label: string; onPlay?: (ch: Channel) => void; onCatchup?: (ch: Channel, p: Program) => void };
  catpicker: { section: AnySection; mode: 'hide' | 'lock' };
}

export interface PlayRequest {
  media: Media;
  episode?: Episode;
  /** Dizi bölümlerinde sıradaki bölüme geçmek için tüm liste */
  playlist?: Episode[];
  startAt?: number;
  /** Geçmiş yayın (catch-up): media yalnızca başlık için kullanılır */
  catchup?: { ch: Channel; prog: Program; url: string };
}

type Factory<K extends keyof Routes> = (arg: Routes[K]) => Screen;
const routes: { [K in keyof Routes]?: Factory<K> } = {};

export function register<K extends keyof Routes>(name: K, f: Factory<K>): void {
  (routes as Record<string, unknown>)[name] = f;
}

function make<K extends keyof Routes>(name: K, arg: Routes[K]): Screen {
  return (routes[name] as Factory<K>)(arg);
}

export function open<K extends keyof Routes>(name: K, arg?: Routes[K]): void {
  push(make(name, arg as Routes[K]));
}

export function restart<K extends keyof Routes>(name: K, arg?: Routes[K]): void {
  reset(make(name, arg as Routes[K]));
}

export const back = pop;
