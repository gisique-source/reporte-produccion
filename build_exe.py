"""Genera el ejecutable de escritorio con PyInstaller."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
DIST = ROOT / "dist"
DESKTOP = Path.home() / "Desktop"
EXE_NAME = "Extrusora reporte de produccion"
LOGO_EXE = ROOT / "public" / "logo-exe.jpg"
ICON_ICO = BUILD / "app_icon.ico"
ICON_SIZES = (16, 32, 48, 64, 128, 256)


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])


def _icon_layer(source, size: int):
    """Escala manteniendo proporción y centra en un cuadrado (sin deformar)."""
    from PIL import Image

    canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    w, h = source.size
    scale = min(size / w, size / h)
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    resized = source.resize((nw, nh), Image.Resampling.LANCZOS)
    x = (size - nw) // 2
    y = (size - nh) // 2
    if resized.mode == "RGBA":
        canvas.paste(resized, (x, y), resized)
    else:
        canvas.paste(resized, (x, y))
    return canvas


def make_icon() -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    if not LOGO_EXE.is_file():
        raise FileNotFoundError(f"No se encontró el logo del ejecutable: {LOGO_EXE}")
    from PIL import Image

    source = Image.open(LOGO_EXE).convert("RGBA")
    layers = [_icon_layer(source, size) for size in ICON_SIZES]
    layers[0].save(
        ICON_ICO,
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
        append_images=layers[1:],
    )
    return ICON_ICO


def build() -> Path:
    ensure_pyinstaller()
    icon = make_icon()
    sep = os.pathsep
    add_data = [
        f"etiqueta_layout.json{sep}.",
        f"public{os.sep}logo.png{sep}public",
    ]
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        f"--name={EXE_NAME}",
        f"--icon={icon}",
        "--hidden-import=win32print",
        "--hidden-import=win32ui",
        "--hidden-import=win32con",
        "--hidden-import=win32api",
        "--hidden-import=tkinterdnd2",
        "--hidden-import=PIL.ImageWin",
        "--hidden-import=openpyxl",
        "--hidden-import=reportlab",
        "--hidden-import=matplotlib.backends.backend_tkagg",
        "--collect-submodules=barcode",
        "--collect-submodules=tkinterdnd2",
        "--collect-data=barcode",
    ]
    for item in add_data:
        cmd.append(f"--add-data={item}")
    cmd.append(str(ROOT / "app.py"))

    print("Ejecutando:", " ".join(cmd))
    subprocess.check_call(cmd, cwd=ROOT)
    exe = DIST / f"{EXE_NAME}.exe"
    if not exe.is_file():
        raise FileNotFoundError(f"No se generó el ejecutable: {exe}")
    return exe


def create_desktop_shortcut(exe: Path, icon: Path) -> Path:
    """Crea un acceso directo en el escritorio hacia el .exe en dist/."""
    DESKTOP.mkdir(parents=True, exist_ok=True)
    link = DESKTOP / f"{EXE_NAME}.lnk"
    try:
        import win32com.client

        shell = win32com.client.Dispatch("WScript.Shell")
        shortcut = shell.CreateShortCut(str(link))
        shortcut.Targetpath = str(exe.resolve())
        shortcut.WorkingDirectory = str(exe.parent.resolve())
        shortcut.IconLocation = str(icon.resolve())
        shortcut.Description = "Extrusora — reporte de producción Gexim"
        shortcut.save()
    except Exception:
        # Fallback sin pywin32: enlace simbólico .exe (Windows 10+)
        if link.is_file():
            link.unlink()
        os.symlink(str(exe.resolve()), str(link))
    # Evitar BD duplicada en escritorio: el .exe usa C:\Proyecto\precix-weight\pesajes.db
    stray_db = DESKTOP / "pesajes.db"
    if stray_db.is_file():
        try:
            stray_db.unlink()
            print(f"Eliminada BD duplicada del escritorio: {stray_db}")
        except OSError as exc:
            print(f"No se pudo eliminar {stray_db}: {exc}")
    return link


def main() -> None:
    exe = build()
    shortcut = create_desktop_shortcut(exe, ICON_ICO)
    print(f"\nEjecutable: {exe}")
    print(f"Acceso directo escritorio: {shortcut}")
    print(f"Ruta para enlace manual: {exe.resolve()}")


if __name__ == "__main__":
    main()
