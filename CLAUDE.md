# tuya-desktop-app

Tuya/Smart Life ışıklarını Bluetooth LE ile kontrol eden Windows odaklı masaüstü uygulaması (Python 3.12+, PySide6, bleak, tuya-ble-sdk). Resmi değildir. Sohbet dili: Türkçe, kısa yanıtlar.

## Mimari (nerede ne var)
- Kök modüller Qt'siz çalışır:
  - light_core.py: BLE oturumu, el sıkışma, DP komutları, LightClient/find_candidates
  - devices.py: ışık deposu (devices.json, kullanıcı veri klasörü); storage.py: ortak JSON okuma/yazma
  - cloud_import.py: Tuya Cloud'dan içe aktarma; get_credentials.py: aynısının komut satırı hâli
  - energy.py: tahmini tüketim (SQLite energy.db)
  - automation.py: otomasyon motoru (kurallar, zamanlayıcı, yumuşak geçiş); sun.py: gün doğumu/batımı hesabı
  - quick_cli.py: --scene/--power argüman çözümleme; shortcuts.py: genel kısayol kombinasyonu çözümleme
  - diagnostics.py: tanılama raporu ve günlük/rapor maskeleme (gizli bilgi süzgeci burada)
- ui/: PySide6 arayüzü
  - main_window, setup_dialog, controller, energy_page, widgets, theme, tray, trouble, workers
  - presets, presets_view, scene_editor: hazır ayarlar ve parlaklık/renk düzenleyici
  - automation_page, rule_dialog, automation_text, automation_host: otomasyon sekmesi ve motoru uygulamaya bağlayan katman
  - ipc.py (komut satırı için yerel kanal), hotkeys.py (Windows genel kısayolları, RegisterHotKey), tray.py (hazır ayar alt menüsü, otomasyonu duraklat)
  - bridge.py: BLE asyncio iş parçacığı ↔ Qt köprüsü ("son değer kazanır" komut birleştirme)
- i18n.py + locales/tr.py, locales/en.py: tüm kullanıcı metinleri buradan; koda Türkçe/İngilizce metin gömme
- light_app.py: giriş noktası; app.py: komut satırı (Türkçe kalır); version.py: sürüm ve veri klasörü adları
- Paketleme: installer/ (Inno Setup), build_exe.ps1, kur.ps1, baslat*.bat, .github/workflows/ (ci.yml, release.yml)
- tests/: pytest, ışık gerekmez; conftest.py her teste Türkçe dille başlar. docs/make_screenshots.py README görüntülerini ÖRNEK verilerle üretir.

## Komutlar
- Test: `.\.venv\Scripts\python.exe -m pytest -q tests` (CI'da ve Linux'ta `QT_QPA_PLATFORM=offscreen`)
- Çalıştır: `.\.venv\Scripts\python.exe light_app.py` (telefondaki Smart Life'ın Bluetooth'u kapalı olmalı)
- Kurulum: kur.ps1; exe: build_exe.ps1

## Kurallar
- GİZLİ BİLGİ: yerel anahtar, Access Secret, cihaz kimliği, MAC, uuid asla commit, log, test verisi, ekran görüntüsü ya da sohbet çıktısında olmasın. config.json, devices.json, tinytuya.json, tuya-raw.json, *.db ve kullanıcı verisi (presets/automations json) .gitignore'da.
- Git: ben söylemeden push, force-push, etiket, release, PR birleştirme, depo ayarı değişikliği YOK. Her iş ayrı commit. `git add .` yerine dosyaları adıyla ekle.
- Yeni kullanıcı metni her zaman tr ve en'de eklenir; tests/test_i18n.py (anahtar tamlığı, gömülü Türkçe metin yok) geçmeli.
- Bağımlılık ekleme; gerekiyorsa önce sor.
- tuya-ble-sdk'nın alt çizgili iç metotlarına dayanıyoruz; sürüm sabit (requirements.txt: ==0.1.3).

## Bilinen sınırlar / durum
- BLE'de ışığa aynı anda tek bağlantı: telefon uygulaması ya da başka bir kopya bağlıysa ışık görünmez.
- Enerji değerleri tahmindir (watt × parlaklık × süre); yalnızca uygulama açık ve bağlıyken kaydedilir.
- Wi-Fi/LAN kontrolü ve Smart Life QR girişi yok (Tuya istemci kimliği gerekir).
- Gerçek cihazda doğrulanmayan özellikler README Durum tablosunda "doğrulanmadı" diye işaretli kalır.
- Dal v0.4.0 üzerinde çalışılıyor: kendi hazır ayarlar, otomasyon motoru ve sekmesi, hızlı erişim (tepsi, --scene/--power, kısayollar). Hepsi gerçek cihazda henüz doğrulanmadı (README Durum tablosunda işaretli).
- Otomasyonlar yalnızca uygulama çalışırken, bilgisayar uyanıkken ve ışık menzildeyken çalışır; Smart Life bulut zamanlayıcılarından ayrıdır.
