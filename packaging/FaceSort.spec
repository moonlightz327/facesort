# Cross-platform PyInstaller spec for FaceSort.
#   macOS   -> dist/FaceSort.app        (onedir + .app bundle, .icns icon)
#   Windows -> dist/FaceSort.exe        (onefile, .ico icon)
# Build:  uv run pyinstaller packaging/FaceSort.spec --noconfirm
import os
import sys

from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

IS_WIN = sys.platform == "win32"
IS_MAC = sys.platform == "darwin"
PROJECT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = [(os.path.join(PROJECT, "facesort", "gui", "static"), "facesort/gui/static")]
binaries = []
hiddenimports = []

# insightface's get_object() reads from sys._MEIPASS/objects/ when frozen, so its
# landmark meanshape pickle must live at the bundle top level.
import insightface  # noqa: E402

_if_objects = os.path.join(os.path.dirname(insightface.__file__), "data", "objects")
if os.path.isdir(_if_objects):
    datas.append((_if_objects, "objects"))

for pkg in ("onnxruntime", "insightface", "skimage", "webview", "cv2", "rawpy", "PIL"):
    datas += collect_data_files(pkg)
    hiddenimports += collect_submodules(pkg)

for pkg in ("onnxruntime", "rawpy", "cv2"):
    binaries += collect_dynamic_libs(pkg)

hiddenimports += ["facesort", "pillow_heif"]

ICON = os.path.join(PROJECT, "packaging", "FaceSort." + ("ico" if IS_WIN else "icns"))

a = Analysis(
    [os.path.join(PROJECT, "packaging", "launcher.py")],
    pathex=[PROJECT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["pytest", "matplotlib", "tkinter", "IPython"],
    noarchive=False,
)
pyz = PYZ(a.pure)

if IS_WIN:
    # Single-file .exe: everything bundled into one downloadable file.
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="FaceSort",
        console=False,
        icon=ICON,
        target_arch=None,
    )
else:
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="FaceSort",
        console=False,
        argv_emulation=True,  # macOS "open with" file args
        icon=ICON,
        target_arch=None,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="FaceSort")
    app = BUNDLE(
        coll,
        name="FaceSort.app",
        icon=ICON,
        bundle_identifier="com.facesort.app",
        info_plist={
            "CFBundleName": "FaceSort",
            "CFBundleDisplayName": "FaceSort 分图",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )
