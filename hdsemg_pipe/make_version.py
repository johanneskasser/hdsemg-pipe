from PyInstaller.utils.win32.versioninfo import (
    VSVersionInfo,
    FixedFileInfo,
    StringFileInfo,
    StringTable,
    StringStruct,
    VarFileInfo,
    VarStruct
)
from version import __version__

# Version in 4 Teile zerlegen (z.B. "0.0.2" → (0, 0, 2, 0))
version_parts = list(map(int, __version__.split('.')))  # Konvertiere map-Objekt zu Liste
version_parts += [0] * (4 - len(version_parts))  # Auf 4 Stellen auffüllen
version_tuple = tuple(version_parts[:4])

# FixedFileInfo mit snake_case-Parametern
ffi = FixedFileInfo(
    filevers=version_tuple,
    prodvers=version_tuple,
    mask=0x3f,
    flags=0x00,
    OS=0x4,
    fileType=0x1,
)

# StringFileInfo
string_table = StringTable(
    '040904B0',
    [
        StringStruct('FileDescription', 'hdsemg-pipe'),
        StringStruct('FileVersion', __version__),
        StringStruct('InternalName', 'hdsemg-pipe.exe'),
        StringStruct('OriginalFilename', 'hdsemg-pipe.exe'),
        StringStruct('ProductName', 'hdsemg-pipe'),
        StringStruct('ProductVersion', __version__),
        StringStruct('CompanyName', 'University of Applied Sciences Campus Wien | Physiotherapy'),
    ],
)

# VarFileInfo
var_info = VarFileInfo([VarStruct('Translation', [0x0409, 1252])])

# VSVersionInfo mit kids-Liste
version_info = VSVersionInfo(
    ffi=ffi,
    kids=[StringFileInfo([string_table]), var_info]
)

# Schreibe die Rohdaten
out = 'version.txt'
# 1) grab the Python‑source representation:
#    PyInstaller’s versioninfo.py defines __unicode__ (py2) or __str__ (py3)
#    to render it back to text
text = str(version_info)

# 2) prepend the UTF-8 marker line it expects
text = text + "\n"

# 3) write *text* (a Python string) in UTF‑8
with open(out, 'w', encoding='utf-8') as f:
    f.write(text)

print(f"Generated {out} for version {__version__}")
