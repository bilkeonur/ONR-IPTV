// Film / dizi ayrıntısı: arka plan görseli, afiş, bilgiler, Oynat / Devam et; dizilerde sezon ve bölümler.
import { Screen, busy, toast } from '../app';
import { t } from '../i18n';
import { back, open } from '../nav';
import { Key } from '../platform';
import { Episode, Media, MediaInfo, Season } from '../providers/types';
import { session } from '../session';
import { store } from '../store';
import { ICONS, duration, h, icon, poster } from '../ui/dom';

type Zone = 'buttons' | 'seasons' | 'episodes';

interface Btn { el: HTMLElement; run: () => void }

export function detailScreen(media: Media): Screen {
  let zone: Zone = 'buttons';
  let btnIdx = 0;
  let seasonIdx = 0;
  let epIdx = 0;
  let buttons: Btn[] = [];
  let seasons: Season[] = [];
  let info: MediaInfo | null = null;
  let loaded = false;

  const backdrop = h('div', 'detail-bg');
  const posterBox = h('div', 'detail-poster', poster(media.poster, media.name));
  const title = h('div', 'detail-title', media.name);
  const meta = h('div', 'detail-meta');
  const plot = h('div', 'detail-plot', media.plot || '');
  const credits = h('div', 'detail-credits');
  const btnRow = h('div', 'detail-buttons');
  const seasonRow = h('div', 'season-row');
  const epInner = h('div', 'hrow-inner');
  const epRow = h('div', 'hrow episodes', epInner);
  const seriesBox = h('div', 'detail-series', seasonRow, epRow);
  if (media.kind !== 'series') seriesBox.style.display = 'none';

  const el = h('div', `screen detail ${media.kind}`,
    backdrop,
    h('div', 'detail-shade'),
    h('div', 'detail-main', posterBox,
      h('div', 'detail-info', title, meta, plot, credits, btnRow)),
    seriesBox);

  function setBackdrop(url: string) {
    if (!url) return;
    const img = new Image();
    img.onload = () => {
      backdrop.style.backgroundImage = `url("${url.replace(/"/g, '%22')}")`;
      backdrop.classList.add('show');
    };
    img.src = url;
  }

  function fillMeta() {
    const parts: string[] = [];
    const year = media.year || (info && info.release ? info.release.slice(0, 4) : '');
    if (year) parts.push(year);
    const rating = media.rating || (info ? parseFloat(info.rating) || 0 : 0);
    meta.innerHTML = '';
    if (rating) meta.appendChild(h('span', { class: 'meta-rating', html: ICONS.star }, rating.toFixed(1)));
    if (info && info.duration) parts.push(info.duration);
    if (info && info.genre) parts.push(info.genre);
    if (media.kind === 'series' && seasons.length) parts.push(t('seasons_n', seasons.length));
    meta.appendChild(h('span', '', parts.join('  ·  ')));
    plot.textContent = (info && info.plot) || media.plot || (loaded ? t('no_plot') : '');
    credits.innerHTML = '';
    if (info && info.director) credits.appendChild(h('div', '', h('span', 'muted', `${t('director')}: `), info.director));
    if (info && info.cast) credits.appendChild(h('div', 'clamp1', h('span', 'muted', `${t('cast')}: `), info.cast));
  }

  const allEpisodes = (): Episode[] => seasons.reduce<Episode[]>((a, s) => a.concat(s.episodes), []);

  function playEpisode(ep: Episode, startAt?: number) {
    const pos = startAt !== undefined ? startAt : store.episodePos(session.pid, ep.id);
    open('play', { media, episode: ep, playlist: allEpisodes(), startAt: pos });
  }

  function makeButtons() {
    buttons = [];
    const btn = (label: string, primary: boolean, run: () => void) => {
      const b = h('div', `dbtn${primary ? ' primary' : ''}`, primary ? icon('play', 'dbtn-icon') : null, label);
      buttons.push({ el: b, run });
    };
    if (media.kind === 'movie') {
      const p = store.progress(session.pid, `movie:${media.id}`);
      if (p && p.pos > 30) {
        btn(t('resume_at', duration(p.pos)), true, () => open('play', { media, startAt: p.pos }));
        btn(t('restart'), false, () => open('play', { media, startAt: 0 }));
      } else {
        btn(t('play'), true, () => open('play', { media, startAt: 0 }));
      }
    } else if (seasons.length) {
      const p = store.progress(session.pid, `series:${media.id}`);
      const ep = p && p.episode ? allEpisodes().find((e) => e.id === p.episode!.id) : undefined;
      if (ep) {
        btn(t('resume_at', t('se_short', ep.season, ep.episode)), true, () => playEpisode(ep));
      }
      const firstEp = seasons[0].episodes[0];
      if (firstEp) btn(ep ? t('restart') : t('play'), !ep, () => playEpisode(firstEp, 0));
    }
    btnRow.innerHTML = '';
    buttons.forEach((b) => btnRow.appendChild(b.el));
    btnIdx = Math.min(btnIdx, Math.max(0, buttons.length - 1));
  }

  function fillSeasons() {
    seasonRow.innerHTML = '';
    seasons.forEach((s) => seasonRow.appendChild(h('div', 'chip', t('season_n', s.num))));
    fillEpisodes();
  }

  function fillEpisodes() {
    epInner.innerHTML = '';
    const s = seasons[seasonIdx];
    if (!s) return;
    s.episodes.forEach((e) => {
      const pos = store.episodePos(session.pid, e.id);
      epInner.appendChild(h('div', 'ecard',
        poster(e.image || media.backdrop || media.poster, e.title, 'ecard-img'),
        h('div', 'ecard-num', t('episode_n', e.episode)),
        h('div', 'ecard-title', e.title),
        pos > 0 ? h('div', 'ecard-resume', `▶ ${duration(pos)}`) : null));
    });
    epIdx = Math.min(epIdx, Math.max(0, s.episodes.length - 1));
  }

  function paint() {
    buttons.forEach((b, i) => b.el.classList.toggle('focused', zone === 'buttons' && i === btnIdx));
    const chips = seasonRow.children;
    for (let i = 0; i < chips.length; i++) {
      chips[i].classList.toggle('current', i === seasonIdx);
      chips[i].classList.toggle('focused', zone === 'seasons' && i === seasonIdx);
    }
    const cards = epInner.children;
    for (let i = 0; i < cards.length; i++) cards[i].classList.toggle('focused', zone === 'episodes' && i === epIdx);
    epInner.style.transform = `translateX(${-Math.max(0, epIdx - 2) * 420}px)`;
    el.classList.toggle('series-focus', zone !== 'buttons');
  }

  async function load() {
    setBackdrop(media.backdrop || '');
    busy(true);
    try {
      if (!session.provider) return;
      if (media.kind === 'series') {
        const r = await session.provider.seasons(media);
        info = r.info;
        seasons = r.seasons;
        // Kaldığı bölümün sezonunu aç
        const p = store.progress(session.pid, `series:${media.id}`);
        if (p && p.episode) {
          const si = seasons.findIndex((s) => s.num === p.episode!.season);
          if (si >= 0) {
            seasonIdx = si;
            epIdx = Math.max(0, seasons[si].episodes.findIndex((e) => e.id === p.episode!.id));
          }
        }
      } else {
        info = await session.provider.mediaInfo(media);
      }
    } catch (e) {
      toast(t('err_load', (e as Error).message), 5000);
    } finally {
      busy(false);
      loaded = true;
    }
    if (info && info.backdrop && !media.backdrop) setBackdrop(info.backdrop);
    if (info && info.poster && !media.poster) {
      posterBox.innerHTML = '';
      posterBox.appendChild(poster(info.poster, media.name));
    }
    fillMeta();
    fillSeasons();
    makeButtons();
    paint();
  }

  fillMeta();
  makeButtons();

  return {
    el,
    onShow() {
      if (!loaded) load();
      else {
        // Oynatıcıdan dönünce "Devam et" ve bölüm işaretleri güncellensin
        makeButtons();
        fillEpisodes();
        paint();
      }
    },
    onKey(key: Key): boolean {
      const hasSeries = media.kind === 'series' && seasons.length > 0;
      if (key === 'back') { back(); return true; }
      if (zone === 'buttons') {
        if (key === 'left' || key === 'right') btnIdx = Math.max(0, Math.min(buttons.length - 1, btnIdx + (key === 'left' ? -1 : 1)));
        else if (key === 'down' && hasSeries) zone = seasons.length > 1 ? 'seasons' : 'episodes';
        else if (key === 'ok' && buttons[btnIdx]) { buttons[btnIdx].run(); return true; }
      } else if (zone === 'seasons') {
        if (key === 'left' || key === 'right') {
          const n = Math.max(0, Math.min(seasons.length - 1, seasonIdx + (key === 'left' ? -1 : 1)));
          if (n !== seasonIdx) { seasonIdx = n; epIdx = 0; fillEpisodes(); }
        } else if (key === 'up') zone = 'buttons';
        else if (key === 'down' || key === 'ok') zone = 'episodes';
      } else {
        const eps = seasons[seasonIdx] ? seasons[seasonIdx].episodes : [];
        if (key === 'left' || key === 'right') epIdx = Math.max(0, Math.min(eps.length - 1, epIdx + (key === 'left' ? -1 : 1)));
        else if (key === 'up') zone = seasons.length > 1 ? 'seasons' : 'buttons';
        else if (key === 'ok' && eps[epIdx]) { playEpisode(eps[epIdx]); return true; }
      }
      paint();
      return true;
    },
  };
}
