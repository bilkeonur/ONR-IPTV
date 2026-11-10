import { Screen, toast } from '../app';
import { currentLang, setLang, t } from '../i18n';
import { back, open, restart } from '../nav';
import { Key } from '../platform';
import { XtreamProvider } from '../providers/xtream';
import { session } from '../session';
import { store } from '../store';
import { h } from '../ui/dom';
import { TopBar } from '../ui/topbar';

declare const __VERSION__: string;

interface Row {
  el: HTMLElement;
  key: (k: Key) => boolean;
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

export function settingsScreen(): Screen {
  let index = 0;
  let logoutArmed = 0;
  const bar = new TopBar(t('settings_title'));
  const settings = store.settings();

  const lang = choice(t('set_language'),
    [{ v: '' as const, label: t('lang_system') }, { v: 'tr' as const, label: 'Türkçe' }, { v: 'en' as const, label: 'English' }],
    () => settings.lang,
    (v) => {
      settings.lang = v;
      store.saveSettings(settings);
      setLang(v);
      // Tüm ekranlar yeni dille yeniden kurulsun
      setTimeout(() => { restart('home'); open('settings'); }, 0);
    });

  const format = choice(t('set_live_format'),
    [{ v: 'ts' as const, label: 'MPEG-TS (.ts)' }, { v: 'm3u8' as const, label: 'HLS (.m3u8)' }],
    () => settings.liveFormat,
    (v) => {
      settings.liveFormat = v;
      store.saveSettings(settings);
      if (session.provider instanceof XtreamProvider) session.provider.liveExt = v;
    });

  const logout: Row = {
    el: h('div', 'set-row danger', h('span', 'set-label', t('set_logout'))),
    key: (k) => {
      if (k !== 'ok') return false;
      if (Date.now() - logoutArmed < 3000) {
        session.logout();
        restart('login');
      } else {
        logoutArmed = Date.now();
        toast(t('confirm_logout'), 3000);
      }
      return true;
    },
  };

  const rows: Row[] = [lang, format, logout];

  const p = session.profile;
  const a = session.account;
  const exp = a && a.expires && a.expires !== '0' && a.expires !== 'null'
    ? new Date(parseInt(a.expires, 10) * 1000).toLocaleDateString(currentLang() === 'tr' ? 'tr-TR' : 'en-GB')
    : t('unlimited');
  const line = (k: string, v: string) => h('div', 'acc-line', h('span', 'muted', k), h('span', '', v));
  const account = h('div', 'account',
    h('div', 'col-title', t('set_account')),
    p ? line(t('field_name'), p.name) : null,
    p ? line(t('field_server'), p.url.replace(/\/\/[^@/]*@/, '//')) : null,
    p && p.username ? line(t('field_username'), p.username) : null,
    a ? line(t('acc_status'), a.status || '—') : null,
    a ? line(t('acc_expires'), exp) : null,
    a && a.maxConnections ? line(t('acc_connections'), `${a.activeConnections || 0} / ${a.maxConnections}`) : null,
    line(t('set_version'), typeof __VERSION__ !== 'undefined' ? __VERSION__ : '1.0.0'));

  const el = h('div', 'screen settings',
    bar.el,
    h('div', 'settings-body',
      h('div', 'set-list', h('div', 'col-title', t('settings_title')), rows.map((r) => r.el)),
      account));

  const paint = () => {
    rows.forEach((r, i) => r.el.classList.toggle('focused', i === index));
  };
  paint();

  return {
    el,
    onShow: () => bar.start(),
    onHide: () => bar.stop(),
    onKey(key) {
      if (key === 'up') { index = Math.max(0, index - 1); paint(); return true; }
      if (key === 'down') { index = Math.min(rows.length - 1, index + 1); paint(); return true; }
      if (key === 'back') { back(); return true; }
      return rows[index].key(key);
    },
  };
}
