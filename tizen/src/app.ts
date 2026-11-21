// Ekran yığını, tuş dağıtımı, bildirim ve yükleniyor göstergesi.
import { Key, keyOf } from './platform';

export interface Screen {
  el: HTMLElement;
  /** Alttaki ekranın üstünde açılan pencere (menü, PIN): alttaki ekran gizlenmez, durmaz. */
  overlay?: boolean;
  /** true dönerse tuş işlenmiş sayılır. */
  onKey(key: Key): boolean;
  /** Tuş bırakıldığında (basılı tutma algısı için). */
  onKeyUp?(key: Key): void;
  /** Ekran öne geldiğinde (ilk kez ya da üstündeki kapanınca). */
  onShow?(): void;
  /** Ekran arkada kaldığında ya da kapandığında. */
  onHide?(): void;
  /** Yığından tamamen çıkarıldığında. */
  onDestroy?(): void;
}

const stack: Screen[] = [];
const root = (): HTMLElement => document.getElementById('app') as HTMLElement;

function top(): Screen | undefined {
  return stack[stack.length - 1];
}

function hideTop() {
  const t = top();
  if (t) {
    if (t.onHide) t.onHide();
    t.el.remove();
    // Üst katman kapanırken altındaki (hep görünür kalmış) ekranlar etkilenmez;
    // normal bir ekran gizlenirken altındaki üst katmanlar zaten yığının üstünde değildir.
  }
}

function showTop() {
  const t = top();
  if (t) {
    root().appendChild(t.el);
    if (t.onShow) t.onShow();
  }
}

/** Yeni ekranı öne getirir; Geri ile öncekine dönülür. */
export function push(screen: Screen): void {
  if (!screen.overlay) hideTop();
  stack.push(screen);
  showTop();
}

/** Üstteki ekranı kapatır ve bir öncekine döner. */
export function pop(): void {
  if (stack.length <= 1) return;
  const s = stack[stack.length - 1];
  hideTop();
  stack.pop();
  if (s.onDestroy) s.onDestroy();
  if (!s.overlay) showTop();
}

/** Belirli bir üst katmanı kapatır (zaten kapandıysa bir şey yapmaz). */
export function close(screen: Screen): void {
  if (top() === screen) pop();
}

/** Yığını temizleyip tek ekranla başlar (giriş, çıkış). */
export function reset(screen: Screen): void {
  while (stack.length) {
    const s = stack.pop() as Screen;
    if (s.el.parentNode) {
      if (s.onHide) s.onHide();
      s.el.remove();
    }
    if (s.onDestroy) s.onDestroy();
  }
  stack.push(screen);
  showTop();
}

/** Şu an öndeki ekran (geç gelen yanıtlar yanlış ekranda pencere açmasın diye). */
export function topScreen(): Screen | undefined {
  return top();
}

export function depth(): number {
  return stack.length;
}

let toastTimer = 0;
export function toast(msg: string, ms = 3000): void {
  const el = document.getElementById('toast') as HTMLElement;
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => el.classList.remove('show'), ms);
}

let busyCount = 0;
export function busy(on: boolean): void {
  busyCount = Math.max(0, busyCount + (on ? 1 : -1));
  (document.getElementById('busy') as HTMLElement).classList.toggle('show', busyCount > 0);
}

export function isEditing(): boolean {
  const a = document.activeElement;
  return !!a && (a.tagName === 'INPUT' || a.tagName === 'TEXTAREA');
}

/** OK'a bu süreden uzun basılırsa 'okhold' (seçenekler menüsü) gönderilir. */
const HOLD_MS = 700;

export function initKeys(): void {
  // OK tuşu bırakılınca 'ok', basılı tutulunca bir kez 'okhold' olarak dağıtılır.
  // Basılıyken gelen tekrarlar yok sayılır (açılan menü kendiliğinden seçim yapmasın).
  let okDown = false;
  let okTimer = 0;
  let okFired = false;
  const dispatch = (key: Key, e?: Event) => {
    const t = top();
    if (t && t.onKey(key) && e) e.preventDefault();
  };

  document.addEventListener('keydown', (e) => {
    const editing = isEditing();
    const key = keyOf(e, editing);
    if (!key) return;
    // Yazı alanındayken yalnızca OK/Bitti/İptal/yukarı/aşağı bizim
    if (editing && ['ok', 'done', 'cancel', 'up', 'down', 'back'].indexOf(key) < 0) return;
    if (key === 'ok' && !editing) {
      e.preventDefault();
      if (okDown) return;
      okDown = true;
      okFired = false;
      okTimer = window.setTimeout(() => {
        okFired = true;
        dispatch('okhold');
      }, HOLD_MS);
      return;
    }
    dispatch(key, e);
  });
  document.addEventListener('keyup', (e) => {
    const key = keyOf(e, isEditing());
    if (key === 'ok' && okDown) {
      okDown = false;
      clearTimeout(okTimer);
      e.preventDefault();
      if (!okFired) dispatch('ok');
      return;
    }
    const t = top();
    if (key && t && t.onKeyUp) t.onKeyUp(key);
  });
  // Uygulama arka plana geçerse yarım kalan basış unutulsun
  window.addEventListener('blur', () => {
    okDown = false;
    clearTimeout(okTimer);
  });
}

/**
 * Tarayıcıda 1920x1080 sahneyi pencereye sığdırır.
 * TV'de ekran klavyesi açılınca pencere yüksekliği küçülür; sahne küçülüp kaymasın diye
 * TV'de yalnızca genişliğe bakılır ve yazı alanı düzenlenirken ölçek değiştirilmez.
 */
export function fitStage(tv: boolean): void {
  const stage = document.getElementById('stage') as HTMLElement;
  const fit = () => {
    if (isEditing()) return;
    const s = tv
      ? Math.max(window.innerWidth, screen.width || 0) / 1920
      : Math.min(window.innerWidth / 1920, window.innerHeight / 1080);
    stage.style.transform = Math.abs(s - 1) < 0.001 ? '' : `scale(${s})`;
  };
  window.addEventListener('resize', fit);
  // Klavye açılınca tarayıcı sayfayı kaydırmasın
  window.addEventListener('scroll', () => window.scrollTo(0, 0));
  fit();
}
