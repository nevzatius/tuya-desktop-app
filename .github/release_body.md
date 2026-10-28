## Tuya Desktop App 0.4.0

Unofficial Windows app that controls Tuya / Smart Life lights over Bluetooth LE. No cloud at runtime; the internet is only used once, by the setup wizard.

### How to install (Windows)

1. Download **`TuyaDesktopApp-Setup-0.4.0.exe`** from the *Assets* list below. This is the recommended file: a per-user installer (no admin rights) with Start menu entry, optional desktop shortcut and optional "Start with Windows" (starts in the tray).
2. Run it. If Windows SmartScreen says "Windows protected your PC", click **More info → Run anyway**. The warning appears because the app is not code-signed yet (a signing certificate costs money), not because something is wrong.
3. Click *Next → Next → Finish*, then follow the first-run wizard to connect your light (about 10 minutes, once).

No installer? Download **`TuyaDesktopApp-portable-0.4.0.zip`**, extract it anywhere and run the `.exe` inside.

**Verify your download** (Windows PowerShell), then compare with the matching line in `SHA256SUMS.txt`:

```powershell
Get-FileHash .\TuyaDesktopApp-Setup-0.4.0.exe -Algorithm SHA256
```

### What's new in 0.4.0

- **Setup wizard v2:** clipboard detection, live validation, nearby-light scan with signal strength, "Try again" recovery buttons.
- **Turkish and English interface** (⚙ menu; follows the system language by default).
- **Energy tab:** *estimated* use and cost per day, week and month (lira by default in the Turkish interface; you choose the currency in English).
- **Automations:** rules at a time on chosen weekdays, at sunrise/sunset (offline calculation) or at app start; on/off/brightness/white/colour/preset actions; **smooth fades** over 1-120 minutes; one or all lights; pause from the tray.
- **Presets:** six built-in ones plus your own (save, edit, delete, hide).
- **Quick access:** tray menu with presets, command line (`--scene`, `--power`) and Windows global shortcuts.
- **Diagnostics:** troubleshooter card, diagnostic report and a rotating log; keys, device IDs and addresses are masked.
- **Installer and portable zip**, with `SHA256SUMS.txt`.
- **Security hardening:** secrets masked in logs and error messages, the Access Secret is never saved and is cleared from memory and clipboard, oversized data files are rejected, and the release workflow is pinned and least-privilege.

### Known limits

- **Bluetooth only.** No Wi-Fi / local network control.
- **One connection at a time.** The light accepts a single Bluetooth connection: the Smart Life app on your phone must have Bluetooth off (or be closed), and only one copy of this app can be connected.
- **Unsigned installer.** Windows SmartScreen may warn (see above).
- **Energy values are estimates** (rated watts × brightness × time), recorded only while the app is open and connected.
- **Automations run only while the app is running,** the computer is awake and the light is in range; they are separate from Smart Life cloud timers.
- **Not tried on a real device:** sunrise/sunset triggers, several lights, global shortcuts and the English interface have **not yet been verified** with real hardware. The same goes for the automations' app-start trigger and white / colour / preset actions, the setup wizard v2, the Blink button, the troubleshooter and the portable zip.
- **Tried on a real light:** Bluetooth connection, on/off, brightness and colour, presets, a timed rule, smooth fades, pausing automations, the command line, the log, the installer and the tray menu.

The README *Status* table is the detailed, honest list. Please report what works (or not) with your light via a [device report](https://github.com/nevzatius/tuya-desktop-app/issues/new?template=device_report.yml).

---

## Tuya Desktop App 0.4.0 (Türkçe)

Tuya / Smart Life ışıklarını Bluetooth LE ile kontrol eden resmi olmayan Windows uygulaması. Çalışırken bulut yok; internet yalnızca kurulum sihirbazında, bir kez kullanılır.

### Nasıl kurulur (Windows)

1. Aşağıdaki *Assets* listesinden **`TuyaDesktopApp-Setup-0.4.0.exe`** dosyasını indirin. Önerilen dosya budur: kullanıcı başına kurulum (yönetici yetkisi gerekmez), Başlat menüsü kaydı, isteğe bağlı masaüstü kısayolu ve isteğe bağlı "Windows ile başlat" (tepside başlar).
2. Çalıştırın. Windows SmartScreen "Windows bilgisayarınızı korudu" derse **Ek bilgi → Yine de çalıştır** deyin. Bu uyarı, uygulama henüz kod imzalı olmadığı için çıkar (imza sertifikası ücretlidir); bir sorun olduğu anlamına gelmez.
3. *İleri → İleri → Bitir* deyin, sonra ilk açılış sihirbazını izleyerek ışığınızı bağlayın (yaklaşık 10 dakika, bir kez).

Kurulum istemezseniz **`TuyaDesktopApp-portable-0.4.0.zip`** dosyasını istediğiniz yere çıkarıp içindeki `.exe`'yi çalıştırın.

**İndirdiğinizi doğrulayın** (Windows PowerShell); çıkan değeri `SHA256SUMS.txt` içindeki ilgili satırla karşılaştırın:

```powershell
Get-FileHash .\TuyaDesktopApp-Setup-0.4.0.exe -Algorithm SHA256
```

### 0.4.0'da yeni olanlar

- **Kurulum sihirbazı v2:** pano algılama, anlık doğrulama, sinyal gücüyle yakın ışık taraması, "Tekrar dene" düğmeleri.
- **Türkçe ve İngilizce arayüz** (⚙ menüsü; varsayılan sistem dilidir).
- **Enerji sekmesi:** günlük, haftalık ve aylık **tahmini** tüketim ve maliyet (Türkçe arayüzde varsayılan TL; İngilizcede para birimini siz seçersiniz).
- **Otomasyonlar:** seçtiğiniz günlerde belirli saatte, gün doğumu/batımında (çevrimdışı hesap) ya da uygulama açılırken çalışan kurallar; aç/kapat/parlaklık/beyaz/renk/hazır ayar eylemleri; 1-120 dakikalık **yumuşak geçiş**; bir ya da tüm ışıklar; tepsiden duraklatma.
- **Hazır ayarlar:** altı yerleşik ayar ve kendi ayarlarınız (kaydet, düzenle, sil, gizle).
- **Hızlı erişim:** hazır ayarlı tepsi menüsü, komut satırı (`--scene`, `--power`) ve Windows genel kısayol tuşları.
- **Tanılama:** sorun giderici kart, tanılama raporu ve dönen günlük; anahtarlar, cihaz kimlikleri ve adresler maskelenir.
- **Yükleyici ve taşınabilir zip**, `SHA256SUMS.txt` ile.
- **Güvenlik sertleştirmeleri:** günlük ve hata metinlerinde gizli bilgi maskelenir, Access Secret hiç kaydedilmez, bellekten ve panodan silinir, aşırı büyük veri dosyaları reddedilir, release iş akışı sabitlenmiş ve en az yetkiyle çalışır.

### Bilinen sınırlar

- **Yalnızca Bluetooth.** Wi-Fi / yerel ağ kontrolü yok.
- **Tek bağlantı.** Işık aynı anda tek Bluetooth bağlantısı kabul eder: telefondaki Smart Life'ın Bluetooth'u kapalı (ya da uygulama kapalı) olmalı ve bu uygulamanın yalnızca tek kopyası bağlanabilir.
- **İmzasız kurulum.** Windows SmartScreen uyarı verebilir (yukarıya bakın).
- **Enerji değerleri tahmindir** (anma gücü × parlaklık × süre); yalnızca uygulama açık ve bağlıyken kaydedilir.
- **Otomasyonlar yalnızca uygulama çalışırken,** bilgisayar uyanıkken ve ışık menzildeyken çalışır; Smart Life bulut zamanlayıcılarından ayrıdır.
- **Gerçek cihazda henüz doğrulanmadı (denenmedi):** gün doğumu/batımı tetikleyicileri, birden çok ışık, genel kısayol tuşları ve İngilizce arayüz. Ayrıca doğrulanmadı: otomasyonların uygulama açılışı tetikleyicisi ve beyaz / renk / hazır ayar eylemleri, kurulum sihirbazı v2, Yanıp söndür düğmesi, sorun giderici ve taşınabilir zip.
- **Gerçek ışıkta denendi:** Bluetooth bağlantısı, aç/kapat, parlaklık ve renk, hazır ayarlar, saatli kural, yumuşak geçiş, otomasyonu duraklatma, komut satırı, günlük, yükleyici ve tepsi menüsü.

Ayrıntılı ve dürüst liste README'deki *Durum* tablosundadır. Işığınızla neyin çalışıp çalışmadığını [cihaz raporu](https://github.com/nevzatius/tuya-desktop-app/issues/new?template=device_report.yml) ile bildirebilirsiniz.

---

**Full Changelog**: https://github.com/nevzatius/tuya-desktop-app/compare/v0.2.0...v0.4.0
