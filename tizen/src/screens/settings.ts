import { Screen, toast } from '../app';
import { expiryText, setLang, t } from '../i18n';
import { back, open, restart } from '../nav';
import { Key, exitApp } from '../platform';
import { AnySection } from '../providers/types';
import { XtreamProvider } from '../providers/xtream';
import { session } from '../session';
import { Settings, store } from '../store';
import { h } from '../ui/dom';
import { confirm, showMenu } from '../ui/menu';
import { askPin, promptPin } from '../ui/pin';
import { TopBar } from '../ui/topbar';
import { clearEpg } from './epg';

declare const __VERSION__: string;

interface Row {
  el: HTMLElement;
  key: (k: Key) => boolean;
  /** Bölüm başlığı (seçilemez) */
  header?: boolean;
  paint?: () => void;
}

const ROW_H = 92;
const VISIBLE = 9;

function header(label: string): Row {
  return { el: h('div', 'set-header', label), key: () => false, header: true };
}

function choice<T extends string>(label: string, options: { v: T; label: string }[], get: () => T, set: (v: T) => void): Row {
  const value = h('span', 'set-value');
  const paint = () => {
    const o = options.find((x) => x.v === get()) || options[0];
    value.textContent = `‹  ${o.label}  ›`;
  };
  paint();
  return {
    el: h('div', 'set-row', h('span', 'set-label', label), value),
    paint,
    key: (k) => {
      if (k !== 'left' && k !== 'right' && k !== 'ok') return false;
      let i = options.findIndex((x) => x.v === get());
      i = (i + (k === 'left' ? -1 : 1) + options.length) % options.length;
      set(options[i].v);
      paint();
      return true;
    },
  };
}

function toggle(label: string, get: () => boolean, set: (v: boolean) => void | Promise<void>): Row {
  const value = h('span', 'set-value');
  const paint = () => {
    value.textContent = get() ? t('on') : t('off');
    value.classList.toggle('on', get());
  };
  paint();
  return {
    el: h('div', 'set-row', h('span', 'set-label', label), value),
    paint,
    key: (k) => {
      if (k !== 'left' && k !== 'right' && k !== 'ok') return false;
      Promise.resolve(set(!get())).then(paint);
      return true;
    },
  };
}

function action(label: string, run: () => void, value?: () => string, danger = false): Row {
  const v = h('span', 'set-value');
  const paint = () => { v.textContent = value ? value() : '›'; };
  paint();
  return {
    el: h('div', `set-row${danger ? ' danger' : ''}`, h('span', 'set-label', label), v),
    paint,
    key: (k) => {
      if (k !== 'ok' && k !== 'right') return false;
      run();
      return true;
    },
  };
}

export function settingsScreen(): Screen {
  let index = 1;
  let topRow = 0;
  const bar = new TopBar(t('settings_title'));
  const settings: Settings = store.settings();
  const save = () => store.saveSettings(settings);

  const sectionLabel = (s: AnySection) => t(s === 'live' ? 'tile_live' : s === 'movie' ? 'tile_movies' : 'tile_series');

  async function setPin() {
    if (settings.pin) {
      showMenu(t('parental_pin'), [
        { label: t('pin_change'), run: () => { askPin(true).then((ok) => { if (ok) newPin(); }); } },
        { label: t('pin_remove'), danger: true, run: () => {
          askPin(true).then((ok) => {
            if (!ok) return;
            settings.pin = '';
            save();
            toast(t('pin_removed'));
            paintAll();
          });
        } },
      ], 0);
    } else newPin();
  }

  async function newPin() {
    const a = await promptPin(t('pin_new'), t('pin_new_hint'));
    if (!a) return;
    const b = await promptPin(t('pin_repeat'));
    if (b === null) return;
    if (a !== b) { toast(t('pin_mismatch')); return; }
    settings.pin = a;
    save();
    session.markUnlocked();
    toast(t('pin_saved'));
    paintAll();
  }

  async function pickCats(section: AnySection, mode: 'hide' | 'lock') {
    if (mode === 'lock') {
      if (!settings.pin) { toast(t('pin_required_first')); return; }
      if (!(await askPin())) return;
    }
    open('catpicker', { section, mode });
  }

  function refreshLists() {
    session.refresh();
    clearEpg();
    toast(t('lists_refreshing'));
    const prov = session.provider;
    if (prov) prov.authenticate().then((a) => { if (prov === session.provider) session.account = a; }).catch(() => undefined);
  }

  const rows: Row[] = [
    header(t('set_account')),
    action(t('profiles'), () => open('profiles'), () => (session.profile ? `${session.profile.name}  ›` : '›')),
    action(t('refresh_lists'), refreshLists),

    header(t('set_appearance')),
    choice(t('set_language'),
      [{ v: '' as const, label: t('lang_system') }, { v: 'tr' as const, label: 'Türkçe' }, { v: 'en' as const, label: 'English' }],
      () => settings.lang,
      (v) => {
        settings.lang = v;
        save();
        setLang(v);
        // Tüm ekranlar yeni dille yeniden kurulsun
        setTimeout(() => { restart('home'); open('settings'); }, 0);
      }),
    toggle(t('show_epg_in_list'), () => settings.showEpgInList, (v) => { settings.showEpgInList = v; save(); }),

    header(t('set_player')),
    choice(t('set_live_format'),
      [{ v: 'ts' as const, label: 'MPEG-TS (.ts)' }, { v: 'm3u8' as const, label: 'HLS (.m3u8)' }],
      () => settings.liveFormat,
      (v) => {
        settings.liveFormat = v;
        save();
        if (session.provider instanceof XtreamProvider) session.provider.liveExt = v;
      }),
    toggle(t('auto_reconnect'), () => settings.autoReconnect, (v) => { settings.autoReconnect = v; save(); }),

    header(t('parental')),
    action(t('parental_pin'), setPin, () => (settings.pin ? `${t('pin_set')}  ›` : `${t('pin_not_set')}  ›`)),
    toggle(t('lock_adult'), () => settings.lockAdult, async (v) => {
      if (!settings.pin) { toast(t('pin_required_first')); return; }
      if (!(await askPin())) return;
      settings.lockAdult = v;
      save();
    }),
    ...(['live', 'movie', 'series'] as AnySection[]).map((s) => action(`${t('hide_cats')}: ${sectionLabel(s)}`, () => pickCats(s, 'hide'),
      () => { const n = session.pset.hidden[s].length; return n ? `${n}  ›` : '›'; })),
    ...(['live', 'movie', 'series'] as AnySection[]).map((s) => action(`${t('lock_cats')}: ${sectionLabel(s)}`, () => pickCats(s, 'lock'),
      () => { const n = session.pset.locks[s].cats.length; return n ? `${n}  ›` : '›'; })),

    header(t('about')),
    action(t('exit_app'), () => confirm(t('exit_app_q'), t('yes'), t('no'), exitApp), undefined, true),
  ];

  const p = session.profile;
  const a = session.account;
  const line = (k: string, v: string) => h('div', 'acc-line', h('span', 'muted', k), h('span', '', v));
  const accountBox = h('div', 'account');
  function fillAccount() {
    const acc = session.account || a;
    accountBox.innerHTML = '';
    accountBox.appendChild(h('div', 'col-title', t('account_info')));
    if (p) {
      accountBox.appendChild(line(t('field_name'), p.name));
      accountBox.appendChild(line(t('acc_type'), p.type === 'xtream' ? 'Xtream Codes' : p.type === 'm3u' ? 'M3U' : 'Stalker Portal'));
      accountBox.appendChild(line(p.type === 'm3u' ? t('field_m3u') : t('field_server'), p.url.replace(/\/\/[^@/]*@/, '//')));
      if (p.username) accountBox.appendChild(line(t('field_username'), p.username));
      if (p.mac) accountBox.appendChild(line(t('field_mac'), p.mac));
    }
    if (acc) {
      accountBox.appendChild(line(t('acc_status'), acc.status || '—'));
      accountBox.appendChild(line(t('acc_expires'), expiryText(acc.expires) || t('unlimited')));
      if (acc.maxConnections) accountBox.appendChild(line(t('acc_connections'), `${acc.activeConnections || 0} / ${acc.maxConnections}`));
    }
    accountBox.appendChild(h('div', 'about',
      h('div', 'about-name', h('span', 'brand-mark', 'ONR'), ' IPTV'),
      h('div', 'muted', `${t('set_version')} ${typeof __VERSION__ !== 'undefined' ? __VERSION__ : '1.0.0'}`),
      h('div', 'muted', `${t('developer')}: Onur BiLKE`),
      h('div', 'muted', 'Xtream Codes · M3U · Stalker Portal')));
  }

  const list = h('div', 'set-list-inner');
  rows.forEach((r) => list.appendChild(r.el));
  const el = h('div', 'screen settings',
    bar.el,
    h('div', 'settings-body',
      h('div', 'set-list', list),
      accountBox));

  function paintAll() {
    rows.forEach((r) => r.paint && r.paint());
    paint();
  }

  function paint() {
    if (index < topRow + 1) topRow = Math.max(0, index - 1);
    if (index >= topRow + VISIBLE) topRow = index - VISIBLE + 1;
    list.style.transform = `translateY(${-topRow * ROW_H}px)`;
    rows.forEach((r, i) => r.el.classList.toggle('focused', i === index));
  }

  function move(d: number) {
    let i = index + d;
    while (rows[i] && rows[i].header) i += d;
    if (rows[i]) index = i;
    paint();
  }

  fillAccount();
  paint();

  return {
    el,
    onShow() {
      bar.start();
      fillAccount();
      paintAll();
    },
    onHide: () => bar.stop(),
    onKey(key) {
      if (key === 'up') { move(-1); return true; }
      if (key === 'down') { move(1); return true; }
      if (key === 'back') { back(); return true; }
      return rows[index].key(key);
    },
  };
}
