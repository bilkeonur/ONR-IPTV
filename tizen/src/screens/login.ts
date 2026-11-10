import { Screen, busy, isEditing } from '../app';
import { t } from '../i18n';
import { restart } from '../nav';
import { Key, exitApp } from '../platform';
import { ProviderError } from '../providers/types';
import { createProvider, session } from '../session';
import { Profile, store } from '../store';
import { h } from '../ui/dom';

type Kind = 'xtream' | 'm3u';

interface Field {
  el: HTMLElement;
  input?: HTMLInputElement;
  kinds: Kind[];
  action?: (key: Key) => boolean;
}

export function loginScreen(): Screen {
  let kind: Kind = 'xtream';
  let index = 0;
  const error = h('div', 'login-error');

  const input = (label: string, type = 'text'): HTMLInputElement =>
    h('input', { type, placeholder: label, autocomplete: 'off', autocapitalize: 'off', spellcheck: 'false' });

  const name = input(t('field_name'));
  const server = input(t('field_server'));
  const user = input(t('field_username'));
  const pass = input(t('field_password'), 'password');
  const m3u = input(t('field_m3u'));
  server.value = 'http://';
  m3u.value = 'http://';

  const typeX = h('div', 'seg', t('type_xtream'));
  const typeM = h('div', 'seg', t('type_m3u'));
  const btn = h('div', 'button primary', t('connect'));

  const row = (label: string, inp: HTMLInputElement) => h('label', 'field', h('span', 'field-label', label), inp);

  const fields: Field[] = [
    {
      el: h('div', 'segmented', typeX, typeM),
      kinds: ['xtream', 'm3u'],
      action: (key) => {
        if (key === 'left' || key === 'right' || key === 'ok') {
          kind = key === 'left' ? 'xtream' : key === 'right' ? 'm3u' : kind === 'xtream' ? 'm3u' : 'xtream';
          layout();
          return true;
        }
        return false;
      },
    },
    { el: row(t('field_name'), name), input: name, kinds: ['xtream', 'm3u'] },
    { el: row(t('field_server'), server), input: server, kinds: ['xtream'] },
    { el: row(t('field_username'), user), input: user, kinds: ['xtream'] },
    { el: row(t('field_password'), pass), input: pass, kinds: ['xtream'] },
    { el: row(t('field_m3u'), m3u), input: m3u, kinds: ['m3u'] },
    { el: btn, kinds: ['xtream', 'm3u'], action: (key) => (key === 'ok' ? (connect(), true) : false) },
  ];

  const visible = () => fields.filter((f) => f.kinds.indexOf(kind) >= 0);

  function layout() {
    typeX.classList.toggle('on', kind === 'xtream');
    typeM.classList.toggle('on', kind === 'm3u');
    fields.forEach((f) => { f.el.style.display = f.kinds.indexOf(kind) >= 0 ? '' : 'none'; });
    paint();
  }

  function paint() {
    const vis = visible();
    index = Math.min(index, vis.length - 1);
    fields.forEach((f) => f.el.classList.toggle('focused', f === vis[index]));
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
  typeX.addEventListener('click', (e) => { e.stopPropagation(); kind = 'xtream'; layout(); });
  typeM.addEventListener('click', (e) => { e.stopPropagation(); kind = 'm3u'; layout(); });

  async function connect() {
    error.textContent = '';
    const blank = (s: string) => !s.trim() || /^https?:\/\/$/i.test(s.trim());
    const p: Profile = {
      id: String(Date.now()),
      type: kind,
      name: name.value.trim(),
      url: kind === 'xtream' ? server.value.trim() : m3u.value.trim(),
      username: kind === 'xtream' ? user.value.trim() : '',
      password: kind === 'xtream' ? pass.value : '',
    };
    if (blank(p.url) || (kind === 'xtream' && (!p.username || !p.password))) {
      error.textContent = t('required');
      return;
    }
    if (!p.name) p.name = p.url.replace(/^https?:\/\//i, '').split(/[/:?]/)[0];
    btn.textContent = t('connecting');
    busy(true);
    try {
      const provider = createProvider(p);
      const account = await provider.authenticate();
      store.setProfile(p);
      session.start(p, provider, account);
      restart('home');
    } catch (e) {
      error.textContent = e instanceof ProviderError ? e.message : String(e);
    } finally {
      busy(false);
      btn.textContent = t('connect');
    }
  }

  const el = h('div', 'screen login',
    h('div', 'login-card',
      h('div', 'brand big', h('span', 'brand-mark', 'ONR'), ' IPTV'),
      h('h1', '', t('login_title')),
      h('p', 'muted', t('login_hint')),
      fields.map((f) => f.el),
      error));

  // Düzenlenen alan klavyenin üstünde kalsın: kartı, alan ekranın üst kısmına gelecek kadar kaydır
  const card = el.firstChild as HTMLElement;
  fields.forEach((f) => {
    if (!f.input) return;
    f.input.addEventListener('focus', () => {
      // offsetTop dönüşümden etkilenmez (sahne pikseli); .screen'e göredir
      const top = f.el.offsetTop;
      card.style.transform = `translateY(${Math.round(110 - top)}px)`;
    });
    f.input.addEventListener('blur', () => { card.style.transform = ''; });
  });

  layout();

  return {
    el,
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
        exitApp();
        return true;
      }
      return false;
    },
  };
}
