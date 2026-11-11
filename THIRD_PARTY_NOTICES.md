# Third-party software in WOP

WOP itself is under the MIT licence (the file `LICENSE`). It uses the programs below. The Windows folder build (`dist\WOP`, made by
`tools/build_exe.py`) contains them; the source and the Linux install (`tools/install_linux.sh`) load them from pip. This file says what
they are, under which licence, and where their source and full licence text are.

## Used by every install

### ezdxf (DXF import)
MIT licence. Copyright (c) 2020 Manfred Moitzi. https://github.com/mozman/ezdxf . The licence text is in the file
`ezdxf-<version>.dist-info/licenses/LICENSE` (in the folder build: next to `WOP.exe`, in `_internal`).

### numpy (3D view, checks)
BSD-3-Clause, with parts under 0BSD, MIT, Zlib and CC0-1.0 (the wheel bundles OpenBLAS and other libraries). Copyright (c) 2005-2025,
NumPy Developers. https://numpy.org , source https://github.com/numpy/numpy . The licence texts are in the file
`numpy-<version>.dist-info/licenses/LICENSE.txt` (in the folder build: in `_internal`).

### fontTools and pyparsing (needed by ezdxf)
MIT licence (the text below). Copyright (c) 2017 Just van Rossum (fontTools, https://github.com/fonttools/fonttools); Copyright (c)
2003-2025 Paul McGuire (pyparsing, https://github.com/pyparsing/pyparsing).

### typing_extensions (needed by ezdxf)
PSF-2.0 licence. https://github.com/python/typing_extensions . Full text: https://github.com/python/typing_extensions/blob/main/LICENSE

### Qt 6 and PySide6 (the window), used under the LGPL-3.0
PySide6 (Qt for Python) and shiboken6 are offered under LGPL-3.0-only, GPL-2.0-only, GPL-3.0-only or a commercial licence; WOP uses
them under the **GNU Lesser General Public Licence 3.0** (the texts of the LGPL-3.0 and of the GPL-3.0 it refers to are in the folder
`licenses` of the repository and next to `WOP.exe`; also https://www.gnu.org/licenses/lgpl-3.0.txt). Qt itself is under the same
terms. Where the source is:
- PySide6 and shiboken6: https://code.qt.io/cgit/pyside/pyside-setup.git/ (the version in use is the one of the pip package or of `_internal\PySide6`)
- Qt 6: https://download.qt.io/official_releases/qt/ and https://code.qt.io/cgit/qt/

WOP is not a modified version of Qt or PySide6. In the folder build the Qt libraries are separate files (`_internal\PySide6\*.dll` and
`*.pyd`), not packed into `WOP.exe`: you may replace them with another build of the same Qt version. The software OpenGL library
`opengl32sw.dll` is the Mesa renderer as shipped by Qt (Mesa licence, MIT style).

## Only in the Windows folder build

- **Python** (`python313.dll`, the standard library): Python Software Foundation licence 2.0, https://docs.python.org/3/license.html
- **OpenSSL** (`libcrypto-3.dll`, part of Python): Apache-2.0, https://www.openssl.org/source/license.html
- **Microsoft Visual C++ runtime** (`vcruntime140*.dll`, `msvcp140*.dll`, `ucrtbase.dll`): redistributable files of Microsoft
- **PyInstaller** (the start program of `WOP.exe`, `tools/build_exe.py`): GPL-2.0-or-later with the exception that programs made with it
  may be distributed under any licence, https://pyinstaller.org

## Only with the compiled core (`tools/build_compiled.py`)

mypyc (part of mypy), MIT licence: Copyright (c) 2012-2023 Jukka Lehtosalo and contributors; Copyright (c) 2015-2023 Dropbox, Inc.
https://github.com/python/mypy . Its small run-time support code is inside the compiled files. Three of its files
(`pythonsupport.h`, `getargs.c`, `getargsfast.c`) are under the PSF-2.0 licence (text in the file `LICENSE` of mypy).

## The MIT licence text (ezdxf, fontTools, pyparsing, mypyc)

The copyright lines are the ones named above; the terms are the same for all of them:

```
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
