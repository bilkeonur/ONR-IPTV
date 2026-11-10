// Arayüz metinleri (TR + EN). {0}, {1} yer tutucularıdır.
const STRINGS = {
  login_title: ['Hesap ekle', 'Add account'],
  login_hint: ['IPTV sağlayıcınızın bilgilerini girin. Bilgiler yalnızca bu televizyonda saklanır.',
    'Enter your IPTV provider details. They are stored only on this TV.'],
  type_xtream: ['Xtream Codes', 'Xtream Codes'],
  type_m3u: ['M3U listesi', 'M3U playlist'],
  field_name: ['Hesap adı', 'Account name'],
  field_server: ['Sunucu adresi', 'Server URL'],
  field_username: ['Kullanıcı adı', 'Username'],
  field_password: ['Şifre', 'Password'],
  field_m3u: ['M3U adresi', 'M3U URL'],
  connect: ['Bağlan', 'Connect'],
  connecting: ['Bağlanıyor…', 'Connecting…'],
  required: ['Lütfen tüm alanları doldurun', 'Please fill in all fields'],

  tile_live: ['Canlı TV', 'Live TV'],
  tile_movies: ['Filmler', 'Movies'],
  tile_series: ['Diziler', 'Series'],
  tile_settings: ['Ayarlar', 'Settings'],
  sub_live: ['Kanallar ve yayın akışı', 'Channels and programme guide'],
  sub_movies: ['Sinema arşivi', 'Film library'],
  sub_series: ['Sezonlar ve bölümler', 'Seasons and episodes'],
  continue_watching: ['İzlemeye devam et', 'Continue watching'],
  hold_to_remove: ['Kaldırmak için OK tuşuna basılı tutun', 'Hold OK to remove'],
  removed_from_list: ['Listeden kaldırıldı', 'Removed from the list'],
  expires_on: ['Bitiş: {0}', 'Expires: {0}'],

  cat_all: ['Tümü', 'All'],
  cat_all_channels: ['Tüm kanallar', 'All channels'],
  cat_favorites: ['Favoriler', 'Favourites'],
  cat_other: ['Diğer', 'Other'],
  categories: ['Kategoriler', 'Categories'],
  channels_n: ['{0} kanal', '{0} channels'],
  items_n: ['{0} içerik', '{0} titles'],
  no_channels: ['Bu kategoride kanal yok', 'No channels in this category'],
  no_items: ['Bu kategoride içerik yok', 'Nothing in this category'],
  no_epg: ['Yayın akışı bilgisi yok', 'No programme information'],
  now: ['Şimdi', 'Now'],
  next: ['Sonra', 'Next'],
  loading: ['Yükleniyor…', 'Loading…'],
  fav_added: ['Favorilere eklendi', 'Added to favourites'],
  fav_removed: ['Favorilerden çıkarıldı', 'Removed from favourites'],
  press_back_exit: ['Çıkmak için tekrar Geri tuşuna basın', 'Press Back again to exit'],
  hint_list: ['OK: izle   ◀: kategoriler   Yeşil: favori   Geri: ana ekran',
    'OK: watch   ◀: categories   Green: favourite   Back: home'],
  hint_live: ['OK: kanal listesi   ▲▼ / CH: kanal değiştir   Bilgi: program',
    'OK: channel list   ▲▼ / CH: change channel   Info: programme'],

  play: ['Oynat', 'Play'],
  resume_at: ['Devam et · {0}', 'Resume · {0}'],
  restart: ['Baştan başla', 'Start over'],
  season_n: ['{0}. Sezon', 'Season {0}'],
  episode_n: ['{0}. Bölüm', 'Episode {0}'],
  episodes: ['Bölümler', 'Episodes'],
  se_short: ['S{0} B{1}', 'S{0} E{1}'],
  seasons_n: ['{0} sezon', '{0} seasons'],
  cast: ['Oyuncular', 'Cast'],
  director: ['Yönetmen', 'Director'],
  genre: ['Tür', 'Genre'],
  no_plot: ['Açıklama yok', 'No description'],
  hint_vod: ['OK: duraklat   ◀ ▶: 10 sn   ◀◀ ▶▶: 1 dk   Geri: çık',
    'OK: pause   ◀ ▶: 10 s   ◀◀ ▶▶: 1 min   Back: exit'],
  next_episode: ['Sıradaki bölüm', 'Next episode'],

  settings_title: ['Ayarlar', 'Settings'],
  set_language: ['Dil', 'Language'],
  set_live_format: ['Canlı yayın biçimi', 'Live stream format'],
  set_account: ['Hesap', 'Account'],
  set_logout: ['Hesaptan çık', 'Sign out'],
  set_version: ['Sürüm', 'Version'],
  acc_status: ['Durum', 'Status'],
  acc_expires: ['Bitiş', 'Expires'],
  acc_connections: ['Bağlantı', 'Connections'],
  unlimited: ['Sınırsız', 'Unlimited'],
  lang_system: ['Sistem', 'System'],
  confirm_logout: ['Çıkmak için OK tuşuna tekrar basın', 'Press OK again to sign out'],

  err_connect: ['Sunucuya bağlanılamadı ({0})', 'Could not connect to the server ({0})'],
  err_http: ['Sunucu hata döndürdü (HTTP {0})', 'The server returned an error (HTTP {0})'],
  err_unauthorized: ['Kullanıcı adı veya şifre hatalı', 'Wrong username or password'],
  err_not_xtream: ['Bu adres bir Xtream Codes sunucusu değil', 'This is not an Xtream Codes server'],
  err_not_m3u: ['Geçerli bir M3U listesi değil', 'Not a valid M3U playlist'],
  err_play: ['Yayın açılamadı', 'Could not play the stream'],
  err_load: ['Liste yüklenemedi: {0}', 'Could not load the list: {0}'],
} as const;

export type StrKey = keyof typeof STRINGS;

let idx = 0;

export function setLang(lang: string): void {
  const l = lang || (navigator.language || 'en').slice(0, 2).toLowerCase();
  idx = l === 'tr' ? 0 : 1;
  document.documentElement.lang = idx === 0 ? 'tr' : 'en';
}

export function currentLang(): 'tr' | 'en' {
  return idx === 0 ? 'tr' : 'en';
}

export function t(key: StrKey, ...args: (string | number)[]): string {
  let s: string = STRINGS[key][idx];
  args.forEach((a, i) => { s = s.replace(`{${i}}`, String(a)); });
  return s;
}
