// TV / tarayıcı farkları: kumanda tuşları, uygulamadan çıkış.
/* eslint-disable @typescript-eslint/no-explicit-any */
declare const __DEV__: boolean;

const w = window as any;
export const isTizen = typeof w.tizen !== 'undefined';
export const hasAvplay = isTizen && !!(w.webapis && w.webapis.avplay);

export type Key =
  | 'up' | 'down' | 'left' | 'right' | 'ok' | 'back'
  | 'chup' | 'chdown' | 'playpause' | 'play' | 'pause' | 'stop' | 'ff' | 'rw'
  | 'red' | 'green' | 'yellow' | 'blue' | 'info' | 'done' | 'cancel'
  | '0' | '1' | '2' | '3' | '4' | '5' | '6' | '7' | '8' | '9';

const TIZEN_KEYS = [
  'MediaPlayPause', 'MediaPlay', 'MediaPause', 'MediaStop', 'MediaFastForward', 'MediaRewind',
  'ChannelUp', 'ChannelDown', 'ColorF0Red', 'ColorF1Green', 'ColorF2Yellow', 'ColorF3Blue', 'Info',
  '0', '1', '2', '3', '4', '5', '6', '7', '8', '9',
];

export function registerKeys(): void {
  if (!isTizen) return;
  try {
    w.tizen.tvinputdevice.registerKeyBatch(TIZEN_KEYS);
  } catch {
    for (const k of TIZEN_KEYS) {
      try { w.tizen.tvinputdevice.registerKey(k); } catch { /* model desteklemiyor */ }
    }
  }
}

const CODES: Record<number, Key> = {
  37: 'left', 38: 'up', 39: 'right', 40: 'down', 13: 'ok',
  10009: 'back', 10252: 'playpause', 415: 'play', 19: 'pause', 413: 'stop', 417: 'ff', 412: 'rw',
  427: 'chup', 428: 'chdown', 403: 'red', 404: 'green', 405: 'yellow', 406: 'blue', 457: 'info',
  65376: 'done', 65385: 'cancel',
};

/** Tarayıcıda test için klavye karşılıkları: Esc=Geri, PgUp/PgDn=kanal, Boşluk=oynat/duraklat, F1-F4=renkli tuşlar, I=bilgi. */
const BROWSER: Record<string, Key> = {
  Escape: 'back', PageUp: 'chup', PageDown: 'chdown', ' ': 'playpause',
  F1: 'red', F2: 'green', F3: 'yellow', F4: 'blue', i: 'info', '.': 'ff', ',': 'rw',
};

export function keyOf(e: KeyboardEvent, inInput: boolean): Key | null {
  const byCode = CODES[e.keyCode];
  if (byCode) return byCode;
  if (e.keyCode >= 48 && e.keyCode <= 57 && !inInput) return String(e.keyCode - 48) as Key;
  if (!isTizen && !inInput) {
    if (e.key === 'Backspace') return 'back';
    const k = BROWSER[e.key];
    if (k) return k;
  }
  if (!isTizen && inInput && e.key === 'Escape') return 'cancel';
  return null;
}

export function exitApp(): void {
  if (isTizen) {
    try { w.tizen.application.getCurrentApplication().exit(); } catch { /* yok */ }
  }
}

export const DEV = typeof __DEV__ !== 'undefined' && __DEV__;
