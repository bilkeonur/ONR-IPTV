// Oturum: etkin hesap, sağlayıcı, yüklenen listeler (bellekte önbellek) ve kullanıcı verisi.
import { ADULT_RE } from './lib';
import { M3uProvider } from './providers/m3u';
import { StalkerProvider } from './providers/stalker';
import { AccountInfo, AnySection, Category, Channel, Media, Provider, Section } from './providers/types';
import { XtreamProvider, parseXtreamLink } from './providers/xtream';
import { HistoryEntry, Profile, ProfileSettings, UserData, slim, slimChannel, store } from './store';

export function createProvider(p: Profile): Provider {
  const fmt = store.settings().liveFormat;
  if (p.type === 'xtream') return new XtreamProvider(p.url, p.username, p.password, fmt);
  if (p.type === 'stalker') return new StalkerProvider(p.url, p.mac || '');
  // get.php?username=..&password=.. biçimli M3U linkleri Xtream API ile daha zengin çalışır
  const x = parseXtreamLink(p.url);
  if (x && !p.epgUrl) return new XtreamProvider(x.server, x.username, x.password, fmt);
  return new M3uProvider(p.url, p.epgUrl || '');
}

/** PIN girildikten sonra korumalı içerik bu süre açık kalır. */
const UNLOCK_MS = 5 * 60000;

class Session {
  profile: Profile | null = null;
  provider: Provider | null = null;
  account: AccountInfo | null = null;
  categories: Category[] = [];
  channels: Channel[] = [];
  loaded = false;
  user: UserData = store.user('');
  pset: ProfileSettings = store.profileSettings('');
  private unlockedAt = 0;
  private mediaCats: Partial<Record<Section, Category[]>> = {};
  private mediaLists = new Map<string, Media[]>();
  /** Sayfalı bölümlerde görülen tüm öğeler (arama için) */
  private seen: Record<Section, Map<string, Media>> = { movie: new Map(), series: new Map() };
  private liveLoading: Promise<void> | null = null;

  start(p: Profile, provider: Provider, account: AccountInfo | null): void {
    this.profile = p;
    this.provider = provider;
    this.account = account;
    this.clearLists();
    this.user = store.user(p.id);
    this.pset = store.profileSettings(p.id);
    this.unlockedAt = 0;
    store.setActive(p.id);
  }

  private clearLists(): void {
    this.categories = [];
    this.channels = [];
    this.loaded = false;
    this.liveLoading = null;
    this.mediaCats = {};
    this.mediaLists.clear();
    this.seen = { movie: new Map(), series: new Map() };
  }

  /** Listeleri sunucudan yeniden yükletir. */
  refresh(): void {
    if (!this.profile) return;
    this.provider = createProvider(this.profile);
    this.clearLists();
  }

  get pid(): string {
    return this.profile ? this.profile.id : '';
  }

  // ---- Listeler
  loadLive(): Promise<void> {
    if (!this.provider || this.loaded) return Promise.resolve();
    if (!this.liveLoading) {
      const prov = this.provider;
      this.liveLoading = Promise.all([prov.liveCategories(), prov.liveChannels()]).then(([cats, chans]) => {
        if (prov !== this.provider) return;
        this.categories = cats;
        this.channels = chans;
        this.loaded = true;
      }).finally(() => { this.liveLoading = null; });
    }
    return this.liveLoading;
  }

  async mediaCategories(section: Section): Promise<Category[]> {
    const c = this.mediaCats[section];
    if (c) return c;
    const cats = this.provider ? await this.provider.mediaCategories(section) : [];
    this.mediaCats[section] = cats;
    return cats;
  }

  /** Bilinen kategori adları (dil filtresi ve yetişkin algılama için). */
  catNames(section: AnySection): Record<string, string> {
    const out: Record<string, string> = {};
    const cats = section === 'live' ? this.categories : this.mediaCats[section] || [];
    cats.forEach((c) => { out[c.id] = c.name; });
    return out;
  }

  isPaged(section: Section): boolean {
    return !!this.provider && this.provider.paged.indexOf(section) >= 0;
  }

  async mediaItems(section: Section, categoryId: string): Promise<Media[]> {
    const key = `${section}|${categoryId}`;
    const c = this.mediaLists.get(key);
    if (c) return c;
    const items = this.provider ? await this.provider.mediaItems(section, categoryId) : [];
    this.remember(section, items);
    // Bellek sınırlı: en fazla 12 liste önbellekte ("Tümü" listesi arama için hep kalır)
    if (this.mediaLists.size >= 12) {
      const k = Array.from(this.mediaLists.keys()).find((x) => !/\|$/.test(x));
      if (k !== undefined) this.mediaLists.delete(k);
    }
    this.mediaLists.set(key, items);
    return items;
  }

  /** Sayfalı bölümler için tek sayfa. */
  async mediaPage(section: Section, categoryId: string, page: number): Promise<{ items: Media[]; pages: number }> {
    if (!this.provider || !this.provider.mediaPage) return { items: await this.mediaItems(section, categoryId), pages: 1 };
    const r = await this.provider.mediaPage(section, categoryId, page);
    this.remember(section, r.items);
    return r;
  }

  private remember(section: Section, items: Media[]): void {
    if (!this.isPaged(section)) return;
    const m = this.seen[section];
    items.forEach((i) => m.set(i.id, i));
  }

  /** Arama için bölümdeki tüm içerik (sayfalı bölümlerde yalnızca açılmış sayfalar). */
  async searchable(section: Section): Promise<Media[]> {
    if (this.isPaged(section)) return Array.from(this.seen[section].values());
    return this.mediaItems(section, '');
  }

  // ---- Kullanıcı verisi
  private saveUser(): void {
    if (this.profile) store.saveUser(this.profile.id, this.user);
  }

  isFavorite(section: AnySection, id: string): boolean {
    return this.user.fav[section].indexOf(id) >= 0;
  }

  /** Favoriye ekler/çıkarır; yeni durumu döndürür. */
  toggleFavorite(section: AnySection, item: Channel | Media): boolean {
    const list = this.user.fav[section];
    const i = list.indexOf(item.id);
    const meta = this.user.favMeta[section] as Record<string, Channel | Media>;
    if (i >= 0) {
      list.splice(i, 1);
      delete meta[item.id];
    } else {
      list.push(item.id);
      meta[item.id] = section === 'live' ? slimChannel(item as Channel) : slim(item as Media);
    }
    this.saveUser();
    return i < 0;
  }

  favoriteChannels(): Channel[] {
    const by = new Map(this.channels.map((c) => [c.id, c] as [string, Channel]));
    return this.user.fav.live.map((id) => by.get(id) || this.user.favMeta.live[id]).filter((c): c is Channel => !!c);
  }

  favoriteMedia(section: Section): Media[] {
    const meta = this.user.favMeta[section];
    return this.user.fav[section].map((id) => meta[id]).filter((m): m is Media => !!m);
  }

  /** Yetişkin içerik mi: adı ya da kategorisinin adı yetişkin kalıbına uyuyor. */
  isAdult(section: AnySection, item: { name: string; categoryId: string }): boolean {
    if (ADULT_RE.test(item.name || '')) return true;
    const cat = this.catNames(section)[item.categoryId];
    return !!cat && ADULT_RE.test(cat);
  }

  /** Yetişkin kategoriler (aramada ve "son izlenen" listelerinde hiç gösterilmez). */
  adultCats(cats: Category[]): Set<string> {
    return new Set(cats.filter((c) => ADULT_RE.test(c.name || '')).map((c) => c.id));
  }

  addHistory(section: AnySection, item: Channel | Media): void {
    // Yetişkin içerik "son izlenen"e girmez
    if (this.isAdult(section, item)) return;
    const e: HistoryEntry = { kind: section, id: item.id, at: Date.now() };
    if (section === 'live') e.ch = slimChannel(item as Channel);
    else e.media = slim(item as Media);
    this.user.history = [e].concat(this.user.history.filter((h) => !(h.kind === section && h.id === item.id)));
    this.saveUser();
  }

  removeHistory(section: AnySection, id: string): void {
    this.user.history = this.user.history.filter((h) => !(h.kind === section && h.id === id));
    this.saveUser();
  }

  clearHistory(section: AnySection): void {
    this.user.history = this.user.history.filter((h) => h.kind !== section);
    this.saveUser();
  }

  recentChannels(): Channel[] {
    const by = new Map(this.channels.map((c) => [c.id, c] as [string, Channel]));
    return this.user.history.filter((h) => h.kind === 'live' && h.ch).map((h) => by.get(h.id) || (h.ch as Channel))
      .filter((c) => !this.isAdult('live', c));
  }

  recentMedia(section: Section): Media[] {
    return this.user.history.filter((h) => h.kind === section && h.media).map((h) => h.media as Media)
      .filter((m) => !this.isAdult(section, m));
  }

  isWatched(key: string): boolean {
    return !!this.user.watched[key];
  }

  setWatched(key: string): void {
    this.user.watched[key] = Date.now();
    this.saveUser();
  }

  // ---- Kategori gizleme ve ebeveyn kilidi
  private savePset(): void {
    if (this.profile) store.saveProfileSettings(this.profile.id, this.pset);
  }

  hidden(section: AnySection): Set<string> {
    return new Set(this.pset.hidden[section]);
  }

  setHidden(section: AnySection, ids: string[]): void {
    this.pset.hidden[section] = ids;
    this.savePset();
  }

  lockedCats(section: AnySection): Set<string> {
    return new Set(this.pset.locks[section].cats);
  }

  setLockedCats(section: AnySection, ids: string[]): void {
    this.pset.locks[section].cats = ids;
    this.savePset();
  }

  pinSet(): boolean {
    return !!store.settings().pin;
  }

  /** Kategori PIN korumalı mı (elle kilitlenmiş ya da yetişkin kilidi). */
  isCatLocked(section: AnySection, cat: Category | undefined): boolean {
    if (!cat || !this.pinSet()) return false;
    if (this.pset.locks[section].cats.indexOf(cat.id) >= 0) return true;
    return store.settings().lockAdult && ADULT_RE.test(cat.name || '');
  }

  isItemLocked(section: AnySection, item: { id: string; categoryId: string } | undefined): boolean {
    if (!item || !this.pinSet()) return false;
    const lk = this.pset.locks[section];
    if (lk.items.indexOf(item.id) >= 0 || lk.cats.indexOf(item.categoryId) >= 0) return true;
    const name = this.catNames(section)[item.categoryId];
    return !!name && store.settings().lockAdult && ADULT_RE.test(name);
  }

  isItemSelfLocked(section: AnySection, id: string): boolean {
    return this.pset.locks[section].items.indexOf(id) >= 0;
  }

  toggleItemLock(section: AnySection, id: string): boolean {
    const lk = this.pset.locks[section];
    const i = lk.items.indexOf(id);
    if (i >= 0) lk.items.splice(i, 1);
    else lk.items.push(id);
    this.savePset();
    return i < 0;
  }

  /** "Tümü" listelerinden çıkarılacak kategoriler: gizli + (PIN varsa) yetişkin. */
  excludedCats(section: AnySection, cats: Category[]): Set<string> {
    const out = this.hidden(section);
    if (this.pinSet() && store.settings().lockAdult) cats.forEach((c) => { if (ADULT_RE.test(c.name)) out.add(c.id); });
    return out;
  }

  get unlocked(): boolean {
    return Date.now() - this.unlockedAt < UNLOCK_MS;
  }

  markUnlocked(): void {
    this.unlockedAt = Date.now();
  }

  logout(): void {
    this.profile = null;
    this.provider = null;
    this.account = null;
    this.clearLists();
  }
}

export const session = new Session();
