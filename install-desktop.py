#!/usr/bin/env python3
"""Install JobTrail as a clickable desktop app on your own machine.

Run this once, locally, after cloning the repo:

    python3 install-desktop.py            # create the desktop icon
    python3 install-desktop.py --uninstall

It detects your OS and creates a native launcher:

  * Linux   -> a .desktop entry in your app menu and on your Desktop
  * macOS   -> a JobTrail.app bundle in ~/Applications (+ a Desktop alias)
  * Windows -> a JobTrail shortcut (.lnk) on your Desktop

Clicking it starts the local server and opens JobTrail in your browser.

Privacy: the launcher points at THIS checkout. Your jobs, uploaded files, and
Google credentials stay in the git-ignored ``data/`` directory and are never
copied anywhere public. The icons it generates are written to ``assets/`` and
are also git-ignored, so open-sourcing the repo leaks nothing personal.

Zero third-party dependencies — standard library only.
"""

from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"
LAUNCHER = ROOT / "bin" / "jobtrail-app"
APP_NAME = "JobTrail"


def _ensure_icons():
    """Render icon-*.png and icon.ico into assets/ (idempotent)."""
    sys.path.insert(0, str(ASSETS))
    import icongen  # noqa: WPS433  (local stdlib-only module)

    return icongen.build(ASSETS)


def _desktop_dir() -> Path | None:
    # Honour XDG user dirs if configured, else ~/Desktop.
    cfg = Path.home() / ".config" / "user-dirs.dirs"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            if line.startswith("XDG_DESKTOP_DIR"):
                val = line.split("=", 1)[1].strip().strip('"')
                val = val.replace("$HOME", str(Path.home()))
                p = Path(val)
                if p.is_dir():
                    return p
    d = Path.home() / "Desktop"
    return d if d.is_dir() else None


# --------------------------------------------------------------------------- #
# Linux
# --------------------------------------------------------------------------- #
def install_linux(icons):
    icon_path = icons["png"]
    py = sys.executable or "python3"
    entry = (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Version=1.0\n"
        f"Name={APP_NAME}\n"
        "Comment=Local-first job application tracker\n"
        f"Exec={py} {LAUNCHER}\n"
        f"Path={ROOT}\n"
        f"Icon={icon_path}\n"
        "Terminal=false\n"
        "Categories=Office;Utility;\n"
        "StartupNotify=true\n"
    )

    apps = Path.home() / ".local" / "share" / "applications"
    apps.mkdir(parents=True, exist_ok=True)
    menu_file = apps / "jobtrail.desktop"
    menu_file.write_text(entry, encoding="utf-8")
    menu_file.chmod(0o755)

    made = [menu_file]
    desk = _desktop_dir()
    if desk:
        desk_file = desk / "jobtrail.desktop"
        desk_file.write_text(entry, encoding="utf-8")
        desk_file.chmod(0o755)
        # GNOME requires desktop launchers to be marked trusted.
        if shutil.which("gio"):
            subprocess.run(
                ["gio", "set", str(desk_file), "metadata::trusted", "true"],
                check=False,
            )
        made.append(desk_file)

    if shutil.which("update-desktop-database"):
        subprocess.run(["update-desktop-database", str(apps)], check=False)

    print(f"Installed {APP_NAME} launcher:")
    for m in made:
        print(f"  • {m}")
    print("\nIt's in your applications menu" + (" and on your Desktop." if desk else "."))
    print("If the Desktop icon shows a prompt the first time, choose "
          '"Allow Launching" / "Trust".')


def uninstall_linux():
    removed = []
    for p in [
        Path.home() / ".local" / "share" / "applications" / "jobtrail.desktop",
        (_desktop_dir() or Path("/nonexistent")) / "jobtrail.desktop",
    ]:
        if p.is_file():
            p.unlink()
            removed.append(p)
    _report_removed(removed)


# --------------------------------------------------------------------------- #
# macOS
# --------------------------------------------------------------------------- #
def _build_icns(icons, resources: Path) -> str | None:
    """Build AppIcon.icns from the PNGs using sips/iconutil. Returns icon filename."""
    if not (shutil.which("iconutil") and shutil.which("sips")):
        # Fall back to a plain PNG (shows a generic icon on some macOS versions).
        shutil.copy(icons["png"], resources / "icon.png")
        return None
    iconset = resources / "AppIcon.iconset"
    iconset.mkdir(parents=True, exist_ok=True)
    mapping = {
        "icon_16x16.png": 16, "icon_16x16@2x.png": 32,
        "icon_32x32.png": 32, "icon_32x32@2x.png": 64,
        "icon_128x128.png": 128, "icon_128x128@2x.png": 256,
        "icon_256x256.png": 256, "icon_256x256@2x.png": 512,
        "icon_512x512.png": 512,
    }
    for name, size in mapping.items():
        src = icons.get(f"png{size}", icons["png"])
        shutil.copy(src, iconset / name)
    subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(resources / "AppIcon.icns")],
        check=False,
    )
    shutil.rmtree(iconset, ignore_errors=True)
    return "AppIcon" if (resources / "AppIcon.icns").is_file() else None


def install_macos(icons):
    apps = Path.home() / "Applications"
    apps.mkdir(parents=True, exist_ok=True)
    bundle = apps / f"{APP_NAME}.app"
    macos = bundle / "Contents" / "MacOS"
    resources = bundle / "Contents" / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)

    icon_name = _build_icns(icons, resources)
    py = sys.executable or "python3"

    launcher = macos / APP_NAME
    launcher.write_text(
        "#!/bin/bash\n"
        f'exec "{py}" "{LAUNCHER}"\n',
        encoding="utf-8",
    )
    launcher.chmod(0o755)

    icon_line = f"  <key>CFBundleIconFile</key>\n  <string>{icon_name}</string>\n" if icon_name else ""
    plist = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n<dict>\n'
        f"  <key>CFBundleName</key>\n  <string>{APP_NAME}</string>\n"
        f"  <key>CFBundleDisplayName</key>\n  <string>{APP_NAME}</string>\n"
        f"  <key>CFBundleExecutable</key>\n  <string>{APP_NAME}</string>\n"
        "  <key>CFBundleIdentifier</key>\n  <string>dev.jobtrail.app</string>\n"
        "  <key>CFBundlePackageType</key>\n  <string>APPL</string>\n"
        "  <key>CFBundleShortVersionString</key>\n  <string>1.0</string>\n"
        "  <key>LSMinimumSystemVersion</key>\n  <string>10.13</string>\n"
        "  <key>LSUIElement</key>\n  <true/>\n"
        f"{icon_line}"
        "</dict>\n</plist>\n"
    )
    (bundle / "Contents" / "Info.plist").write_text(plist, encoding="utf-8")

    print(f"Installed {bundle}")
    desk = _desktop_dir()
    if desk:
        alias = desk / f"{APP_NAME}.app"
        if alias.exists() or alias.is_symlink():
            alias.unlink()
        os.symlink(bundle, alias)
        print(f"Added a Desktop alias: {alias}")
    print("\nDouble-click JobTrail in Applications (or on your Desktop) to launch.")
    print('First launch: if macOS blocks it, right-click → Open → Open.')


def uninstall_macos():
    removed = []
    bundle = Path.home() / "Applications" / f"{APP_NAME}.app"
    if bundle.exists():
        shutil.rmtree(bundle, ignore_errors=True)
        removed.append(bundle)
    desk = _desktop_dir()
    if desk:
        alias = desk / f"{APP_NAME}.app"
        if alias.exists() or alias.is_symlink():
            alias.unlink()
            removed.append(alias)
    _report_removed(removed)


# --------------------------------------------------------------------------- #
# Windows
# --------------------------------------------------------------------------- #
def _pythonw() -> str:
    exe = Path(sys.executable)
    cand = exe.with_name("pythonw.exe")
    return str(cand if cand.is_file() else exe)


def install_windows(icons):
    desk = _desktop_dir() or (Path.home() / "Desktop")
    desk.mkdir(parents=True, exist_ok=True)
    lnk = desk / f"{APP_NAME}.lnk"
    ico = icons["ico"]
    target = _pythonw()

    ps = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('{lnk}');"
        "$s.TargetPath = '{target}';"
        "$s.Arguments = '\"{launcher}\"';"
        "$s.WorkingDirectory = '{root}';"
        "$s.IconLocation = '{ico}';"
        "$s.Description = 'Local-first job application tracker';"
        "$s.Save()"
    ).format(lnk=lnk, target=target, launcher=LAUNCHER, root=ROOT, ico=ico)

    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
        check=True,
    )
    print(f"Installed shortcut: {lnk}")
    print("\nDouble-click JobTrail on your Desktop to launch.")


def uninstall_windows():
    desk = _desktop_dir() or (Path.home() / "Desktop")
    lnk = desk / f"{APP_NAME}.lnk"
    removed = []
    if lnk.is_file():
        lnk.unlink()
        removed.append(lnk)
    _report_removed(removed)


# --------------------------------------------------------------------------- #
def _report_removed(removed):
    if removed:
        print("Removed:")
        for r in removed:
            print(f"  • {r}")
    else:
        print("Nothing to remove.")


def main():
    ap = argparse.ArgumentParser(description="Install JobTrail as a desktop app.")
    ap.add_argument("--uninstall", action="store_true", help="Remove the launcher.")
    args = ap.parse_args()

    system = platform.system()

    if args.uninstall:
        {"Linux": uninstall_linux, "Darwin": uninstall_macos, "Windows": uninstall_windows}.get(
            system, lambda: print(f"Unsupported OS: {system}")
        )()
        return

    if not LAUNCHER.is_file():
        sys.exit(f"Launcher not found: {LAUNCHER}")

    print("Generating app icons (stdlib renderer)…")
    icons = _ensure_icons()

    if system == "Linux":
        install_linux(icons)
    elif system == "Darwin":
        install_macos(icons)
    elif system == "Windows":
        install_windows(icons)
    else:
        sys.exit(f"Unsupported OS: {system}. See docs/DESKTOP_APP.md to set it up by hand.")


if __name__ == "__main__":
    main()
