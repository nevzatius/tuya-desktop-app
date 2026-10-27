"""assets/app.ico ve assets/app.png dosyalarını üretir (Pillow gerekmez)."""

from __future__ import annotations

import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QBuffer, QByteArray, QIODevice  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

from ui.icons import SIZES, render_icon  # noqa: E402

OUT = Path(__file__).resolve().parent / "assets"


def png_bytes(size: int) -> bytes:
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    render_icon(size).save(buf, "PNG")
    buf.close()
    return bytes(data)


def main() -> int:
    app = QGuiApplication(sys.argv)  # noqa: F841
    OUT.mkdir(exist_ok=True)
    images = [(s, png_bytes(s)) for s in SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries, blobs = b"", b""
    for size, blob in images:
        dim = 0 if size >= 256 else size
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(blob), offset)
        blobs += blob
        offset += len(blob)
    (OUT / "app.ico").write_bytes(header + entries + blobs)
    (OUT / "app.png").write_bytes(png_bytes(256))
    print("Yazıldı:", OUT / "app.ico", "ve", OUT / "app.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
