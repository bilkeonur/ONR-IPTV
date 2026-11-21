import { busy, fitStage, initKeys } from './app';
import { setLang } from './i18n';
import { register, restart } from './nav';
import { isTizen, registerKeys } from './platform';
import { player } from './player';
import { catPickerScreen } from './screens/catpicker';
import { detailScreen } from './screens/detail';
import { guideScreen } from './screens/guide';
import { homeScreen } from './screens/home';
import { liveScreen } from './screens/live';
import { loginScreen } from './screens/login';
import { profilesScreen } from './screens/profiles';
import { searchScreen } from './screens/search';
import { settingsScreen } from './screens/settings';
import { vodScreen } from './screens/vod';
import { vodPlayerScreen } from './screens/vodplayer';
import { createProvider, session } from './session';
import { store } from './store';

register('login', loginScreen);
register('live', liveScreen);
register('settings', settingsScreen);
register('home', homeScreen);
register('vod', vodScreen);
register('detail', detailScreen);
register('play', vodPlayerScreen);
register('search', searchScreen);
register('guide', guideScreen);
register('profiles', profilesScreen);
register('catpicker', catPickerScreen);

async function start() {
  document.documentElement.classList.add(isTizen ? 'tizen' : 'browser');
  setLang(store.settings().lang);
  fitStage(isTizen);
  registerKeys();
  initKeys();

  // Arka plana geçince yayını durdur, dönünce sürdür
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) player.suspend();
    else player.restore();
  });

  const p = store.profile();
  if (!p) {
    restart('login');
    return;
  }
  // Kayıtlı hesapla doğrudan aç; hesap bilgisi arka planda tazelenir
  const provider = createProvider(p);
  session.start(p, provider, null);
  restart('home');
  busy(true);
  provider.authenticate()
    .then((a) => { session.account = a; })
    .catch(() => { /* liste yüklenirken hata gösterilir */ })
    .then(() => busy(false));
}

start();
