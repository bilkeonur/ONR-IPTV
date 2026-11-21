# ONR IPTV — Samsung Smart TV (Tizen)

Samsung televizyonlar (Tizen 5.5+, 2020 ve sonrası modeller) için ONR IPTV.
HTML + TypeScript ile yazılmış bir Tizen web uygulamasıdır. Videolar Samsung'un
donanım hızlandırmalı **AVPlay** oynatıcısıyla oynatılır.

**Bu sürümde:** Xtream Codes, M3U (isteğe bağlı XMLTV rehberi) ve Stalker portal; birden çok profil;
canlı TV (kategoriler, favoriler, son izlenenler, sıralama, içerik dili filtresi, kanal numarasıyla geçiş,
yayın koparsa yeniden bağlanma); TV rehberi ve kanal yayın akışı; geçmiş yayın (catch-up, Xtream);
filmler ve diziler (favoriler, son izlenenler, izlendi işaretleri, kaldığı yerden devam, sıralama, dil filtresi);
kanal, film ve dizilerde genel arama; ebeveyn kilidi (PIN, yetişkin kategorileri, kategori ve içerik kilidi);
kategori gizleme; ses parçası, altyazı ve görüntü oranı seçimi; TR/EN dil desteği.
İndirme, kayıt, çoklu ekran ve Chromecast yalnızca masaüstü sürümdedir.

Kumanda: **Yeşil** favori, **Sarı** seçenekler menüsü (sıralama, dil, kilit, ses/altyazı), **Mavi** arama,
**Kırmızı** TV rehberi, **Bilgi** kanalın yayın akışı.

## Tarayıcıda geliştirme

```bash
cd tizen
npm install
npm run fake-server     # sahte sunucu: http://localhost:8765 — Xtream test/test, Stalker portal (aynı adres, herhangi bir 00:1A:79 MAC), M3U + XMLTV: /get.php?username=test&password=test
npm run dev             # http://localhost:5173
```

Kumanda tuşları klavyede şöyle karşılanır: oklar, Enter = OK, Esc/Backspace = Geri,
PgUp/PgDn = CH +/-, F1–F4 = Kırmızı/Yeşil/Sarı/Mavi, Boşluk = Oynat/Duraklat, I = Bilgi.
Tarayıcıda HTML5 video kullanılır (`.ts` canlı yayınlar tarayıcıda oynamaz, TV'de oynar).

## Televizyona kurulum (kendi kullanımın için)

1. **Tizen Studio**'yu kur (`C:\tizen-studio`). Package Manager'da şunları ekle:
   *Tizen SDK tools*, *Extension SDK → Samsung Certificate Extension* ve *TV Extensions*.
2. **TV'de geliştirici modu:** Uygulamalar → en alttaki **Uygulama Ayarları** ekranında `1 2 3 4 5` gir
   (rakam tuşu olmayan kumandalarda telefondaki SmartThings sanal kumandasının 123 tuş takımıyla).
   *Developer mode* = **On**, *Host PC IP* = bilgisayarının IP adresi, OK, sonra TV'yi tamamen
   yeniden başlat (güç tuşuna basılı tut). Durum: `http://<TV-IP>:8001/api/v2/` → `developerMode`.
3. **Sertifika:** Tizen Studio → Tools → Certificate Manager → `+` → **Samsung** →
   TV → profil adı `onriptv` → Samsung hesabıyla giriş. Distributor sertifikasına
   TV'nin DUID'sini eklemek için TV'nin bağlı olması gerekir (adım 4'ten sonra yapılabilir).
4. Paketle, kur ve başlat:

```bash
npm run tv -- 192.168.1.50      # TV'nin IP adresi
```

Yalnızca paket üretmek için `npm run package` (çıktı: `build/ONRIPTV.wgt`).

## Mağaza

Samsung Apps TV mağazası için Samsung Seller Office'te başvuru yapılır. İncelemeye
bir demo hesap gerekir; `scripts/fake_xtream.py` türünde herkese açık bir test sunucusu kullanılabilir.

## Bilinen tuzaklar

- **Türkçe Windows:** Tizen CLI `os.name`'i yerel ayarla büyük harfe çevirip Windows'u tanımıyor
  (`NullPointerException`, `SigningProfile.java:265`). `scripts/tv.mjs` CLI'yi
  `JAVA_TOOL_OPTIONS=-Duser.language=en` ile çalıştırır; elle çalıştırırken de bunu ayarla.
- **Paket kimliği tam 10 karakter olmalı** (`OnrIptvTv1`); değilse kurulum
  `install failed[118, -4] Load archive info fail` verir.
