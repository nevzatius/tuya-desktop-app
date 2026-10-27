"""Türkçe arayüz metinleri. Yer tutucular `{ad}` biçimindedir; İngilizce dosyayla aynı olmalı."""

STRINGS: dict[str, str] = {
    # -- uygulama ----------------------------------------------------------------
    "app.already_running": "Uygulama zaten çalışıyor (sistem tepsisine bakın).",
    "app.store_error": "{error}\n\nDosyayı silip uygulamayı yeniden açabilirsiniz.",
    # -- ışık adları ---------------------------------------------------------------
    "device.default_name": "Odamdaki ışık",
    "device.fallback_name": "Işık",
    # -- bağlantı durumu (durum etiketi) --------------------------------------------
    "status.searching": "Işık aranıyor…",
    "status.not_found": "Işık bulunamadı",
    "status.connecting": "Bağlanılıyor…",
    "status.failed": "Bağlantı kurulamadı",
    "status.connected": "Bağlı",
    "status.closed": "Bağlantı kapalı",
    "status.no_light": "Işık yok",
    # -- hatalar ---------------------------------------------------------------------
    "error.config_missing": "{name} bulunamadı. Önce `python get_credentials.py` komutunu çalıştırın.",
    "error.config_unreadable": "{name} okunamadı: {error}",
    "error.config_field": "{name} içinde eksik alan: {fields}",
    "error.not_found": (
        "Işık bulunamadı. Bluetooth açık mı, ışığa yakın mısınız ve telefondaki "
        "Smart Life uygulaması ışığa bağlı değil mi? (BLE'de aynı anda tek bağlantı olur)"
    ),
    "error.auth_rejected": (
        "Işık anahtarı reddetti. Yerel anahtar eski olabilir (ışığı Smart Life'tan silip yeniden eklediyseniz değişir): "
        "üstteki menüden “Işık ekle…” ile anahtarı yenileyin. Yakında aynı modelden başka ışıklar da olabilir."
    ),
    "error.handshake": (
        "Işık el sıkışmaya yanıt vermedi. Yerel anahtar yanlış olabilir ya da "
        "cihaz bu BLE protokolünü desteklemiyor (hem Wi-Fi hem Bluetooth'lu her cihaz desteklemez)."
    ),
    "error.bluetooth": "Bluetooth hatası: {error}",
    "error.unexpected": "Beklenmeyen hata: {error}",
    "error.timeout": "Bağlantı zaman aşımına uğradı",
    "error.store_unreadable": "{path} okunamadı: {error}",
    "error.store_incomplete": "device_id/local_key eksik",
    # -- Tuya Cloud ------------------------------------------------------------------
    "cloud.no_tinytuya": "tinytuya yüklü değil. Bağımlılıkları yeniden kurun (pip install -r requirements.txt).",
    "cloud.id_length": "Access ID {length} karakter olmalı (şu an {got}).",
    "cloud.secret_length": "Access Secret {length} karakter olmalı (şu an {got}). Yapıştırırken karakter kaybolmuş olabilir.",
    "cloud.sign_invalid": "Access ID veya Secret yanlış (ya da bu bölgeye ait değil). Değerleri iot.tuya.com'dan yeniden kopyalayın.",
    "cloud.permission": "Proje bu işlem için yetkili değil. Cloud projesinde 'Smart Home' API paketlerinin ekli olduğundan emin olun.",
    "cloud.token": "Tuya Cloud'dan oturum alınamadı. Bilgileri ve internet bağlantısını kontrol edin.",
    "cloud.network": "Tuya Cloud'a ulaşılamadı. İnternet bağlantınızı kontrol edip tekrar deneyin.",
    "cloud.failed": "Tuya Cloud bağlantısı başarısız: {error}",
    "cloud.unknown_error": "bilinmeyen hata",
    "cloud.list_failed": "Cihaz listesi alınamadı: {error}",
    "cloud.no_devices": (
        "Bu projeye bağlı cihaz bulunamadı. Cloud projesinde Devices → Link App Account bölümünden "
        "Smart Life hesabınızı QR ile bağlayın."
    ),
    "region.eu": "Orta Avrupa (Türkiye için genelde bu)",
    "region.eu-w": "Batı Avrupa",
    "region.us": "Batı ABD",
    "region.us-e": "Doğu ABD",
    "region.in": "Hindistan",
    "region.sg": "Singapur",
    "region.cn": "Çin",
    # -- ana pencere -----------------------------------------------------------------
    "main.no_light_button": "Işık yok  ▾",
    "main.no_light_banner": "Henüz ışık eklenmedi. Üstteki menüden “Işık ekle…” seçin.",
    "main.add_light": "Işık ekle…",
    "main.rename": "Adını değiştir…",
    "main.remove": "Bu ışığı kaldır",
    "main.tab_control": "Kontrol",
    "main.tab_energy": "Enerji",
    "main.brightness": "Parlaklık",
    "main.white": "Beyaz",
    "main.colour": "Renk",
    "main.temperature": "Işık sıcaklığı",
    "main.warm": "Sıcak",
    "main.neutral": "Nötr",
    "main.cool": "Soğuk",
    "main.presets": "Hazır ayarlar",
    "main.log": "Günlük",
    "main.reconnect": "Yeniden bağlan",
    "main.read_state": "Durumu oku",
    "main.settings": "Ayarlar",
    "main.language": "Dil",
    "main.language_auto": "Sistem dili",
    "main.language_restart": "Dil değişikliği uygulamayı bir sonraki açışınızda geçerli olur.",
    "mode.white": "Beyaz ışık",
    "mode.colour": "Renkli",
    "mode.scene": "Sahne",
    "mode.music": "Müzik",
    "state.on": "Açık",
    "state.off": "Kapalı",
    "state.tap_to_turn_on": "Açmak için dokun",
    "state.waiting": "Işıktan bilgi bekleniyor",
    # -- hazır ayarlar -----------------------------------------------------------------
    "preset.reading": "Okuma",
    "preset.focus": "Odak",
    "preset.night": "Gece",
    "preset.movie": "Film",
    "preset.romantic": "Romantik",
    "preset.ocean": "Okyanus",
    # -- tepsi ---------------------------------------------------------------------------
    "tray.on": "Işığı aç",
    "tray.off": "Işığı kapat",
    "tray.show": "Pencereyi göster",
    "tray.quit": "Çık",
    "tray.hint": "Uygulama sistem tepsisinde çalışmaya devam ediyor.",
    # -- denetleyici ---------------------------------------------------------------------
    "controller.remove_confirm": "“{name}” kaldırılsın mı? Anahtarı bu bilgisayardan silinir (ışığın kendisine dokunulmaz).",
    "controller.remove": "Kaldır",
    "controller.cancel": "Vazgeç",
    "controller.rename_title": "Adını değiştir",
    "controller.rename_label": "Işığın adı:",
    # -- enerji --------------------------------------------------------------------------
    "energy.period_day": "BUGÜN",
    "energy.period_week": "SON 7 GÜN",
    "energy.period_month": "SON 30 GÜN",
    "energy.tab_day": "Gün",
    "energy.tab_week": "Hafta",
    "energy.tab_month": "Ay",
    "energy.settings_title": "Tahmin ayarları",
    "energy.watts_label": "Işığın gücü (tam parlaklıkta)",
    "energy.price_label": "Elektrik birim fiyatı",
    "energy.currency_label": "Para birimi",
    "energy.price_unset": "Girilmedi",
    "energy.price_note": "EPDK mesken tarifesi (Nisan 2026, kademe 1, KDV ve BTV dahil) ≈ 3,37 TL/kWh. Güncel fiyat için faturanıza bakın.",
    "energy.watts_hint": "Işığın gücü ambalajında ya da ürün sayfasında yazar (ör. 9 W).",
    "energy.disclaimer": (
        "Bu değerler <b>tahmindir</b>: ışık güç ölçmez; güç × parlaklık × açık kalma süresi hesaplanır. "
        "Yalnızca uygulama açıkken ve ışığa bağlıyken kaydedilir; telefon ya da duvar anahtarıyla yapılan "
        "değişiklikler bağlantı kesikken görülmez."
    ),
    "energy.no_records": "Kayıt yok",
    "energy.price_needed": "Maliyeti görmek için elektrik birim fiyatını girin",
    "energy.detail": "{kwh} · {duration} açık",
    "energy.all_lights": "Tüm ışıklar: {cost} · {kwh}",
    "energy.all_lights_nocost": "Tüm ışıklar: {kwh}",
    "energy.tip_duration": "{duration} açık",
    "day.0": "Pzt",
    "day.1": "Sal",
    "day.2": "Çar",
    "day.3": "Per",
    "day.4": "Cum",
    "day.5": "Cmt",
    "day.6": "Paz",
    "fmt.percent": "%{value}",
    "fmt.hours_minutes": "{hours} sa {minutes} dk",
    "fmt.hours": "{hours} sa",
    "fmt.minutes": "{minutes} dk",
    # -- ekleme sihirbazı ----------------------------------------------------------------
    "setup.title": "Işık ekle",
    "setup.step_of": "Adım {current} / {total}",
    "setup.back": "Geri",
    "setup.cancel": "Vazgeç",
    "setup.open_tuya": "iot.tuya.com'u aç",
    # 1. adım: hoş geldin
    "setup.welcome_title": "Işığını bağlayalım",
    "setup.welcome_body": (
        "Işığı kontrol edebilmek için <b>bir kerelik bir anahtar</b> gerekir. Bu anahtarı yalnızca kendi Tuya "
        "hesabın verebilir. Yaklaşık 10 dakika sürer ve yalnızca bir kez yapılır; sonrasında her şey internetsiz, "
        "Bluetooth ile çalışır."
    ),
    "setup.welcome_checklist": (
        "<b>Başlamadan önce hazır olsun:</b><br>"
        "• Telefonunda Smart Life uygulaması ve ışığın orada kayıtlı olması<br>"
        "• Işığın yanında, prize takılı ve açık olması<br>"
        "• Bilgisayarında Bluetooth"
    ),
    "setup.start": "Başlayalım",
    # 2. adım: Tuya hesabı
    "setup.account_title": "Tuya hesabını hazırla",
    "setup.account_intro": "Aşağıdaki adımları Tuya'nın sitesinde yap. Bu pencereyi açık bırakabilirsin.",
    "setup.account_step1": "<b>1. Ücretsiz hesap aç</b> (ya da giriş yap). Smart Life hesabından ayrı, geliştirici hesabıdır.",
    "setup.account_step2": (
        "<b>2. Proje oluştur.</b> Cloud → Development → <i>Create Cloud Project</i>. "
        "Industry: <i>Smart Home</i>, Development Method: <i>Smart Home</i>, Data Center: bulunduğun bölge "
        "(Türkiye için Central Europe ya da Western Europe)."
    ),
    "setup.account_step3": (
        "<b>3. Smart Life hesabını bağla.</b> Projede <i>Devices → Link App Account → Add App Account</i> de, "
        "çıkan QR kodu telefondaki Smart Life ile okut (Ben → sağ üstteki tarama simgesi)."
    ),
    "setup.account_step4": "<b>4. Anahtarları kopyala.</b> Projenin <i>Overview</i> sayfasındaki <i>Access ID</i> ve <i>Access Secret</i> değerlerini kopyalayacaksın.",
    "setup.account_trouble": (
        "Sonra “yetki” hatası alırsan projenin <i>Service API</i> sekmesinde Smart Home ile ilgili hizmetlerin "
        "(ör. <i>IoT Core</i>) ekli olduğundan emin ol."
    ),
    "setup.account_next": "Access ID ve Secret'ı aldım",
    # 3. adım: bilgiler
    "setup.cred_title": "Anahtarlarını gir",
    "setup.cred_intro": "Değerleri Overview sayfasından kopyala. İpucu: yalnızca kopyalaman yeterli, uygulama panodan kendisi alır.",
    "setup.chars_20": "20 karakter",
    "setup.chars_32": "32 karakter",
    "setup.show": "Göster",
    "setup.field_status": "{got} / {length}",
    "setup.field_ok": "✓ {got} / {length}",
    "setup.pasted_id": "Access ID panodan yapıştırıldı.",
    "setup.pasted_secret": "Access Secret panodan yapıştırıldı.",
    "setup.advanced": "Gelişmiş  ▾",
    "setup.region": "Veri merkezi",
    "setup.region_auto": "Otomatik (önerilen)",
    "setup.region_hint": "Otomatik seçilirse bölgen tahmin edilir, olmazsa diğerleri sırayla denenir.",
    "setup.manual_button": "Anahtarı elle gireceğim",
    "setup.find": "Işıklarımı bul",
    "setup.connecting": "Tuya Cloud'a bağlanılıyor…",
    "setup.retry": "Tekrar dene",
    # 4. adım: ışık seç
    "setup.lights_title": "Işıklarını seç ve adlandır",
    "setup.lights_hint": "Eklemek istediklerini işaretle ve her birine tanıyacağın bir ad ver.",
    "setup.name_placeholder": "Işığın adı",
    "setup.scan": "Yakınımdaki ışıkları ara",
    "setup.scanning": "Yakındaki Bluetooth ışıkları aranıyor…",
    "setup.scan_found": "Yakında {count} Tuya Bluetooth cihazı bulundu.",
    "setup.scan_none": "Yakında Tuya Bluetooth cihazı bulunamadı. Işık açık mı, Bluetooth açık mı ve telefondaki Smart Life ışığa bağlı değil mi?",
    "setup.scan_failed": "Tarama başarısız: {error}",
    "setup.nearby": "yakında · sinyal {signal}",
    "setup.signal_strong": "güçlü",
    "setup.signal_good": "iyi",
    "setup.signal_weak": "zayıf",
    "setup.not_seen": "yakında görünmedi",
    "setup.scan_unmatched": "Hesabınla eşleşmeyen {count} cihaz daha var (en güçlü sinyal: {signal}); bazılarının kimliği okunamamış olabilir, “Yanıp söndür” yine de doğru ışığı bulur.",
    "setup.blink": "Yanıp söndür",
    "setup.blink_hint": "Yakında birden çok ışık mı var? Hangisinin hangisi olduğunu görmek için “Yanıp söndür”e bas.",
    "setup.blinking": "Işığa bağlanılıyor, yanıp sönecek…",
    "setup.blink_done": "Yanıp söndü mü? O zaman bu ışık bu. Eski durumuna döndü.",
    "setup.blink_failed": "Yanıp söndürülemedi: {error}",
    "setup.add_selected": "Seçilenleri ekle",
    "setup.not_light": "ışık değil",
    "setup.already_added": "zaten ekli, anahtarı güncellenir",
    "setup.experimental": "deneysel",
    "setup.experimental_note": "“Deneysel” cihazlar standart ışık komutlarını kullanmayabilir; çalışmazsa günlükten bakın.",
    "setup.pick_one": "Önce en az bir cihaz işaretleyin.",
    # elle giriş (ileri düzey)
    "setup.manual_title": "Anahtarı elle gir",
    "setup.manual_intro": "Bu bilgileri Tuya Cloud'dan ya da başka bir araçtan zaten aldıysanız kullanın.",
    "setup.manual_name_placeholder": "ör. Oturma odası",
    "setup.field_name": "Ad",
    "setup.field_device_id": "Cihaz ID",
    "setup.field_local_key": "Yerel anahtar",
    "setup.field_uuid": "UUID",
    "setup.add": "Ekle",
    "setup.manual_required": "Cihaz ID ve yerel anahtar zorunlu.",
    # başarı
    "setup.done_title": "Hazırsın",
    "setup.done_body": "{names} eklendi. Uygulama şimdi Bluetooth ile ışığa bağlanacak. Bir daha bu adımlara gerek yok.",
    "setup.done_button": "Uygulamayı aç",
    # -- sorun giderici ve tanılama -------------------------------------------------------
    "common.unverified": "Deneysel: bu özellik gerçek cihazda henüz doğrulanmadı.",
    "trouble.title": "Işığına ulaşılamadı",
    "trouble.intro": "Sırayla şunlara bak (en olası olandan başlayarak):",
    "trouble.bt_title": "Bluetooth",
    "trouble.bt_checking": "Bluetooth denetleniyor…",
    "trouble.bt_ok": "Bluetooth açık ve adaptör çalışıyor.",
    "trouble.bt_off": "Bluetooth kapalı görünüyor.",
    "trouble.bt_off_fix": "Çözüm: Windows ayarlarından Bluetooth'u aç, sonra “Tekrar dene”ye bas.",
    "trouble.bt_missing": "Bluetooth adaptörü bulunamadı.",
    "trouble.bt_missing_fix": "Çözüm: bilgisayarında Bluetooth (4.0 ya da üstü) olmalı; yoksa ucuz bir USB Bluetooth adaptörü takabilirsin.",
    "trouble.bt_unknown": "Bluetooth denetlenemedi; yine de aşağıdakilere bak.",
    "trouble.open_bt": "Bluetooth ayarlarını aç",
    "trouble.recheck": "Bluetooth'u yeniden denetle",
    "trouble.phone_title": "Telefondaki Smart Life ışığa bağlı olabilir",
    "trouble.phone_fix": "Işığa aynı anda tek cihaz bağlanabilir. Smart Life uygulamasını tamamen kapat ya da telefonun Bluetooth'unu kapat.",
    "trouble.far_title": "Işık uzakta ya da kapalı olabilir",
    "trouble.far_fix": "Işığın prizde ve açık olduğundan emin ol (duvar anahtarı dahil) ve bilgisayara birkaç metre yaklaştır.",
    "trouble.other_title": "Uygulama başka bir yerde açık olabilir",
    "trouble.other_fix": "Sistem tepsisine bak; uygulamanın başka bir kopyasını ya da ışığa bağlanan başka bir programı kapat.",
    "trouble.retry": "Tekrar dene",
    "trouble.copy_report": "Tanılama raporunu kopyala",
    "main.copy_report": "Tanılama raporunu kopyala",
    "main.report_problem": "Sorun bildir…",
    "main.report_copied": (
        "Tanılama raporu panoya kopyalandı. Sorun bildirirken GitHub'daki forma yapıştırın. "
        "Yerel anahtar, cihaz kimliği ve adres içermez; yine de göndermeden önce göz atın."
    ),
    # -- kullanıcının kendi hazır ayarları -------------------------------------------------
    "presets.save_current": "＋ Şu anki durumu kaydet",
    "presets.manage": "Yönet…",
    "presets.dialog_new": "Hazır ayar olarak kaydet",
    "presets.dialog_edit": "Hazır ayarı düzenle",
    "presets.name_label": "Ayarın adı",
    "presets.name_placeholder": "ör. Çalışma masası",
    "presets.save": "Kaydet",
    "presets.edit": "Düzenle…",
    "presets.delete": "Sil",
    "presets.hide": "Gizle",
    "presets.show": "Göster",
    "presets.close": "Kapat",
    "presets.manage_title": "Hazır ayarları yönet",
    "presets.builtin_tag": "yerleşik",
    "presets.hidden_tag": "gizli",
    "presets.delete_confirm": "“{name}” silinsin mi?",
    "presets.error_empty": "Bir ad yazın.",
    "presets.error_too_long": "Ad en fazla {max} karakter olabilir.",
    "presets.error_duplicate": "Bu ada sahip bir hazır ayar zaten var.",
    "presets.error_limit": "En fazla {max} kendi ayarınızı kaydedebilirsiniz.",
    "presets.error_builtin": "Yerleşik ayarlar silinemez ya da değiştirilemez; yalnızca gizlenebilir.",
    "presets.error_unknown": "Hazır ayar bulunamadı.",
    "presets.error_values": "Ayar değerleri geçersiz.",
    "presets.error_write": "Dosyaya yazılamadı: {error}",
    "presets.recovered": "Hazır ayarlar dosyası okunamadı ya da bozuktu. Yedeği alındı, yerleşik ayarlarla devam ediliyor.",
    # -- otomasyon (motor) -----------------------------------------------------------------
    "automation.failed": "“{rule}” otomasyonu çalışamadı ({light}): {reason}",
    "automation.reason_unreachable": "ışığa ulaşılamadı (3 deneme yapıldı)",
    "automation.reason_unknown_light": "ışık artık kayıtlı değil",
    "automation.reason_preset_missing": "kullanılan hazır ayar silinmiş",
    "automation.reason_other": "beklenmeyen bir hata oluştu",
    "automation.recovered": "Otomasyon dosyası okunamadı ya da bazı kurallar bozuktu. Yedeği alındı; geçerli kurallarla devam ediliyor.",
}
