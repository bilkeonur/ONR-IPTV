// Ekranlar arası geçiş (döngüsel import olmasın diye kayıtla).
import { Screen, pop, push, reset } from './app';
import { Episode, Media } from './providers/types';

export interface Routes {
  login: void;
  home: void;
  live: void;
  settings: void;
  vod: 'movie' | 'series';
  detail: Media;
  play: PlayRequest;
}

export interface PlayRequest {
  media: Media;
  episode?: Episode;
  /** Dizi bölümlerinde sıradaki bölüme geçmek için tüm liste */
  playlist?: Episode[];
  startAt?: number;
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
