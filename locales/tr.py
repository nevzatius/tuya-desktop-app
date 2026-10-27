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
    "fmt.hours_minutes": "{hours} sa {minutes} dk",
    "fmt.hours": "{hours} sa",
    "fmt.minutes": "{minutes} dk",
    # -- ekleme sihirbazı ----------------------------------------------------------------
    "setup.title": "Işık ekle",
    "setup.intro": (
        "Bir Tuya / Smart Life ışığını Bluetooth ile kontrol etmek için ışığa özel bir "
        "<b>yerel anahtar</b> gerekir. Bu anahtarı yalnızca ışığın bağlı olduğu Tuya hesabı verebilir; "
        "bir kez alındıktan sonra uygulama internetsiz çalışır."
    ),
    "setup.cloud_button": "Tuya hesabımdan otomatik al (önerilen)",
    "setup.manual_button": "Anahtarı elle gireceğim (ileri düzey)",
    "setup.cancel": "Vazgeç",
    "setup.cloud_title": "Tuya Cloud ile ekle",
    "setup.how": "Nasıl alırım?  ▾",
    "setup.cloud_help": (
        "<b>Bir kerelik hazırlık (yaklaşık 10 dakika)</b><br>"
        "1. <a href='https://iot.tuya.com'>iot.tuya.com</a> adresinde ücretsiz hesap açın.<br>"
        "2. Cloud → Development → <i>Create Cloud Project</i>. Industry: <i>Smart Home</i>, "
        "Development Method: <i>Smart Home</i>, Data Center: bulunduğunuz bölge (Türkiye için Central/Western Europe).<br>"
        "3. Projenin <i>Overview</i> sayfasındaki <i>Access ID</i> ve <i>Access Secret</i> değerlerini aşağıya yapıştırın.<br>"
        "4. Projede <i>Devices → Link App Account → Add App Account</i> deyip çıkan QR kodu telefonunuzdaki "
        "Smart Life uygulamasıyla okutun (Ben → sağ üstteki tarama simgesi). Işıklarınız projeye bağlanır.<br>"
        "Bilgileriniz yalnızca bu bilgisayarda saklanır; Access Secret ise hiç kaydedilmez."
    ),
    "setup.chars_20": "20 karakter",
    "setup.chars_32": "32 karakter",
    "setup.show": "Göster",
    "setup.region": "Bölge",
    "setup.back": "Geri",
    "setup.find": "Işıkları bul",
    "setup.connecting": "Tuya Cloud'a bağlanılıyor…",
    "setup.results_title": "Bulunan cihazlar",
    "setup.results_hint": "Eklemek istediklerinizi işaretleyin.",
    "setup.add_selected": "Seçilenleri ekle",
    "setup.not_light": "(ışık değil)",
    "setup.already_added": "(zaten ekli, anahtar güncellenir)",
    "setup.experimental": "(deneysel)",
    "setup.experimental_note": "“Deneysel” cihazlar standart ışık komutlarını kullanmayabilir; çalışmazsa günlükten bakın.",
    "setup.pick_one": "Önce en az bir cihaz işaretleyin.",
    "setup.manual_title": "Anahtarı elle gir",
    "setup.manual_intro": "Bu bilgileri Tuya Cloud'dan ya da başka bir araçtan zaten aldıysanız kullanın.",
    "setup.name_placeholder": "ör. Oturma odası",
    "setup.field_name": "Ad",
    "setup.field_device_id": "Cihaz ID",
    "setup.field_local_key": "Yerel anahtar",
    "setup.field_uuid": "UUID",
    "setup.add": "Ekle",
    "setup.manual_required": "Cihaz ID ve yerel anahtar zorunlu.",
}
