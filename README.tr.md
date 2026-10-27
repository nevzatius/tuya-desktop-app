# Tuya Desktop App

[English](README.md) · **Türkçe**

[![Testler](https://github.com/nevzatius/tuya-desktop-app/actions/workflows/ci.yml/badge.svg)](https://github.com/nevzatius/tuya-desktop-app/actions/workflows/ci.yml)
[![Lisans: MIT](https://img.shields.io/github/license/nevzatius/tuya-desktop-app)](LICENSE)
[![Son sürüm](https://img.shields.io/github/v/release/nevzatius/tuya-desktop-app?include_prereleases)](https://github.com/nevzatius/tuya-desktop-app/releases)

Tuya / Smart Life ışıklarınızı Windows bilgisayarınızdan Bluetooth ile kontrol edin; kurulumdan sonra bulut da internet de gerekmez.

> **Resmi olmayan bir projedir.** Tuya Inc. ile bağlantısı, onayı ya da ortaklığı yoktur. "Tuya" ve "Smart Life" ilgili sahiplerinin ticari markalarıdır. Yazılım olduğu gibi sunulur ([LICENSE](LICENSE)).

<p align="center">
  <img src="docs/screenshots/tr/home.png" width="230" alt="Ana ekran: güç düğmesi, parlaklık ve beyaz ışık sıcaklığı">
  <img src="docs/screenshots/tr/color.png" width="230" alt="Renk çarkıyla renk modu">
  <img src="docs/screenshots/tr/energy.png" width="230" alt="Tahmini tüketim ve maliyeti gösteren enerji sekmesi">
</p>

## Hızlı başlangıç

1. [Sürümler](https://github.com/nevzatius/tuya-desktop-app/releases) sayfasından `TuyaDesktopApp-Setup-<sürüm>.exe` dosyasını **indirin**.
2. **Çalıştırın.** Windows SmartScreen "Windows bilgisayarınızı korudu" derse **Ek bilgi → Yine de çalıştır** deyin. Bu uyarı, uygulama henüz kod imzalı olmadığı için çıkar (imza sertifikası ücretlidir); bir sorun olduğu anlamına gelmez.
3. **İlk açılış sihirbazını izleyin** ve ışığınızı bağlayın. Yaklaşık 10 dakika sürer ve yalnızca bir kez yapılır.

> ### Anahtar neden gerekir?
> Bir Tuya ışığı yalnızca **yerel anahtarını** bilen cihazlarla konuşur ve bu anahtarı yalnızca ışığın bağlı olduğu Tuya hesabı verebilir. Sihirbaz, bu anahtarı kendi ücretsiz Tuya geliştirici hesabınızdan adım adım almanızı sağlar. Bunu **bir kez** yaparsınız; sonrasında uygulama ışıkla doğrudan Bluetooth üzerinden konuşur ve **internetsiz** çalışır. Atlamayın: anahtar olmadan ışık kontrol edilemez.

<p align="center">
  <img src="docs/screenshots/tr/wizard-keys.png" width="300" alt="Kurulum sihirbazı 3. adım: canlı doğrulamalı Access ID ve Secret">
  <img src="docs/screenshots/tr/wizard-lights.png" width="300" alt="Kurulum sihirbazı 4. adım: ışıkları seç ve adlandır">
</p>

## Özellikler

- Açma/kapama, parlaklık, beyaz ışık sıcaklığı, renk ve altı hazır ayar (Okuma, Odak, Gece, Film, Romantik, Okyanus).
- Birden çok ışık; başlıktaki menüden değiştirme, yeniden adlandırma, kaldırma.
- Sistem tepsisi: pencereyi kapatınca uygulama çalışmaya devam eder; tepsiden ışığı açıp kapatabilirsiniz. Bağlantı koparsa kendiliğinden yeniden bağlanır.
- Pano algılama, canlı doğrulama ve "Tekrar dene" düğmeleriyle yönlendirmeli kurulum sihirbazı.
- Çevredeki ışıkları sinyal gücüyle tarama ve ışıkları ayırt etmek için **Yanıp söndür** düğmesi (deneysel, bkz. [Durum](#durum)).
- "Işık bulunamadı" için sorun giderici kart ve sorun bildirirken yapıştırabileceğiniz tanılama raporu.
- **Tahmini** enerji tüketimi ve maliyeti: günlük, haftalık, aylık.
- Türkçe ve İngilizce arayüz (dil ⚙ menüsünde; varsayılan sistem dili).
- Başlat menüsü kısayolu, isteğe bağlı masaüstü kısayolu ve isteğe bağlı "Windows ile başlat" (tepside açılır) seçenekleriyle Windows yükleyicisi.

## Nasıl çalışır?

```mermaid
flowchart LR
    A["Tuya hesabınız<br/>(yalnızca bir kez)"] -- "yerel anahtar" --> B["Tuya Desktop App"]
    B -- "Bluetooth LE<br/>(internetsiz)" --> C["Işığınız"]
```

Kurulum sihirbazı, ışığınızın yerel anahtarını kendi Tuya Cloud projenizden bir kez alır. Sonrasında uygulama ışığı Bluetooth ile bulur, bu anahtarla Tuya BLE el sıkışmasını yapar ve komutları doğrudan gönderir. Bu projenin hiçbir sunucusuna veri gitmez.

## Durum

Gerçek cihazla nelerin denendiğinin, nelerin denenmediğinin dürüst özeti:

| Alan | Durum |
|---|---|
| Bluetooth bağlantısı ve el sıkışma | Gerçek bir ışıkla (Tuya `dj` kategorisi, YX-ZNLD9) v0.2.0 ile **doğrulandı** |
| Komutlar (aç/kapat, parlaklık, renk, hazır ayarlar), arayüz, enerji tahmini | Otomatik testlerle sınandı; gerçek ışıkta uçtan uca doğrulama sürüyor |
| Kurulum sihirbazı v2 (pano algılama, yakın tarama) | Yalnızca otomatik testler — **gerçek cihazda henüz doğrulanmadı** |
| **Yanıp söndür** düğmesi (ışığı tanıma) | Deneysel — **gerçek cihazda henüz doğrulanmadı** |
| **Sorun giderici** kart ve tanılama raporu | Deneysel — **gerçek cihazda henüz doğrulanmadı** (raporun gizlilik filtresi testlerle sınandı) |
| Windows yükleyicisi ve taşınabilir zip | Derleme betikleri ve release iş akışı yazıldı; **geliştirici tarafından henüz derlenip denenmedi** |
| İngilizce arayüz | Otomatik testler ve üretilen ekran görüntüleri; İngilizce Windows'ta henüz gözden geçirilmedi |
| Windows 10/11 | Birincil hedef; arayüz gerçek Windows kurulumlarında henüz geniş denenmedi |
| macOS / Linux | Çalışması beklenir (Qt + bleak), **denenmedi** |
| Wi-Fi (yerel ağ) kontrolü | **Henüz yok** (planlı) |

## Desteklenen cihazlar

| Cihaz | Durum |
|---|---|
| YX-ZNLD9 (Tuya `dj` kategorisi) | **Denendi**: Bluetooth bağlantısı ve el sıkışma doğrulandı |
| Diğer standart `dj` ışıkları (v2 komut seti: `switch_led`=20, `work_mode`=21, `bright_value_v2`=22, `temp_value_v2`=23, `colour_data_v2`=24) | Çalışması **beklenir**, denenmedi |
| Diğer ışık kategorileri (`dd`, `xdd`, `fwd`, `dc`, `tgq`, `tyndj`, `fsd`) | "Deneysel" olarak listelenir; farklı komutlar kullanabilir |
| Yalnızca Wi-Fi'lı cihazlar, prizler, diğer Tuya cihaz türleri | Desteklenmiyor |

**Topluluk raporları bekleniyor.** Işığınızla denediniz mi? Lütfen bir [cihaz raporu](https://github.com/nevzatius/tuya-desktop-app/issues/new?template=device_report.yml) açın (model, kategori, neyin çalıştığı) ve tanılama raporunu (⚙ → *Tanılama raporunu kopyala*) yapıştırın. Anahtar, kimlik ya da adres içermez.

## Enerji tahmini: ne söyler, ne söylemez

Işıklar güç ölçmez. Uygulama şunu tahmin eder: *anma gücü (W) × parlaklık × açık kalma süresi*.

- Kullanım **yalnızca uygulama açıkken ve ışığa bağlıyken** kaydedilir. Uygulama kapalıyken ya da bağlantı kesikken telefonla veya duvar anahtarıyla yapılan değişiklikler görülmez; bu yüzden değerler gerçeğin alt sınırına yakındır.
- Işığın anma gücünü (ambalajında yazar, ör. 9 W) ve faturanızdaki elektrik birim fiyatını girin.
- Türkçe arayüz: varsayılan fiyat EPDK mesken tarifesidir (Nisan 2026) ve para birimi liradır; kendi faturanıza bakın, tarifeler değişir. İngilizce arayüz: fiyat **boş** başlar ve para birimini siz seçersiniz (varsayılan sistem bölgenize uyar).
- Kayıtlar yerel olarak, anahtarlarınızın yanındaki `energy.db` dosyasında tutulur.

## Gizlilik ve güvenlik

- Işıklarınızın yerel anahtarları **yalnızca bu bilgisayarda** saklanır: Windows'ta `%APPDATA%\TuyaDesktopApp\devices.json` (macOS: `~/Library/Application Support/TuyaDesktopApp`, Linux: `~/.config/TuyaDesktopApp`). Dosya şifrelenmez (Linux/macOS'ta yalnızca kullanıcınız okuyabilir). **Paylaşmayın, depoya yüklemeyin.**
- **Access Secret** yalnızca tek seferlik alma işlemi için kullanılır ve hiçbir yere kaydedilmez. Başarılı alımdan sonra, pano hâlâ o secret'ı tutuyorsa uygulama panoyu da temizler.
- Uygulama hiçbir yere veri göndermez. İnternet yalnızca kurulum sihirbazında Tuya Cloud ile konuşmak için kullanılır.
- Günlük, hata mesajları ve tanılama raporunda yerel anahtar, cihaz kimliği, UUID, Bluetooth adresi ve ışık adları maskelenir.
- Bir ışığın yerel anahtarını bilen ve Bluetooth menzilinde olan biri o ışığı kontrol edebilir.
- Kaldırırken ışıklarınız ve enerji geçmişiniz, silmeyi seçmedikçe korunur.
- Eski bir sürümden (veri klasörü `OdamdakiIsik`) geçiyorsanız ışıklarınız ve enerji geçmişiniz ilk açılışta otomatik taşınır.

## Sorun giderme

Uygulama ışığı bulamadığında bir **sorun giderici kart** gösterir. Çözmezse ⚙ → *Tanılama raporunu kopyala* deyip bir [sorun kaydı](https://github.com/nevzatius/tuya-desktop-app/issues/new/choose) açın.

| Belirti | Olası neden / çözüm |
|---|---|
| "Işık bulunamadı" | Bluetooth kapalı ya da yok; **telefondaki Smart Life ışığa bağlı** (ışığa aynı anda tek bağlantı olur: uygulamayı kapatın ya da telefonun Bluetooth'unu kapatın); ışık kapalı ya da uzakta; uygulamanın başka bir kopyası ya da başka bir program ışığı kullanıyor. |
| "Işık anahtarı reddetti" | Anahtar eski (ışığı Smart Life'tan silip yeniden eklediyseniz değişir). *Işık ekle…* ile yeniden alın. |
| "Işık el sıkışmaya yanıt vermedi" | Anahtar yanlış ya da cihaz bu BLE protokolünü desteklemiyor (hem Wi-Fi hem Bluetooth'lu her cihaz desteklemez). |
| Bağlanıyor ama ışık tepki vermiyor | **Günlük** düğmesini açıp hataya bakın. DP numaraları standarttan farklı olabilir ([Desteklenen cihazlar](#desteklenen-cihazlar)); sihirbaz bunları cihazdan okur, "deneysel" cihazlar farklı komut seti kullanabilir. |
| Sihirbaz: "Access ID veya Secret yanlış" | İki değeri de projenin *Overview* sayfasından yeniden kopyalayın (yapıştırırken karakter kaybolabilir) ve aynı projeye ait olduklarından emin olun. Veri merkezi otomatik denenir; *Gelişmiş* bölümünden seçebilirsiniz. |
| Sihirbaz: "Bu projeye bağlı cihaz bulunamadı" | Tuya projesinde *Devices → Link App Account* ile Smart Life hesabınızı QR kodla bağlayın. |
| Sihirbaz: "yetki" hatası | Projenin *Service API* sekmesinde Smart Home ile ilgili hizmetlerin (ör. *IoT Core*) ekli olduğundan emin olun. |
| Kurulumda Windows SmartScreen uyarısı | Beklenen durum: yükleyici henüz kod imzalı değil. *Ek bilgi → Yine de çalıştır*. İndirdiğinizi sürümdeki `SHA256SUMS.txt` ile doğrulayabilirsiniz. |
| Uygulama açılışta pencere göstermiyor | "Windows ile başlat"ı seçtiniz: sistem tepsisinde açılır. Tepsi simgesine tıklayın. |
| Dili değiştirdim ama bir şey olmadı | Dil, uygulamayı bir sonraki açışınızda değişir. |

## Yol haritası

- Wi-Fi / yerel ağ kontrolü (tinytuya ile)
- Geliştirici hesabı gerektirmeyen Smart Life QR girişi (kendi Tuya istemci kimliğimiz gerekir)
- Kod imzalı yükleyici (SmartScreen uyarısını kaldırır)
- Gerçekten güç ölçen akıllı prizler için enerji sekmesi
- Daha fazla ışık türü, sahne ve zamanlayıcı; daha fazla çeviri

## Katkıda bulunma

Hata bildirimleri, cihaz raporları ve çekme istekleri (pull request) memnuniyetle karşılanır. Testleri çalıştırma ve çeviri ekleme için [CONTRIBUTING.md](CONTRIBUTING.md) dosyasına bakın.

## Lisans

[MIT](LICENSE).

## Teşekkürler

[tuya-ble-sdk](https://pypi.org/project/tuya-ble-sdk/) (BLE el sıkışması), [bleak](https://github.com/hbldh/bleak) (Bluetooth), [tinytuya](https://github.com/jasonacox/tinytuya) (Tuya Cloud), [PySide6 / Qt](https://www.qt.io/) (LGPL), [Inno Setup](https://jrsoftware.org/isinfo.php) (yükleyici).

---

## Kaynaktan kurulum

Python 3.12 ya da üstü gerekir.

```
python -m pip install -r requirements.txt
python light_app.py
```

Windows'ta ayrıca `kur.ps1` (sanal ortam kurar), ardından konsol penceresi açmadan başlatmak için `baslat.bat` ya da masaüstü kısayolu için `kisayol_olustur.ps1` kullanılabilir.

Kendi Windows dosyalarınızı derlemek için (PyInstaller; yükleyici için ayrıca [Inno Setup 6](https://jrsoftware.org/isinfo.php) gerekir):

```
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
powershell -ExecutionPolicy Bypass -File .\installer\build_installer.ps1
powershell -ExecutionPolicy Bypass -File .\installer\package_release.ps1
```

## Geliştirme

```
python -m pip install -r requirements-dev.txt
python -m pytest tests            # ışık gerekmez; Qt "offscreen" modunda çalışır
python docs/make_screenshots.py   # docs/screenshots/en ve /tr klasörlerini örnek verilerle yeniden üretir
```

Yapı: `light_core.py` (BLE oturumu, komut kodlama), `devices.py` (ışık deposu, veri klasörü geçişi), `cloud_import.py` (Tuya Cloud'dan içe aktarma), `energy.py` (tahminler), `diagnostics.py` ve `privacy.py` (rapor ve maskeleme), `i18n.py` ve `locales/` (metinler), `ui/` (PySide6 arayüzü), `light_app.py` (giriş noktası), `installer/` (Inno Setup betiği ve derleme betikleri).

Komut satırı araçları (`app.py`, `get_credentials.py`) geliştirici araçlarıdır ve hâlâ **yalnızca Türkçedir**. `python app.py scan` çevredeki Tuya BLE cihazlarını listeler; `python app.py -h` tüm komutları gösterir.
