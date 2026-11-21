// Profiller: birden çok IPTV hesabı arasında geçiş, ekleme, düzenleme, silme.
import { Screen, busy, toast } from '../app';
import { t } from '../i18n';
import { back, open, restart } from '../nav';
import { Key } from '../platform';
import { createProvider, session } from '../session';
import { Profile, store } from '../store';
import { h } from '../ui/dom';
import { confirm, showMenu } from '../ui/menu';
import { TopBar } from '../ui/topbar';
import { clearEpg } from './epg';

const TYPE_LABEL: Record<Profile['type'], string> = { xtream: 'Xtream Codes', m3u: 'M3U', stalker: 'Stalker Portal' };

/** Profili etkinleştirir ve ana ekrana döner; hesap bilgisi arka planda gelir. */
export function activateProfile(p: Profile): void {
  const provider = createProvider(p);
  clearEpg();
  session.start(p, provider, null);
  restart('home');
  busy(true);
  provider.authenticate()
    .then((a) => { if (session.provider === provider) session.account = a; })
    .catch((e) => toast((e as Error).message, 5000))
    .then(() => busy(false));
}

export function profilesScreen(): Screen {
  let index = 0;
  let profiles: Profile[] = [];
  const bar = new TopBar(t('profiles'));
  const list = h('div', 'prof-list');
  const el = h('div', 'screen profiles', bar.el, h('div', 'prof-body', list));
  let rows: HTMLElement[] = [];

  function build() {
    profiles = store.profiles();
    list.innerHTML = '';
    rows = profiles.map((p) => {
      const active = session.profile && session.profile.id === p.id;
      return h('div', `prof-row${active ? ' active' : ''}`,
        h('div', 'prof-avatar', (p.name || '?').slice(0, 1).toUpperCase()),
        h('div', 'prof-main',
          h('div', 'prof-name', p.name, active ? h('span', 'prof-badge', t('active')) : null),
          h('div', 'prof-sub', `${TYPE_LABEL[p.type]}  ·  ${p.url.replace(/^https?:\/\//i, '').replace(/[?#].*$/, '')}`)));
    });
    rows.push(h('div', 'prof-row add', h('div', 'prof-avatar', '+'), h('div', 'prof-main', h('div', 'prof-name', t('profile_add')))));
    rows.forEach((r) => list.appendChild(r));
    index = Math.min(index, rows.length - 1);
    paint();
  }

  function paint() {
    rows.forEach((r, i) => r.classList.toggle('focused', i === index));
    list.style.transform = `translateY(${-Math.max(0, index - 5) * 132}px)`;
  }

  function remove(p: Profile) {
    confirm(t('profile_delete_q', p.name), t('delete'), t('cancel'), () => {
      store.removeProfile(p.id);
      const wasActive = session.profile && session.profile.id === p.id;
      if (!wasActive) { build(); return; }
      const next = store.profiles()[0];
      session.logout();
      if (next) activateProfile(next);
      else restart('login');
    });
  }

  function actions(p: Profile) {
    const active = session.profile && session.profile.id === p.id;
    showMenu(p.name, [
      ...(active ? [] : [{ label: t('profile_use'), run: () => activateProfile(p) }]),
      { label: t('edit'), run: () => open('login', { profile: p, cancelable: true }) },
      { label: t('delete'), danger: true, run: () => remove(p) },
    ], 0);
  }

  return {
    el,
    onShow() {
      bar.start();
      build();
    },
    onHide() { bar.stop(); },
    onKey(key: Key): boolean {
      switch (key) {
        case 'up': index = Math.max(0, index - 1); paint(); return true;
        case 'down': index = Math.min(rows.length - 1, index + 1); paint(); return true;
        case 'ok':
          if (index >= profiles.length) open('login', { cancelable: true });
          else actions(profiles[index]);
          return true;
        case 'red':
          if (profiles[index]) remove(profiles[index]);
          return true;
        case 'back': back(); return true;
      }
      return true;
    },
  };
}
