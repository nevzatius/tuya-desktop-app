"""English UI strings. Placeholders use `{name}` and must match the Turkish file."""

STRINGS: dict[str, str] = {
    # -- app ------------------------------------------------------------------------
    "app.already_running": "The app is already running (check the system tray).",
    "app.store_error": "{error}\n\nYou can delete the file and reopen the app.",
    # -- light names ------------------------------------------------------------------
    "device.default_name": "Room light",
    "device.fallback_name": "Light",
    # -- connection status (status pill) --------------------------------------------------
    "status.searching": "Searching for the light…",
    "status.not_found": "Light not found",
    "status.connecting": "Connecting…",
    "status.failed": "Could not connect",
    "status.connected": "Connected",
    "status.closed": "Disconnected",
    "status.no_light": "No light",
    # -- errors ------------------------------------------------------------------------
    "error.config_missing": "{name} not found. Run `python get_credentials.py` first.",
    "error.config_unreadable": "{name} could not be read: {error}",
    "error.config_field": "{name} is missing field(s): {fields}",
    "error.not_found": (
        "Light not found. Is Bluetooth on, are you close to the light, and is the Smart Life app "
        "on your phone disconnected from it? (BLE allows only one connection at a time)"
    ),
    "error.auth_rejected": (
        "The light rejected the key. The local key may be outdated (it changes if you remove the light from "
        "Smart Life and add it again): refresh it with “Add light…” in the menu above. "
        "There may also be other lights of the same model nearby."
    ),
    "error.handshake": (
        "The light did not answer the handshake. The local key may be wrong, or the device does not "
        "support this BLE protocol (not every device with both Wi-Fi and Bluetooth does)."
    ),
    "error.bluetooth": "Bluetooth error: {error}",
    "error.unexpected": "Unexpected error: {error}",
    "error.timeout": "The connection timed out",
    "error.store_unreadable": "{path} could not be read: {error}",
    "error.store_incomplete": "device_id/local_key missing",
    # -- Tuya Cloud --------------------------------------------------------------------
    "cloud.no_tinytuya": "tinytuya is not installed. Reinstall the dependencies (pip install -r requirements.txt).",
    "cloud.id_length": "Access ID must be {length} characters (currently {got}).",
    "cloud.secret_length": "Access Secret must be {length} characters (currently {got}). Characters may have been lost while pasting.",
    "cloud.sign_invalid": "Access ID or Secret is wrong (or belongs to a different region). Copy the values from iot.tuya.com again.",
    "cloud.permission": "The project is not authorized for this action. Make sure the “Smart Home” API services are added to the Cloud project.",
    "cloud.token": "Could not get a session from Tuya Cloud. Check the credentials and your internet connection.",
    "cloud.network": "Could not reach Tuya Cloud. Check your internet connection and try again.",
    "cloud.failed": "Tuya Cloud connection failed: {error}",
    "cloud.unknown_error": "unknown error",
    "cloud.list_failed": "Could not fetch the device list: {error}",
    "cloud.no_devices": (
        "No devices are linked to this project. In the Cloud project, open Devices → Link App Account "
        "and link your Smart Life account with the QR code."
    ),
    "region.eu": "Central Europe",
    "region.eu-w": "Western Europe",
    "region.us": "Western US",
    "region.us-e": "Eastern US",
    "region.in": "India",
    "region.sg": "Singapore",
    "region.cn": "China",
    # -- main window -------------------------------------------------------------------
    "main.no_light_button": "No light  ▾",
    "main.no_light_banner": "No light added yet. Choose “Add light…” from the menu above.",
    "main.add_light": "Add light…",
    "main.rename": "Rename…",
    "main.remove": "Remove this light",
    "main.tab_control": "Control",
    "main.tab_energy": "Energy",
    "main.brightness": "Brightness",
    "main.white": "White",
    "main.colour": "Color",
    "main.temperature": "Light temperature",
    "main.warm": "Warm",
    "main.neutral": "Neutral",
    "main.cool": "Cool",
    "main.presets": "Presets",
    "main.log": "Log",
    "main.reconnect": "Reconnect",
    "main.read_state": "Read status",
    "main.settings": "Settings",
    "main.language": "Language",
    "main.language_auto": "System language",
    "main.language_restart": "The language change takes effect the next time you start the app.",
    "mode.white": "White light",
    "mode.colour": "Color",
    "mode.scene": "Scene",
    "mode.music": "Music",
    "state.on": "On",
    "state.off": "Off",
    "state.tap_to_turn_on": "Tap to turn on",
    "state.waiting": "Waiting for the light",
    # -- presets -----------------------------------------------------------------------
    "preset.reading": "Reading",
    "preset.focus": "Focus",
    "preset.night": "Night",
    "preset.movie": "Movie",
    "preset.romantic": "Romantic",
    "preset.ocean": "Ocean",
    # -- tray --------------------------------------------------------------------------
    "tray.on": "Turn light on",
    "tray.off": "Turn light off",
    "tray.show": "Show window",
    "tray.quit": "Quit",
    "tray.hint": "The app keeps running in the system tray.",
    # -- controller ----------------------------------------------------------------------
    "controller.remove_confirm": "Remove “{name}”? Its key is deleted from this computer (the light itself is untouched).",
    "controller.remove": "Remove",
    "controller.cancel": "Cancel",
    "controller.rename_title": "Rename",
    "controller.rename_label": "Light name:",
    # -- energy ------------------------------------------------------------------------
    "energy.period_day": "TODAY",
    "energy.period_week": "LAST 7 DAYS",
    "energy.period_month": "LAST 30 DAYS",
    "energy.tab_day": "Day",
    "energy.tab_week": "Week",
    "energy.tab_month": "Month",
    "energy.settings_title": "Estimate settings",
    "energy.watts_label": "Light power (at full brightness)",
    "energy.price_label": "Electricity rate",
    "energy.currency_label": "Currency",
    "energy.price_unset": "Not set",
    "energy.price_note": "Enter the per-kWh rate from your electricity bill to see costs.",
    "energy.watts_hint": "The light's power is printed on the packaging or product page (e.g. 9 W).",
    "energy.disclaimer": (
        "These values are <b>estimates</b>: the light does not measure power; the app computes "
        "power × brightness × time on. Usage is only recorded while the app is running and connected "
        "to the light; changes made with the phone or a wall switch while disconnected are not seen."
    ),
    "energy.no_records": "No records",
    "energy.price_needed": "Enter your electricity rate to see costs",
    "energy.detail": "{kwh} · {duration} on",
    "energy.all_lights": "All lights: {cost} · {kwh}",
    "energy.all_lights_nocost": "All lights: {kwh}",
    "energy.tip_duration": "{duration} on",
    "day.0": "Mon",
    "day.1": "Tue",
    "day.2": "Wed",
    "day.3": "Thu",
    "day.4": "Fri",
    "day.5": "Sat",
    "day.6": "Sun",
    "fmt.hours_minutes": "{hours} h {minutes} min",
    "fmt.hours": "{hours} h",
    "fmt.minutes": "{minutes} min",
    # -- add-light wizard ----------------------------------------------------------------
    "setup.title": "Add light",
    "setup.step_of": "Step {current} / {total}",
    "setup.back": "Back",
    "setup.cancel": "Cancel",
    "setup.open_tuya": "Open iot.tuya.com",
    # step 1: welcome
    "setup.welcome_title": "Let's connect your light",
    "setup.welcome_body": (
        "To control your light you need a <b>one-time key</b>. Only your own Tuya account can provide it. "
        "It takes about 10 minutes and you only do it once; afterwards everything works over Bluetooth, "
        "without internet."
    ),
    "setup.welcome_checklist": (
        "<b>Have these ready:</b><br>"
        "• The Smart Life app on your phone, with your light already added<br>"
        "• The light plugged in, switched on and close to you<br>"
        "• Bluetooth on your computer"
    ),
    "setup.start": "Get started",
    # step 2: Tuya account
    "setup.account_title": "Prepare your Tuya account",
    "setup.account_intro": "Do these steps on the Tuya website. You can keep this window open.",
    "setup.account_step1": "<b>1. Create a free account</b> (or log in). It is a developer account, separate from your Smart Life login.",
    "setup.account_step2": (
        "<b>2. Create a project.</b> Cloud → Development → <i>Create Cloud Project</i>. "
        "Industry: <i>Smart Home</i>, Development Method: <i>Smart Home</i>, Data Center: your region."
    ),
    "setup.account_step3": (
        "<b>3. Link your Smart Life account.</b> In the project choose <i>Devices → Link App Account → Add App Account</i> "
        "and scan the QR code with the Smart Life app on your phone (Me → scan icon at the top right)."
    ),
    "setup.account_step4": "<b>4. Copy the keys.</b> You will copy the <i>Access ID</i> and <i>Access Secret</i> from the project's <i>Overview</i> page.",
    "setup.account_trouble": (
        "If you get a “permission” error later, open the project's <i>Service API</i> tab and make sure the "
        "Smart Home related services (e.g. <i>IoT Core</i>) are added."
    ),
    "setup.account_next": "I have my Access ID and Secret",
    # step 3: credentials
    "setup.cred_title": "Enter your keys",
    "setup.cred_intro": "Copy the values from the Overview page. Tip: just copy them, the app picks them up from the clipboard.",
    "setup.chars_20": "20 characters",
    "setup.chars_32": "32 characters",
    "setup.show": "Show",
    "setup.field_status": "{got} / {length}",
    "setup.field_ok": "✓ {got} / {length}",
    "setup.pasted_id": "Access ID pasted from the clipboard.",
    "setup.pasted_secret": "Access Secret pasted from the clipboard.",
    "setup.advanced": "Advanced  ▾",
    "setup.region": "Data center",
    "setup.region_auto": "Automatic (recommended)",
    "setup.region_hint": "With Automatic your region is guessed first; if that fails the others are tried in turn.",
    "setup.manual_button": "I'll enter the key manually",
    "setup.find": "Find my lights",
    "setup.connecting": "Connecting to Tuya Cloud…",
    "setup.retry": "Try again",
    # step 4: choose lights
    "setup.lights_title": "Choose and name your lights",
    "setup.lights_hint": "Tick the lights you want to add and give each one a name you will recognize.",
    "setup.name_placeholder": "Light name",
    "setup.scan": "Scan for lights near me",
    "setup.scanning": "Scanning for nearby Bluetooth lights…",
    "setup.scan_found": "Found {count} Tuya Bluetooth device(s) nearby.",
    "setup.scan_none": "No Tuya Bluetooth devices found nearby. Is the light on, is Bluetooth on, and is the Smart Life app on your phone disconnected from the light?",
    "setup.scan_failed": "Scan failed: {error}",
    "setup.nearby": "nearby · {signal} signal",
    "setup.signal_strong": "strong",
    "setup.signal_good": "good",
    "setup.signal_weak": "weak",
    "setup.not_seen": "not seen nearby",
    "setup.scan_unmatched": "{count} more device(s) do not match your account (strongest signal: {signal}); some may simply be unidentifiable, and “Blink” still finds the right light.",
    "setup.blink": "Blink",
    "setup.blink_hint": "Several lights nearby? Press “Blink” to see which one is which.",
    "setup.blinking": "Connecting to the light, it will blink…",
    "setup.blink_done": "Did it blink? Then that's this light. It went back to its previous state.",
    "setup.blink_failed": "Could not blink the light: {error}",
    "setup.add_selected": "Add selected lights",
    "setup.not_light": "not a light",
    "setup.already_added": "already added, key will be updated",
    "setup.experimental": "experimental",
    "setup.experimental_note": "“Experimental” devices may not use the standard light commands; if one does not work, check the log.",
    "setup.pick_one": "Tick at least one device first.",
    # manual entry (advanced)
    "setup.manual_title": "Enter the key manually",
    "setup.manual_intro": "Use this if you already got these details from Tuya Cloud or another tool.",
    "setup.manual_name_placeholder": "e.g. Living room",
    "setup.field_name": "Name",
    "setup.field_device_id": "Device ID",
    "setup.field_local_key": "Local key",
    "setup.field_uuid": "UUID",
    "setup.add": "Add",
    "setup.manual_required": "Device ID and local key are required.",
    # done
    "setup.done_title": "You're all set",
    "setup.done_body": "{names} added. The app will now connect to the light over Bluetooth. You won't need these steps again.",
    "setup.done_button": "Open the app",
}
