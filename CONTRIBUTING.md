# Contributing / Katkıda bulunma

Thanks for helping! Bug reports, **device reports** (does your light work?) and pull requests are all welcome.
Teşekkürler! Hata bildirimleri, **cihaz raporları** (ışığınız çalıştı mı?) ve çekme istekleri memnuniyetle karşılanır.

## Before you post anything / Bir şey paylaşmadan önce

Never paste local keys, an Access Secret, device IDs or Bluetooth addresses into an issue, a pull request or a screenshot.
Use the app's ⚙ → **Copy diagnostic report**: it is built to leave all of those out.
Yerel anahtar, Access Secret, cihaz kimliği ya da Bluetooth adresini sorun kaydına, çekme isteğine ya da ekran görüntüsüne yapıştırmayın.
Uygulamada ⚙ → **Tanılama raporunu kopyala** bunların hiçbirini içermeyecek şekilde hazırlanır.

## Run the tests / Testleri çalıştırma

Python 3.12 or newer. No light is needed; Qt runs in offscreen mode.

```
python -m pip install -r requirements-dev.txt
python -m pytest tests
```

Please keep the suite green and add a test for new behaviour. Tests run in Turkish by default (`tests/conftest.py`); a test that needs English calls `i18n.set_language("en")`.

**Tests must never touch a real light or a running copy of the app.** An autouse fixture in `tests/conftest.py` enforces this: user-data folders (`APPDATA`, `LOCALAPPDATA`, `XDG_CONFIG_HOME`, `HOME`, temp) point to a temporary directory, `QSettings` writes to a temporary `.ini`, any real `BleakScanner`/`BleakClient` use raises an error, the command channel name is unique per test (connecting to or listening on the real app's channel raises), and global hotkeys go to an in-memory fake instead of Win32 `RegisterHotKey`. Do not work around it; if a test needs Bluetooth, give it a fake (see `tests/test_core.py`). `tests/test_isolation.py` proves the guard works.
Testler gerçek ışığa ve çalışan uygulamaya dokunmamalıdır: `tests/conftest.py` içindeki otomatik koruma veri klasörlerini geçici dizine yönlendirir, Bluetooth'u engeller, komut kanalını benzersiz yapar ve genel kısayolları sahteye bağlar. Bu korumayı aşmayın; Bluetooth gereken testte sahte nesne kullanın.

## Add or fix a translation / Çeviri ekleme

Texts live in plain dictionaries, one file per language: `locales/en.py` (reference) and `locales/tr.py`. No Qt Linguist is used.

To fix a text, edit the value in the language file. To **add a language** (for example German, code `de`):

1. Copy `locales/en.py` to `locales/de.py` and translate the values. Keep every key and every `{placeholder}` exactly as in English (for example `{name}`, `{count}`).
2. Register it in `i18n.py`: import the module, then add it to `_CATALOGS` (`"de": _de.STRINGS`) and to `LANGUAGES` with its name in its own language (`"de": "Deutsch"`).
3. Run `python -m pytest tests/test_i18n.py`. It checks that your file has exactly the same keys and placeholders as English, and that no user-visible text is hard-coded in the Python code.
4. Regenerate screenshots if you like: `python docs/make_screenshots.py` (edit the language list in that script).

Notes: the system language is picked automatically when its code matches a registered language, otherwise English. Number formats follow English rules unless the language is Turkish; the electricity price starts empty with a selectable currency for every language except Turkish. Log lines and the diagnostic report are always English on purpose, so maintainers can read them.

Çeviri eklemek için `locales/en.py` dosyasını `locales/<kod>.py` olarak kopyalayın, değerleri çevirin (anahtarları ve `{yer_tutucuları}` değiştirmeyin), dili `i18n.py` içinde `_CATALOGS` ve `LANGUAGES` sözlüklerine ekleyin ve `python -m pytest tests/test_i18n.py` çalıştırın.

## Pull requests

- Keep the change focused; describe what you tried and on which device (or say that it was tests only).
- Do not mark a feature as verified on real hardware unless you tried it on real hardware. The README *Status* table is meant to be honest.
- Windows is the primary target; changes must not break `python -m pytest tests` on Linux either (CI runs it there).
