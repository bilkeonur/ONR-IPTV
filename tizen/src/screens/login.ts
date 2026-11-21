// Profil ekleme / düzenleme: Xtream Codes, M3U (isteğe bağlı XMLTV rehberi) ve Stalker portal.
import { Screen, busy, isEditing } from '../app';
import { t } from '../i18n';
import { back, restart } from '../nav';
import { Key, exitApp } from '../platform';
import { MAC_RE, randomMac } from '../providers/stalker';
import { ProviderError } from '../providers/types';
import { createProvider, session } from '../session';
import { Profile, ProfileType, store } from '../store';
import { h } from '../ui/dom';
import { clearEpg } from './epg';

interface Field {
  el: HTMLElement;
  input?: HTMLInputElement;
  kinds: ProfileType[];
  action?: (key: Key) => boolean;
}

const KINDS: ProfileType[] = ['xtream', 'm3u', 'stalker'];

export function loginScreen(arg: { profile?: Profile; cancelable?: boolean } | void): Screen {
  const editing = arg && arg.profile;
  const cancelable = !!(arg && arg.cancelable);
  let kind: ProfileType = editing ? editing.type : 'xtream';
  let index = 0;
  const error = h('div', 'login-error');

  const input = (label: string, type = 'text'): HTMLInputElement =>
    h('input', { type, placeholder: label, autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false' });

  const name = input(t('field_name'));
  const server = input(t('field_server'));
  const user = input(t('field_username'));
  const pass = input(t('field_password'), 'password');
  const m3u = input(t('field_m3u'));
  const epg = input(t('field_epg_hint'));
  const portal = input(t('field_portal'));
  const mac = input('00:1A:79:XX:XX:XX');
  server.value = 'http://';
  m3u.value = 'http://';
  portal.value = 'http://';
  mac.value = randomMac();
  if (editing) {
    name.value = editing.name;
    if (editing.type === 'xtream') {
      server.value = editing.url;
      user.value = editing.username;
      pass.value = editing.password;
    } else if (editing.type === 'm3u') {
      m3u.value = editing.url;
      epg.value = editing.epgUrl || '';
    } else {
      portal.value = editing.url;
      mac.value = editing.mac || mac.value;
    }
  }

  const segs = KINDS.map((k) => h('div', 'seg', t(`type_${k}` as 'type_xtream')));
  const btn = h('div', 'button primary', editing ? t('save') : t('connect'));
  const macBtn = h('div', 'button small', t('mac_generate'));

  const row = (label: string, inp: HTMLInputElement) => h('label', 'field', h('span', 'field-label', label), inp);

  const fields: Field[] = [
    {
      el: h('div', 'segmented', segs),
      kinds: KINDS,
      action: (key) => {
        if (key === 'left' || key === 'right' || key === 'ok') {
          const i = KINDS.indexOf(kind);
          const d = key === 'left' ? -1 : 1;
          kind = KINDS[(i + d + KINDS.length) % KINDS.length];
          layout();
          return true;
        }
        return false;
      },
    },
    { el: row(t('field_name'), name), input: name, kinds: KINDS },
    { el: row(t('field_server'), server), input: server, kinds: ['xtream'] },
    { el: row(t('field_username'), user), input: user, kinds: ['xtream'] },
    { el: row(t('field_password'), pass), input: pass, kinds: ['xtream'] },
    { el: row(t('field_m3u'), m3u), input: m3u, kinds: ['m3u'] },
    { el: row(t('field_epg'), epg), input: epg, kinds: ['m3u'] },
    { el: row(t('field_portal'), portal), input: portal, kinds: ['stalker'] },
    { el: row(t('field_mac'), mac), input: mac, kinds: ['stalker'] },
    {
      el: macBtn, kinds: ['stalker'],
      action: (key) => {
        if (key !== 'ok') return false;
        mac.value = randomMac();
        return true;
      },
    },
    { el: btn, kinds: KINDS, action: (key) => (key === 'ok' ? (connect(), true) : false) },
  ];

  const visible = () => fields.filter((f) => f.kinds.indexOf(kind) >= 0);

  function layout() {
    segs.forEach((s, i) => s.classList.toggle('on', KINDS[i] === kind));
    fields.forEach((f) => { f.el.style.display = f.kinds.indexOf(kind) >= 0 ? '' : 'none'; });
    paint();
  }

  function paint() {
    const vis = visible();
    index = Math.min(index, vis.length - 1);
    fields.forEach((f) => f.el.classList.toggle('focused', f === vis[index]));
    // Uzun formlarda odaklı alan görünür kalsın
    const f = vis[index];
    if (f && !isEditing()) {
      const overflow = f.el.offsetTop + f.el.offsetHeight - 1000;
      card.style.transform = overflow > 0 ? `translateY(${-overflow}px)` : '';
    }
  }

  function move(d: number) {
    if (isEditing()) (document.activeElement as HTMLElement).blur();
    index = Math.max(0, Math.min(visible().length - 1, index + d));
    paint();
  }

  // Fareyle de kullanılabilsin (tarayıcıda test)
  fields.forEach((f) => {
    f.el.addEventListener('click', () => {
      index = visible().indexOf(f);
      paint();
      if (f.input) f.input.focus();
      else if (f.action) f.action('ok');
    });
  });
  segs.forEach((s, i) => s.addEventListener('click', (e) => { e.stopPropagation(); kind = KINDS[i]; layout(); }));

  async function connect() {
    error.textContent = '';
    const blank = (s: string) => !s.trim() || /^https?:\/\/$/i.test(s.trim());
    const url = kind === 'xtream' ? server.value.trim() : kind === 'm3u' ? m3u.value.trim() : portal.value.trim();
    const p: Profile = {
      id: editing ? editing.id : String(Date.now()),
      type: kind,
      name: name.value.trim(),
      url,
      username: kind === 'xtream' ? user.value.trim() : '',
      password: kind === 'xtream' ? pass.value : '',
    };
    if (kind === 'm3u' && !blank(epg.value)) p.epgUrl = epg.value.trim();
    if (kind === 'stalker') p.mac = mac.value.trim().toUpperCase();
    if (blank(p.url) || (kind === 'xtream' && (!p.username || !p.password))) {
      error.textContent = t('required');
      return;
    }
    if (kind === 'stalker' && !MAC_RE.test(p.mac || '')) {
      error.textContent = t('err_mac');
      return;
    }
    if (!p.name) p.name = p.url.replace(/^https?:\/\//i, '').split(/[/:?]/)[0];
    btn.textContent = t('connecting');
    busy(true);
    try {
      const provider = createProvider(p);
      const account = await provider.authenticate();
      store.upsertProfile(p);
      clearEpg();
      session.start(p, provider, account);
      restart('home');
    } catch (e) {
      error.textContent = e instanceof ProviderError ? e.message : String(e);
    } finally {
      busy(false);
      btn.textContent = editing ? t('save') : t('connect');
    }
  }

  const card = h('div', 'login-card',
    h('div', 'brand big', h('span', 'brand-mark', 'ONR'), ' IPTV'),
    h('h1', '', editing ? t('profile_edit') : t('login_title')),
    h('p', 'muted', t('login_hint')),
    fields.map((f) => f.el),
    error);
  const el = h('div', 'screen login', card);

  // Düzenlenen alan klavyenin üstünde kalsın: kartı, alan ekranın üst kısmına gelecek kadar kaydır
  fields.forEach((f) => {
    if (!f.input) return;
    f.input.addEventListener('focus', () => {
      // offsetTop dönüşümden etkilenmez (sahne pikseli); .screen'e göredir
      const top = f.el.offsetTop;
      card.style.transform = `translateY(${Math.round(110 - top)}px)`;
    });
    f.input.addEventListener('blur', () => { card.style.transform = ''; paint(); });
  });

  layout();

  return {
    el,
    onShow() { layout(); },
    onKey(key) {
      const vis = visible();
      const f = vis[index];
      if (isEditing()) {
        // Ekran klavyesinde Bitti/OK: sonraki alana geç
        if (key === 'ok' || key === 'done' || key === 'down') { move(1); return true; }
        if (key === 'cancel' || key === 'up' || key === 'back') { move(key === 'up' ? -1 : 0); return true; }
        return false;
      }
      if (key === 'up') { move(-1); return true; }
      if (key === 'down') { move(1); return true; }
      if (f.action && f.action(key)) return true;
      if (key === 'ok' && f.input) {
        f.input.focus();
        const v = f.input.value;
        f.input.setSelectionRange(v.length, v.length);
        return true;
      }
      if (key === 'back') {
        if (cancelable) back();
        else exitApp();
        return true;
      }
      return false;
    },
  };
}
