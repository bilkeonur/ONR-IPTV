// PIN penceresi: kumandanın rakam tuşlarıyla ya da ekrandaki tuş takımıyla (oklar + OK) girilir.
import { Screen, close, push, toast } from '../app';
import { t } from '../i18n';
import { Key } from '../platform';
import { session } from '../session';
import { store } from '../store';
import { h } from './dom';

const PAD = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '⌫', '0', '✓'];
const LEN = 4;

/** 4 haneli PIN ister; iptal edilirse null. */
export function promptPin(title: string, hint = ''): Promise<string | null> {
  return new Promise((resolve) => {
    let value = '';
    let index = 0;
    let done = false;
    const dots = Array.from({ length: LEN }, () => h('div', 'pin-dot'));
    const keys = PAD.map((k) => h('div', `pin-key${k === '✓' ? ' ok' : ''}`, k));
    const msg = h('div', 'pin-hint', hint);
    const box = h('div', 'menu-box pin-box',
      h('div', 'menu-title', title), h('div', 'pin-dots', dots), msg, h('div', 'pin-pad', keys));
    const el = h('div', 'modal', box);

    function paint() {
      dots.forEach((d, i) => d.classList.toggle('on', i < value.length));
      keys.forEach((k, i) => k.classList.toggle('focused', i === index));
    }

    function finish(v: string | null) {
      if (done) return;
      done = true;
      close(screen);
      resolve(v);
    }

    function press(k: string) {
      if (k === '⌫') value = value.slice(0, -1);
      else if (k === '✓') { if (value.length === LEN) finish(value); return; }
      else if (value.length < LEN) value += k;
      paint();
      if (value.length === LEN) setTimeout(() => finish(value), 150);
    }

    const screen: Screen = {
      el,
      overlay: true,
      onKey(key: Key): boolean {
        if (key.length === 1 && key >= '0' && key <= '9') { press(key); return true; }
        switch (key) {
          case 'left': if (index % 3) index--; break;
          case 'right': if (index % 3 < 2) index++; break;
          case 'up': if (index >= 3) index -= 3; break;
          case 'down': if (index < 9) index += 3; break;
          case 'ok': press(PAD[index]); return true;
          case 'back': case 'cancel': finish(null); return true;
        }
        paint();
        return true;
      },
    };
    keys.forEach((k, i) => k.addEventListener('click', () => { index = i; press(PAD[i]); }));
    paint();
    push(screen);
  });
}

/**
 * Korumalı içerik için PIN sorar. PIN yoksa ya da son 5 dakikada girildiyse doğrudan true.
 * force: kilit ayarlarını değiştirmek gibi işlemler için her zaman sor.
 */
export async function askPin(force = false): Promise<boolean> {
  const pin = store.settings().pin;
  if (!pin) return true;
  if (!force && session.unlocked) return true;
  const v = await promptPin(t('pin_enter'));
  if (v === null) return false;
  if (v !== pin) {
    toast(t('pin_wrong'));
    return false;
  }
  session.markUnlocked();
  return true;
}
