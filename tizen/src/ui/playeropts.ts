// Oynatıcı seçenekleri: ses parçası, altyazı, görüntü oranı.
import { toast } from '../app';
import { t } from '../i18n';
import { Aspect, player } from '../player';
import { MenuItem, showMenu } from './menu';

let subsOn = false;

export function audioMenu(): void {
  const tracks = player.tracks().filter((x) => x.type === 'audio');
  if (tracks.length < 2) { toast(tracks.length ? t('only_one_audio') : t('no_audio_tracks')); return; }
  showMenu(t('audio_track'), tracks.map((tr) => ({
    label: tr.label, checked: tr.selected, run: () => player.selectTrack('audio', tr.index),
  })));
}

export function subtitleMenu(): void {
  const tracks = player.tracks().filter((x) => x.type === 'text');
  if (!tracks.length) { toast(t('no_subtitles')); return; }
  const items: MenuItem[] = [{ label: t('off'), checked: !subsOn, run: () => { subsOn = false; player.setSubtitles(false); } }];
  tracks.forEach((tr) => items.push({
    label: tr.label, checked: subsOn && tr.selected, run: () => { subsOn = true; player.selectTrack('text', tr.index); },
  }));
  showMenu(t('subtitles'), items);
}

export function aspectMenu(): void {
  const opts: [Aspect, string][] = [['auto', t('aspect_auto')], ['stretch', t('aspect_stretch')]];
  showMenu(t('aspect'), opts.map(([v, label]) => ({ label, checked: player.aspect === v, run: () => player.setAspect(v) })));
}

/** Tek menüde tüm oynatıcı seçenekleri; extra en üste eklenir. */
export function playerMenu(extra: MenuItem[] = []): void {
  showMenu(t('options'), extra.concat([
    { label: t('audio_track'), run: audioMenu },
    { label: t('subtitles'), run: subtitleMenu },
    { label: t('aspect'), run: aspectMenu },
  ]), 0);
}

/** Yeni yayında altyazı kapalı başlar. */
export function resetSubtitles(): void {
  subsOn = false;
}
