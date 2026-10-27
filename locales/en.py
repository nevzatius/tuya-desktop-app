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
    "setup.intro": (
        "To control a Tuya / Smart Life light over Bluetooth you need a light-specific "
        "<b>local key</b>. Only the Tuya account the light is linked to can provide it; "
        "once you have it, the app works without internet."
    ),
    "setup.cloud_button": "Get it from my Tuya account (recommended)",
    "setup.manual_button": "I'll enter the key manually (advanced)",
    "setup.cancel": "Cancel",
    "setup.cloud_title": "Add with Tuya Cloud",
    "setup.how": "How do I get these?  ▾",
    "setup.cloud_help": (
        "<b>One-time setup (about 10 minutes)</b><br>"
        "1. Create a free account at <a href='https://iot.tuya.com'>iot.tuya.com</a>.<br>"
        "2. Cloud → Development → <i>Create Cloud Project</i>. Industry: <i>Smart Home</i>, "
        "Development Method: <i>Smart Home</i>, Data Center: your region.<br>"
        "3. Paste the <i>Access ID</i> and <i>Access Secret</i> from the project's <i>Overview</i> page below.<br>"
        "4. In the project open <i>Devices → Link App Account → Add App Account</i> and scan the QR code "
        "with the Smart Life app on your phone (Me → scan icon at the top right). Your lights are linked to the project.<br>"
        "Your details are stored only on this computer; the Access Secret is never saved."
    ),
    "setup.chars_20": "20 characters",
    "setup.chars_32": "32 characters",
    "setup.show": "Show",
    "setup.region": "Region",
    "setup.back": "Back",
    "setup.find": "Find lights",
    "setup.connecting": "Connecting to Tuya Cloud…",
    "setup.results_title": "Devices found",
    "setup.results_hint": "Tick the ones you want to add.",
    "setup.add_selected": "Add selected",
    "setup.not_light": "(not a light)",
    "setup.already_added": "(already added, key will be updated)",
    "setup.experimental": "(experimental)",
    "setup.experimental_note": "“Experimental” devices may not use the standard light commands; if one does not work, check the log.",
    "setup.pick_one": "Tick at least one device first.",
    "setup.manual_title": "Enter the key manually",
    "setup.manual_intro": "Use this if you already got these details from Tuya Cloud or another tool.",
    "setup.name_placeholder": "e.g. Living room",
    "setup.field_name": "Name",
    "setup.field_device_id": "Device ID",
    "setup.field_local_key": "Local key",
    "setup.field_uuid": "UUID",
    "setup.add": "Add",
    "setup.manual_required": "Device ID and local key are required.",
}
