// Oturum: etkin hesap, sağlayıcı ve yüklenen listeler (bellekte önbellek).
import { M3uProvider } from './providers/m3u';
import { AccountInfo, Category, Channel, Media, Provider, Section } from './providers/types';
import { XtreamProvider, parseXtreamLink } from './providers/xtream';
import { Profile, store } from './store';

export function createProvider(p: Profile): Provider {
  if (p.type === 'xtream') return new XtreamProvider(p.url, p.username, p.password, store.settings().liveFormat);
  // get.php?username=..&password=.. biçimli M3U linkleri Xtream API ile daha zengin çalışır
  const x = parseXtreamLink(p.url);
  if (x) return new XtreamProvider(x.server, x.username, x.password, store.settings().liveFormat);
  return new M3uProvider(p.url);
}

class Session {
  profile: Profile | null = null;
  provider: Provider | null = null;
  account: AccountInfo | null = null;
  categories: Category[] = [];
  channels: Channel[] = [];
  favorites = new Set<string>();
  loaded = false;
  private mediaCats: Partial<Record<Section, Category[]>> = {};
  private mediaLists = new Map<string, Media[]>();

  start(p: Profile, provider: Provider, account: AccountInfo | null): void {
    this.profile = p;
    this.provider = provider;
    this.account = account;
    this.loaded = false;
    this.mediaCats = {};
    this.mediaLists.clear();
    this.favorites = new Set(store.favorites(p.id));
  }

  get pid(): string {
    return this.profile ? this.profile.id : '';
  }

  async loadLive(): Promise<void> {
    if (!this.provider || this.loaded) return;
    const [cats, chans] = await Promise.all([this.provider.liveCategories(), this.provider.liveChannels()]);
    this.categories = cats;
    this.channels = chans;
    this.loaded = true;
  }

  async mediaCategories(section: Section): Promise<Category[]> {
    const c = this.mediaCats[section];
    if (c) return c;
    const cats = this.provider ? await this.provider.mediaCategories(section) : [];
    this.mediaCats[section] = cats;
    return cats;
  }

  async mediaItems(section: Section, categoryId: string): Promise<Media[]> {
    const key = `${section}|${categoryId}`;
    const c = this.mediaLists.get(key);
    if (c) return c;
    const items = this.provider ? await this.provider.mediaItems(section, categoryId) : [];
    // Bellek sınırlı: en fazla 12 liste önbellekte
    if (this.mediaLists.size >= 12) {
      const firstKey = this.mediaLists.keys().next().value;
      if (firstKey !== undefined) this.mediaLists.delete(firstKey);
    }
    this.mediaLists.set(key, items);
    return items;
  }

  toggleFavorite(ch: Channel): boolean {
    if (!this.profile) return false;
    const on = !this.favorites.has(ch.id);
    if (on) this.favorites.add(ch.id);
    else this.favorites.delete(ch.id);
    store.setFavorites(this.profile.id, Array.from(this.favorites));
    return on;
  }

  logout(): void {
    this.profile = null;
    this.provider = null;
    this.account = null;
    this.categories = [];
    this.channels = [];
    this.loaded = false;
    this.mediaCats = {};
    this.mediaLists.clear();
    store.setProfile(null);
  }
}

export const session = new Session();
