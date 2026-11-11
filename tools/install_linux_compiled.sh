#!/usr/bin/env bash
# Install WOP on Linux like tools/install_linux.sh, and then compile the hot core with mypyc (planning is about twice as fast).
# Tested on nothing yet: written 2026-11-02 for a first try on the lathe PC.
#
#   tools/install_linux_compiled.sh                  install (or update) and compile
#   tools/install_linux_compiled.sh --prefix DIR     install somewhere else (default: ~/.local/share/wop)
#   tools/install_linux_compiled.sh --uninstall      remove the program (the same as install_linux.sh --uninstall)
#   tools/install_linux_compiled.sh --no-desktop-icon, --dry-run    as for install_linux.sh
#
# It needs everything install_linux.sh needs, and a C compiler and the Python headers (Debian: sudo apt install gcc python3-dev).
# If the compiling does not work, the plain install stays and works (only slower), and the script says why. To go back to the plain
# install, run tools/install_linux.sh again: it removes the compiled files. Run it as your normal user, never with sudo.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/.." && pwd)"
PREFIX="${XDG_DATA_HOME:-$HOME/.local/share}/wop"
DRY_RUN=0
UNINSTALL=0
ARGUMENTS=("$@")

while [ $# -gt 0 ]; do
  case "$1" in
    --prefix) case "$2" in /*) PREFIX="$2" ;; *) PREFIX="$PWD/$2" ;; esac; shift 2 ;;
    --uninstall) UNINSTALL=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-desktop-icon) shift ;;
    -h|--help) sed -n '2,12p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 2 ;;
  esac
done

run() {  # print the command; run it unless --dry-run
  echo "+ $*"
  if [ "$DRY_RUN" -eq 0 ]; then "$@"; fi
}

# 1. The plain install (it also removes the compiled files of an earlier run, so a new version never meets an old compiled file).
bash "$HERE/install_linux.sh" ${ARGUMENTS[@]+"${ARGUMENTS[@]}"}
if [ "$UNINSTALL" -eq 1 ]; then exit 0; fi

# 2. The compiling. Whatever goes wrong here leaves the plain install as it is.
VENV_PYTHON="$PREFIX/venv/bin/python"
fail() {
  echo >&2
  echo "NOT COMPILED: $1" >&2
  echo "WOP is installed and works as plain Python (planning is slower). Fix the cause and run this script again." >&2
  exit 3
}

echo
echo "Compiling the core with mypyc (about a minute)"
if [ "$DRY_RUN" -eq 0 ]; then
  command -v gcc >/dev/null 2>&1 || command -v cc >/dev/null 2>&1 || fail "there is no C compiler. On Debian: sudo apt install gcc python3-dev"
  "$VENV_PYTHON" -c 'import os, sys, sysconfig; sys.exit(0 if os.path.exists(os.path.join(sysconfig.get_paths()["include"], "Python.h")) else 1)' \
    || fail "the Python headers are missing (Python.h). On Debian: sudo apt install python3-dev"
fi
run "$VENV_PYTHON" -m pip install --upgrade mypy setuptools

# mypyc builds next to the sources, so it builds in a copy: nothing is written into the repository.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
SRC="$WORK/src"
run mkdir -p "$SRC/tools"
run cp -r "$REPO/wop" "$SRC/"
run cp "$REPO/tools/build_compiled.py" "$SRC/tools/"
run find "$SRC" -name __pycache__ -type d -prune -exec rm -rf {} +
if [ "$DRY_RUN" -eq 0 ]; then
  (cd "$SRC" && "$VENV_PYTHON" tools/build_compiled.py) || fail "the build did not finish; the messages above say why"
  # The compiled files go to the same places in the installed package: the modules next to their sources, the shared support file
  # (wop_compiled__mypyc...) next to the folder wop.
  SITE="$("$VENV_PYTHON" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
  [ -d "$SITE/wop" ] || fail "the installed package was not found in $SITE"
  COUNT=0
  while IFS= read -r -d '' FILE; do
    RELATIVE="${FILE#"$SRC"/}"
    mkdir -p "$SITE/$(dirname "$RELATIVE")"
    cp "$FILE" "$SITE/$RELATIVE"
    COUNT=$((COUNT + 1))
  done < <({ find "$SRC/wop" -name '*.so' -print0; find "$SRC" -maxdepth 1 -name '*.so' -print0; })
  [ "$COUNT" -gt 0 ] || fail "the build made no compiled file"
  echo "copied $COUNT compiled files into $SITE"
  # Is Python really taking the compiled file? (it would say .py when not)
  USED="$(cd "$WORK" && "$VENV_PYTHON" -c 'import wop.core.geometry.primitives as m; print(m.__file__)')"
  case "$USED" in
    *.so) echo "The core is compiled: $USED" ;;
    *) fail "Python still takes the plain file ($USED)" ;;
  esac
  echo "Self-test (no window is opened):"
  if (cd "$WORK" && QT_QPA_PLATFORM=offscreen "$VENV_PYTHON" "$PREFIX/app/wop_app.py" --selftest); then
    echo "The self-test is fine."
  else
    fail "the self-test failed with the compiled files; run tools/install_linux.sh to go back to the plain install"
  fi
else
  echo "+ build in $SRC, copy the compiled files into the installed package, check and self-test"
fi
echo
if [ "$DRY_RUN" -eq 0 ]; then
  echo "Done: WOP is installed with the compiled core (start it like the plain one: wop)."
else
  echo "Dry run: nothing was done."
fi
