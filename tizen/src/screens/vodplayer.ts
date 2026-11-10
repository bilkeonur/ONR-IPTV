// Film / bölüm oynatıcı: tam ekran, ilerleme çubuğu, sarma, kaldığı yerden devam, sıradaki bölüm.
import { Screen, toast } from '../app';
import { t } from '../i18n';
import { PlayRequest, back } from '../nav';
import { Key } from '../platform';
import { FULL, PlayerState, player } from '../player';
import { Episode } from '../providers/types';
import { session } from '../session';
import { store } from '../store';
import { duration, h, icon } from '../ui/dom';

export function vodPlayerScreen(req: PlayRequest): Screen {
  const media = req.media;
  let episode: Episode | undefined = req.episode;
  let unsub: (() => void) | null = null;
  let osdTimer = 0;
  let tickTimer = 0;
  let saveTimer = 0;
  let seekTarget: number | null = null;
  let seekTimer = 0;
  let state: PlayerState = 'idle';

  const titleEl = h('div', 'vosd-title');
  const subEl = h('div', 'vosd-sub');
  const fill = h('div', 'bar-fill');
  const knob = h('div', 'vosd-knob');
  const timeEl = h('div', 'vosd-time');
  const durEl = h('div', 'vosd-time right');
  const stateIcon = h('div', 'vosd-state');
  const osd = h('div', 'vosd',
    h('div', 'vosd-head', titleEl, subEl),
    h('div', 'vosd-bar', timeEl, h('div', 'bar big', fill, knob), durEl),
    h('div', 'vosd-hint', t('hint_vod')));
  const status = h('div', 'video-status');
  const el = h('div', 'screen vplayer', status, stateIcon, osd);

  function url(): string {
    if (!session.provider) return '';
    return episode ? session.provider.episodeUrl(episode) : session.provider.movieUrl(media);
  }

  function setTitles() {
    titleEl.textContent = media.name;
    subEl.textContent = episode ? `${t('season_n', episode.season)} · ${t('episode_n', episode.episode)} — ${episode.title}` : media.year || '';
  }

  function showOsd(autoHide = true) {
    osd.classList.add('show');
    clearTimeout(osdTimer);
    if (autoHide && state === 'playing') osdTimer = window.setTimeout(() => osd.classList.remove('show'), 4000);
  }

  function tick() {
    const d = player.duration();
    const pos = seekTarget !== null ? seekTarget : player.time();
    const pct = d > 0 ? Math.min(100, (pos / d) * 100) : 0;
    fill.style.width = `${pct}%`;
    knob.style.left = `${pct}%`;
    timeEl.textContent = duration(pos);
    durEl.textContent = d > 0 ? duration(d) : '--:--';
  }

  function save() {
    const d = player.duration();
    const pos = player.time();
    if (d > 0 && pos > 5) store.saveProgress(session.pid, media, episode, pos, d);
  }

  function start(at: number) {
    setTitles();
    player.play(url(), FULL, at);
    showOsd();
  }

  function nextEpisode(): Episode | undefined {
    if (!episode || !req.playlist) return undefined;
    const i = req.playlist.findIndex((e) => e.id === episode!.id);
    return i >= 0 ? req.playlist[i + 1] : undefined;
  }

  function onState(s: PlayerState) {
    state = s;
    status.className = `video-status ${s}`;
    status.textContent = s === 'error' ? t('err_play') : '';
    stateIcon.innerHTML = '';
    if (s === 'paused') stateIcon.appendChild(icon('pause', 'state-icon'));
    if (s === 'paused' || s === 'error') showOsd(false);
    if (s === 'playing') showOsd();
    if (s === 'ended') {
      // Bitti olarak kaydet
      const d = player.duration();
      store.saveProgress(session.pid, media, episode, d, d);
      const next = nextEpisode();
      if (next) {
        toast(`${t('next_episode')}: ${t('episode_n', next.episode)}`);
        episode = next;
        start(store.episodePos(session.pid, next.id));
      } else {
        back();
      }
    }
  }

  function seekBy(delta: number) {
    const d = player.duration();
    if (!d) return;
    const base = seekTarget !== null ? seekTarget : player.time();
    seekTarget = Math.max(0, Math.min(d - 2, base + delta));
    tick();
    showOsd();
    // Art arda basışlar birikir, tek seferde sarılır
    clearTimeout(seekTimer);
    seekTimer = window.setTimeout(() => {
      if (seekTarget !== null) player.seek(seekTarget);
      seekTarget = null;
    }, 700);
  }

  return {
    el,
    onShow() {
      unsub = player.onState(onState);
      tickTimer = window.setInterval(tick, 1000);
      saveTimer = window.setInterval(save, 15000);
      start(req.startAt || 0);
    },
    onHide() {
      save();
      clearInterval(tickTimer);
      clearInterval(saveTimer);
      clearTimeout(seekTimer);
      clearTimeout(osdTimer);
      if (unsub) unsub();
      player.stop();
    },
    onKey(key: Key): boolean {
      switch (key) {
        case 'ok': case 'playpause': case 'play': case 'pause':
          if (state === 'error') start(player.time());
          else player.togglePause();
          return true;
        case 'left': seekBy(-10); return true;
        case 'right': seekBy(10); return true;
        case 'rw': seekBy(-60); return true;
        case 'ff': seekBy(60); return true;
        case 'up': case 'down': case 'info':
          if (osd.classList.contains('show')) osd.classList.remove('show');
          else showOsd();
          return true;
        case 'stop': case 'back': back(); return true;
      }
      return true;
    },
  };
}
