"""Tuya ışık kontrolü: masaüstü arayüzü ve komut satırı (Bluetooth / BLE).

    python app.py                 arayüzü aç
    python app.py scan            çevredeki Tuya BLE cihazlarını listele
    python app.py status          bağlan ve ışığın bildirdiği DP'leri yazdır
    python app.py on | off
    python app.py brightness 60   parlaklık %1-100
    python app.py white 80 20     beyaz mod: parlaklık %, sıcaklık % (0 sıcak, 100 soğuk)
    python app.py colour ff8800   renk (hex RGB)
"""

from __future__ import annotations

import argparse
import asyncio
import colorsys
import logging
import queue
import sys
import threading

import light_core as lc

MODE_NAMES = {"white": "Beyaz", "colour": "Renkli", "scene": "Sahne", "music": "Müzik"}


# --------------------------------------------------------------------------
# GUI için: BLE'yi ayrı bir iş parçacığında (kendi asyncio döngüsünde) çalıştır
# --------------------------------------------------------------------------


class ThreadedLight:
    """Tk ana iş parçacığını bloklamadan LightClient kullanmayı sağlar."""

    def __init__(self, cfg: lc.Config, events: queue.Queue) -> None:
        self.events = events
        self._loop = asyncio.new_event_loop()
        self.client = lc.LightClient(
            cfg,
            on_state=lambda s: events.put(("state", s)),
            on_status=lambda t: events.put(("status", t)),
            on_log=lambda t: events.put(("log", t)),
        )
        threading.Thread(target=self._run, name="ble", daemon=True).start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def submit(self, coro) -> None:
        async def guarded() -> None:
            try:
                await coro
            except Exception as exc:  # noqa: BLE001 - arayüze Türkçe mesaj ilet
                self.events.put(("error", lc.friendly_error(exc)))

        asyncio.run_coroutine_threadsafe(guarded(), self._loop)

    def shutdown(self) -> None:
        future = asyncio.run_coroutine_threadsafe(self.client.close(), self._loop)
        try:
            future.result(timeout=5)
        except Exception:  # noqa: BLE001
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)


class App:
    def __init__(self, cfg: lc.Config) -> None:
        import tkinter as tk
        from tkinter import colorchooser, ttk

        self.tk, self.ttk, self.colorchooser = tk, ttk, colorchooser
        self.cfg = cfg
        self.events: queue.Queue = queue.Queue()
        self.light = ThreadedLight(cfg, self.events)
        self._timers: dict[str, str] = {}
        self._updating = False
        self._colour_hex = "#ffffff"

        root = self.root = tk.Tk()
        root.title(cfg.name)
        root.minsize(420, 560)
        root.protocol("WM_DELETE_WINDOW", self.close)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)

        # Başlık + bağlantı durumu
        head = ttk.Frame(frame)
        head.pack(fill="x")
        from tkinter import font as tkfont

        title_font = tkfont.nametofont("TkDefaultFont").copy()
        title_font.configure(size=15, weight="bold")
        ttk.Label(head, text=cfg.name, font=title_font).pack(side="left")
        self.dot = tk.Canvas(head, width=14, height=14, highlightthickness=0)
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill="#999999", outline="")
        self.dot.pack(side="right")
        self.status_var = tk.StringVar(value="Bağlanılmadı")
        ttk.Label(head, textvariable=self.status_var).pack(side="right", padx=6)
        self.error_var = tk.StringVar()
        ttk.Label(frame, textvariable=self.error_var, foreground="#b3261e", wraplength=380).pack(
            fill="x", pady=(4, 0)
        )

        # Aç / Kapat
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(12, 4))
        ttk.Button(row, text="Aç", command=lambda: self.light.submit(self.light.client.set_power(True))).pack(
            side="left", expand=True, fill="x", padx=(0, 4)
        )
        ttk.Button(row, text="Kapat", command=lambda: self.light.submit(self.light.client.set_power(False))).pack(
            side="left", expand=True, fill="x", padx=(4, 0)
        )
        self.info_var = tk.StringVar(value="Durum: –")
        ttk.Label(frame, textvariable=self.info_var).pack(anchor="w", pady=(0, 8))

        # Parlaklık
        self.bright_var = tk.DoubleVar(value=50)
        self.bright_label = tk.StringVar(value="Parlaklık: %50")
        ttk.Label(frame, textvariable=self.bright_label).pack(anchor="w")
        self.bright_scale = ttk.Scale(frame, from_=1, to=100, variable=self.bright_var, command=self._on_bright)
        self.bright_scale.pack(fill="x", pady=(0, 10))

        # Beyaz ışık sıcaklığı
        self.temp_var = tk.DoubleVar(value=0)
        self.temp_label = tk.StringVar(value="Beyaz ışık sıcaklığı: %0 (sıcak)")
        ttk.Label(frame, textvariable=self.temp_label).pack(anchor="w")
        self.temp_scale = ttk.Scale(frame, from_=0, to=100, variable=self.temp_var, command=self._on_temp)
        self.temp_scale.pack(fill="x", pady=(0, 10))
        scale_hint = ttk.Frame(frame)
        scale_hint.pack(fill="x")
        ttk.Label(scale_hint, text="Sıcak", foreground="#777").pack(side="left")
        ttk.Label(scale_hint, text="Soğuk", foreground="#777").pack(side="right")

        # Renk
        colour_row = ttk.Frame(frame)
        colour_row.pack(fill="x", pady=(14, 4))
        ttk.Button(colour_row, text="Renk seç…", command=self.pick_colour).pack(side="left")
        self.swatch = tk.Canvas(colour_row, width=28, height=28, highlightthickness=1, highlightbackground="#bbb")
        self.swatch_id = self.swatch.create_rectangle(0, 0, 28, 28, fill=self._colour_hex, outline="")
        self.swatch.pack(side="left", padx=10)
        ttk.Button(colour_row, text="Beyaza dön", command=self.back_to_white).pack(side="right")

        # Araçlar + günlük
        tools = ttk.Frame(frame)
        tools.pack(fill="x", pady=(16, 4))
        ttk.Button(tools, text="Durumu oku", command=lambda: self.light.submit(self.light.client.refresh())).pack(
            side="left"
        )
        ttk.Button(tools, text="Yeniden bağlan", command=lambda: self.light.submit(self.light.client.reconnect())).pack(
            side="left", padx=6
        )
        self.log = tk.Text(frame, height=8, state="disabled", wrap="word", font="TkFixedFont")
        self.log.pack(fill="both", expand=True)

        self.root.after(100, self._poll)
        self.light.submit(self.light.client.connect())

    # -- yardımcılar -------------------------------------------------------

    def _debounce(self, key: str, fn, delay_ms: int = 350) -> None:
        if key in self._timers:
            self.root.after_cancel(self._timers[key])
        self._timers[key] = self.root.after(delay_ms, fn)

    def _log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    # -- kullanıcı eylemleri -------------------------------------------------

    def _on_bright(self, _value: str) -> None:
        pct = round(self.bright_var.get())
        self.bright_label.set(f"Parlaklık: %{pct}")
        if not self._updating:
            self._debounce("bright", lambda: self.light.submit(self.light.client.set_brightness(pct)))

    def _on_temp(self, _value: str) -> None:
        temp = round(self.temp_var.get())
        self.temp_label.set(f"Beyaz ışık sıcaklığı: %{temp} ({'sıcak' if temp < 50 else 'soğuk'})")
        if not self._updating:
            bright = round(self.bright_var.get())
            self._debounce("temp", lambda: self.light.submit(self.light.client.set_white(bright, temp)))

    def pick_colour(self) -> None:
        (rgb, hex_value) = self.colorchooser.askcolor(color=self._colour_hex, title="Renk seç", parent=self.root)
        if rgb is None:
            return
        r, g, b = (int(c) for c in rgb)
        self._set_swatch(hex_value)
        self.light.submit(self.light.client.set_colour_rgb(r, g, b, round(self.bright_var.get())))

    def back_to_white(self) -> None:
        self.light.submit(
            self.light.client.set_white(round(self.bright_var.get()), round(self.temp_var.get()))
        )

    def _set_swatch(self, hex_value: str) -> None:
        self._colour_hex = hex_value
        self.swatch.itemconfigure(self.swatch_id, fill=hex_value)

    # -- olay döngüsü (BLE iş parçacığından gelen bildirimler) ---------------

    def _poll(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                try:
                    getattr(self, f"_on_{kind}_event")(payload)
                except Exception as exc:  # noqa: BLE001 - bir olay döngüyü durdurmasın
                    self._log(f"Arayüz hatası ({kind}): {exc!r}")
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _on_log_event(self, text: str) -> None:
        self._log(text)

    def _on_error_event(self, text: str) -> None:
        self.error_var.set(text)
        self._log("HATA: " + text)

    def _on_status_event(self, text: str) -> None:
        self.status_var.set(text)
        busy = text.endswith("…")
        colour = "#2e7d32" if text == "Bağlı" else "#ef6c00" if busy else "#b3261e"
        self.dot.itemconfigure(self.dot_id, fill=colour)
        if text == "Bağlı":
            self.error_var.set("")

    def _on_state_event(self, st: lc.LightState) -> None:
        power = {True: "Açık", False: "Kapalı", None: "–"}[st.power]
        mode = MODE_NAMES.get(st.mode or "", "–")
        self.info_var.set(f"Durum: {power} · Mod: {mode}")
        self._updating = True
        try:
            if st.mode == "colour" and st.val is not None:
                self.bright_var.set(lc.bright_to_pct(st.val))
            elif st.brightness_pct is not None:
                self.bright_var.set(st.brightness_pct)
            if st.temp_pct is not None:
                self.temp_var.set(st.temp_pct)
            self.bright_label.set(f"Parlaklık: %{round(self.bright_var.get())}")
            temp = round(self.temp_var.get())
            self.temp_label.set(f"Beyaz ışık sıcaklığı: %{temp} ({'sıcak' if temp < 50 else 'soğuk'})")
        finally:
            self._updating = False
        if st.hue is not None and st.sat is not None:
            r, g, b = colorsys.hsv_to_rgb(st.hue / 360, st.sat / 1000, 1.0)
            self._set_swatch(f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}")

    # -- kapanış -----------------------------------------------------------

    def close(self) -> None:
        self.light.shutdown()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


# --------------------------------------------------------------------------
# Komut satırı
# --------------------------------------------------------------------------


def parse_hex_colour(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    if len(value) != 6:
        raise argparse.ArgumentTypeError("Renk 6 haneli hex olmalı, örn. ff8800")
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Geçersiz hex renk") from exc


def percent(value: str) -> int:
    number = int(value)
    if not 0 <= number <= 100:
        raise argparse.ArgumentTypeError("0 ile 100 arasında olmalı")
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Tuya ışık kontrolü (Bluetooth)")
    from version import APP_NAME, __version__

    parser.add_argument("--version", action="version", version=f"{APP_NAME} {__version__}")
    parser.add_argument("-v", "--verbose", action="store_true", help="ayrıntılı günlük")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("gui", help="yeni masaüstü arayüzünü aç (varsayılan)")
    sub.add_parser("eski-gui", help="eski basit tkinter arayüzünü aç")
    p = sub.add_parser("scan", help="çevredeki Tuya BLE cihazlarını listele")
    p.add_argument("--raw", action="store_true", help="ham reklam verisini de göster (hata ayıklama)")
    sub.add_parser("status", help="bağlan ve ışığın bildirdiği DP'leri göster")
    sub.add_parser("on", help="ışığı aç")
    sub.add_parser("off", help="ışığı kapat")
    p = sub.add_parser("brightness", help="parlaklık yüzde 1-100")
    p.add_argument("percent", type=percent)
    p = sub.add_parser("white", help="beyaz mod")
    p.add_argument("brightness", type=percent)
    p.add_argument("temperature", type=percent, help="0 sıcak … 100 soğuk")
    p = sub.add_parser("colour", aliases=["color"], help="renk (hex RGB)")
    p.add_argument("hex", type=parse_hex_colour)
    return parser


async def run_scan(raw: bool = False) -> None:
    try:
        cfg = lc.Config.load()
        own_uuid, own_address = cfg.uuid, cfg.address
    except lc.ConfigError:
        own_uuid, own_address = "", ""
    print("Taranıyor (8 sn)…")
    devices = await lc.scan_tuya_devices(8)
    if not devices:
        print("Hiç Tuya BLE cihazı görünmedi. Bluetooth açık mı? Telefon ışığa bağlıysa kapatın.")
        return
    for d in devices:
        by_uuid = bool(own_uuid) and d.uuid == own_uuid
        by_address = bool(own_address) and lc._norm_address(d.address) == lc._norm_address(own_address)
        if by_uuid or by_address:
            mark = "  <== sizin ışığınız"
        elif d.uuid is None and len(devices) == 1:
            mark = "  <== tek Tuya cihazı: büyük ihtimalle sizin ışığınız (uuid çözülemedi)"
        else:
            mark = ""
        print(f"{d.address}  rssi={d.rssi}  uuid={d.uuid}  product={d.product_id or '(gizli)'}  bound={d.bound}{mark}")
        if raw:
            print(f"    servis verisi   : {d.service_hex}")
            print(f"    üretici verisi  : {d.manufacturer_hex}")


async def run_command(args: argparse.Namespace) -> None:
    cfg = lc.Config.load()
    client = lc.LightClient(cfg, on_status=print, on_log=print if args.verbose else None)
    try:
        match args.cmd:
            case "on":
                await client.set_power(True)
            case "off":
                await client.set_power(False)
            case "brightness":
                await client.set_brightness(args.percent)
            case "white":
                await client.set_white(args.brightness, args.temperature)
            case "colour" | "color":
                await client.set_colour_rgb(*args.hex)
            case "status":
                await client.connect()
                await asyncio.sleep(2.5)  # cihazın DP raporunu bekle
                st = client.state
                print(f"Güç: {st.power}  Mod: {st.mode}  Parlaklık: {st.brightness_pct}  Sıcaklık: {st.temp_pct}")
                print("Ham DP'ler (numara: değer):")
                for identifier, value in sorted(st.raw.items()):
                    print(f"  {identifier}: {value!r}")
                if not st.raw:
                    print("  (cihaz hiç DP bildirmedi; -v ile tekrar deneyin)")
        if args.cmd != "status":
            await asyncio.sleep(0.8)  # komutun cihaza ulaşması için kısa bekleme
            print("Tamam.")
    finally:
        await client.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.WARNING)
    cmd = args.cmd or "gui"
    try:
        if cmd == "scan":
            asyncio.run(run_scan(args.raw))
        elif cmd == "gui":
            import light_app

            return light_app.main()
        elif cmd == "eski-gui":
            try:
                import tkinter  # noqa: F401
            except ImportError:
                print("tkinter bulunamadı. Windows/macOS'ta python.org kurulumunu kullanın; Ubuntu'da: sudo apt install python3-tk")
                return 1
            App(lc.Config.load()).run()
        else:
            asyncio.run(run_command(args))
    except Exception as exc:  # noqa: BLE001
        print(lc.friendly_error(exc))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
