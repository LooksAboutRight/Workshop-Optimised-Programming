#!/usr/bin/env bash
# Install WOP on Linux into its own virtual environment, from this repository (tested on Debian 13 only).
#
#   tools/install_linux.sh                  install (or update) for this user: no root needed
#   tools/install_linux.sh --prefix DIR     install somewhere else (default: ~/.local/share/wop)
#   tools/install_linux.sh --uninstall      remove the program, the start command and the shortcuts (your settings stay)
#   tools/install_linux.sh --no-desktop-icon   do not put a shortcut on the desktop (the entry in the application menu stays)
#   tools/install_linux.sh --dry-run        only print what would be done
#
# It needs Python 3.11 or newer with the venv module (Debian: sudo apt install python3 python3-venv python3-pip), the system
# libraries of the Qt window (Debian: sudo apt install libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0
# libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libegl1 libgl1 libfontconfig1 libdbus-1-3; without them
# the window does not open) and an internet connection for pip (ezdxf, numpy, PySide6; about 250 MB). The program then starts with `wop` (in ~/.local/bin) or from
# the application menu. The core is not compiled in this install (planning is about twice as slow); tools/install_linux_compiled.sh does the
# same and compiles it. Running this script again removes compiled files an earlier run of that one left in the installed package.
# Settings, machines and libraries are kept in ~/.config/WOP (XDG_CONFIG_HOME).

set -euo pipefail

PYTHON="${PYTHON:-python3}"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/wop"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
XCB_PACKAGES="libxcb-cursor0 libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libegl1 libgl1 libfontconfig1 libdbus-1-3"  # Debian packages the Qt xcb plug-in needs
DRY_RUN=0
UNINSTALL=0
DESKTOP_ICON=1

usage() { sed -n '2,17p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) case "$2" in /*) PREFIX="$2" ;; *) PREFIX="$PWD/$2" ;; esac; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-desktop-icon) DESKTOP_ICON=0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage >&2; exit 2 ;;
  esac
done

LAUNCHER="$BIN_DIR/wop"
DESKTOP_FILE="$DESKTOP_DIR/wop.desktop"
DESKTOP_FOLDER="$(xdg-user-dir DESKTOP 2>/dev/null || true)"  # where the desktop icons are (not always ~/Desktop)
[ -n "$DESKTOP_FOLDER" ] || DESKTOP_FOLDER="$HOME/Desktop"
DESKTOP_COPY="$DESKTOP_FOLDER/wop.desktop"

run() {  # print the command; run it unless --dry-run
  echo "+ $*"
  if [ "$DRY_RUN" -eq 0 ]; then "$@"; fi
}

if [ "$UNINSTALL" -eq 1 ]; then
  run rm -rf "$PREFIX"
  run rm -f "$LAUNCHER" "$DESKTOP_FILE" "$DESKTOP_COPY"
  echo "WOP is removed. Your settings, machines and libraries are still in ${XDG_CONFIG_HOME:-$HOME/.config}/WOP (delete that folder too if you want)."
  exit 0
fi

# --- checks ---------------------------------------------------------------------------------------------------------------------
if [ "$(id -u)" -eq 0 ] && [ "$DRY_RUN" -eq 0 ]; then
  echo "Do not run this as root (su, sudo): the program would be installed for root, and root cannot open a window on your desktop." >&2
  echo "Use root only for apt (sudo apt install python3-venv ...), then run this script and WOP as the user who is logged in to the desktop." >&2
  exit 1
fi
if ! command -v "$PYTHON" >/dev/null 2>&1; then
  echo "Python is not installed ($PYTHON). On Debian: sudo apt install python3 python3-venv python3-pip" >&2
  exit 1
fi
if ! "$PYTHON" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
  echo "WOP needs Python 3.11 or newer; this is $("$PYTHON" --version 2>&1)." >&2
  exit 1
fi
if ! "$PYTHON" -c 'import venv, ensurepip' >/dev/null 2>&1; then
  echo "The venv module is missing. On Debian: sudo apt install python3-venv python3-pip" >&2
  exit 1
fi
if [ ! -f "$REPO/pyproject.toml" ] || [ ! -f "$REPO/tools/wop_app.py" ]; then
  echo "This script must stay inside the WOP repository (tools/install_linux.sh); $REPO is not it." >&2
  exit 1
fi
# The window needs these system libraries. The self-test below runs without a window and does not notice when they are missing.
if command -v dpkg >/dev/null 2>&1; then
  MISSING_PACKAGES=""
  for PACKAGE in $XCB_PACKAGES; do
    dpkg -s "$PACKAGE" >/dev/null 2>&1 || MISSING_PACKAGES="$MISSING_PACKAGES $PACKAGE"
  done
  if [ -n "$MISSING_PACKAGES" ]; then
    echo "These system packages are missing; WOP is installed, but its window does not open without them:" >&2
    echo "  sudo apt install$MISSING_PACKAGES" >&2
    echo "(as root or with sudo; this script itself must run as your normal user)" >&2
  fi
fi

# --- install --------------------------------------------------------------------------------------------------------------------
echo "Installing WOP from $REPO into $PREFIX"
# pip builds from a copy in a temporary folder: nothing is written into the repository (a build folder left there by root, or in a
# read-only folder, makes "could not build wheel").
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SRC="$WORK/src"
run mkdir -p "$SRC" "$PREFIX/app" "$BIN_DIR" "$DESKTOP_DIR"
run cp -r "$REPO/wop" "$REPO/pyproject.toml" "$REPO/LICENSE" "$REPO/THIRD_PARTY_NOTICES.md" "$SRC/"
run find "$SRC" -name __pycache__ -type d -prune -exec rm -rf {} +
run "$PYTHON" -m venv "$PREFIX/venv"
if [ -d "$PREFIX/venv" ]; then  # compiled files of tools/install_linux_compiled.sh: pip does not know them, an old one would hide a new .py
  run find "$PREFIX/venv" \( -path '*/site-packages/wop/*.so' -o -path '*/site-packages/wop_compiled__mypyc*.so' \) -delete
fi
run "$PREFIX/venv/bin/python" -m pip install --upgrade pip
run "$PREFIX/venv/bin/python" -m pip install --upgrade "$SRC[gui]"
run cp "$REPO/tools/wop_app.py" "$PREFIX/app/wop_app.py"

if [ "$DRY_RUN" -eq 0 ]; then
  cat > "$LAUNCHER" <<EOF
#!/usr/bin/env bash
if [ -z "\${DISPLAY:-}\${WAYLAND_DISPLAY:-}" ]; then
  echo "WOP needs a desktop session (DISPLAY is empty). Start it as the user who is logged in to the desktop, not with su or sudo." >&2
  exit 1
fi
exec "$PREFIX/venv/bin/python" "$PREFIX/app/wop_app.py" "\$@"
EOF
  chmod +x "$LAUNCHER"
  cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Type=Application
Name=WOP
Comment=Workshop Optimised Programming for CNC lathes
Exec="$LAUNCHER" %f
Icon=applications-engineering
Terminal=false
Categories=Development;Engineering;
StartupNotify=true
EOF
  chmod +x "$DESKTOP_FILE"
  if command -v update-desktop-database >/dev/null 2>&1; then update-desktop-database "$DESKTOP_DIR" >/dev/null 2>&1 || true; fi
  if command -v desktop-file-validate >/dev/null 2>&1; then desktop-file-validate "$DESKTOP_FILE" || echo "(the menu entry has a note, see above; it may still work)"; fi
  if [ "$DESKTOP_ICON" -eq 1 ] && [ -d "$DESKTOP_FOLDER" ]; then
    cp "$DESKTOP_FILE" "$DESKTOP_COPY"
    chmod +x "$DESKTOP_COPY"
    gio set "$DESKTOP_COPY" metadata::trusted true >/dev/null 2>&1 || true  # GNOME: the icon may be started
  fi
else
  echo "+ write $LAUNCHER and $DESKTOP_FILE"
fi

# --- check the install ----------------------------------------------------------------------------------------------------------
if [ "$DRY_RUN" -eq 0 ]; then
  echo "Self-test (no window is opened):"
  if (cd "$WORK" && QT_QPA_PLATFORM=offscreen "$PREFIX/venv/bin/python" "$PREFIX/app/wop_app.py" --selftest); then
    echo "The self-test is fine."
  else
    echo "The self-test FAILED: the messages above say which part is missing." >&2
    exit 1
  fi
  # The window itself needs the Qt xcb plug-in and the system libraries it uses: say which are missing.
  XCB="$(find "$PREFIX/venv" -name libqxcb.so 2>/dev/null | head -n 1)"
  if [ -n "$XCB" ] && command -v ldd >/dev/null 2>&1; then
    MISSING="$(ldd "$XCB" 2>/dev/null | grep 'not found' | sed 's/^[[:space:]]*\([^ ]*\).*/\1/' | sort -u || true)"
    if [ -n "$MISSING" ]; then
      echo "The window needs system libraries that this computer does not have:" >&2
      echo "$MISSING" | sed 's/^/  /' >&2
      echo "On Debian: sudo apt install $XCB_PACKAGES" >&2
      echo "(then start WOP again; apt-file search <library> tells the package of a library that is still missing)" >&2
    fi
  fi
fi
echo
echo "Done. WOP is installed here:"
echo "  program and its Python environment: $PREFIX"
echo "  start command:                      $LAUNCHER   (type  wop  in a terminal when ~/.local/bin is in your PATH)"
echo "  application menu entry:             $DESKTOP_FILE   (search for WOP; it may take a log-out and log-in to show)"
if [ "$DESKTOP_ICON" -eq 1 ]; then
  echo "  desktop icon:                       $DESKTOP_COPY   (on GNOME: right click > Allow Launching, once)"
fi
echo "  your settings, machines, libraries: ${XDG_CONFIG_HOME:-$HOME/.config}/WOP"
