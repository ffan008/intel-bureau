# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 配置：把工作台打成 macOS 的 .app（onedir）。

用法： .venv/bin/pyinstaller pack/intelbureau.spec --noconfirm
产物： dist-app/情报局.app

注意：config/secrets.yaml 与 config/settings.yaml 是用户自己的密钥和设置，绝不进安装包。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

ROOT = Path(SPECPATH).parent          # SPECPATH 是 pack/ 目录
datas: list[tuple[str, str]] = []
hiddenimports: list[str] = []


def add_tree(src: Path, dest: str, skip: frozenset[str] = frozenset(),
             skip_suffix: tuple[str, ...] = ()) -> None:
    if not src.is_dir():
        return
    for p in sorted(src.rglob("*")):
        if not p.is_file() or p.name in skip or (skip_suffix and p.name.endswith(skip_suffix)):
            continue
        rel = p.parent.relative_to(src)
        datas.append((str(p), dest if str(rel) == "." else f"{dest}/{rel.as_posix()}"))


# 前端已经 build 好，直接随包（服务端按 Paths.web_dist 提供）；.map 是调试用，不进安装包
add_tree(ROOT / "web" / "dist", "web/dist", skip_suffix=(".map",))
# 配置模板：提示词、词典、分类表、示例
add_tree(ROOT / "config", "config", skip=frozenset({"secrets.yaml", "settings.yaml"}))

# jieba 只要分词词典和 TF-IDF 的 idf 表；lac_small / posseg 是词性标注和深度学习模型，
# 本项目用不到，collect_data_files('jieba') 会把它们全收进来（多 25MB）。
import jieba as _jieba

_JBASE = Path(_jieba.__file__).parent
for _name, _dest in (("dict.txt", "jieba"), ("analyse/idf.txt", "jieba/analyse")):
    _f = _JBASE / _name
    if _f.is_file():
        datas.append((str(_f), _dest))

# uvicorn / apscheduler 大量用字符串动态导入，整包收集最省事（纯 Python，体积很小）
hiddenimports += collect_submodules("uvicorn")
hiddenimports += collect_submodules("apscheduler")
hiddenimports += ["AppKit", "Foundation", "objc", "bureau.api", "bureau.cli"]

# bureau 自己的模块也用「模块路径字符串 + importlib」懒加载（采集器、推送通道、research/media
# 的降级加载），静态分析看不到，整包收最保险——bureau 本身只有 1.8MB 源码。
import sys as _sys

_sys.path.insert(0, str(ROOT))
hiddenimports += collect_submodules("bureau")

from bureau.channels import CHANNEL_REGISTRY  # noqa: E402
from bureau.collectors import COLLECTOR_REGISTRY  # noqa: E402

for _target in list(COLLECTOR_REGISTRY.values()) + list(CHANNEL_REGISTRY.values()):
    _mod = _target.partition(":")[0]
    if _mod not in hiddenimports:
        hiddenimports.append(_mod)

# macOS 的离线 OCR（可选）：装了才带上
try:
    import Vision  # noqa: F401

    hiddenimports += ["Vision", "Quartz", "bureau.media.ocr"]
except ImportError:
    pass

# 有些库运行时要读自身 dist-info
for pkg in ("fastapi", "starlette", "uvicorn", "pydantic", "jieba", "APScheduler"):
    try:
        datas += copy_metadata(pkg)
    except Exception:  # noqa: BLE001  没装就没元数据，不影响
        pass

block_cipher = None

a = Analysis(
    [str(ROOT / "pack" / "app_main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "pytest", "PyInstaller", "tests", "IPython", "notebook"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
# PyInstaller 自带的 hook-jieba 会把整包数据都收进来（lac_small 深度学习模型、posseg 词性表，
# 共 25MB）。本项目只做分词 + TF-IDF，只留 dict.txt 和 analyse/idf.txt。
_KEEP_JIEBA = {"dict.txt", "idf.txt"}
a.datas = [d for d in a.datas
           if "jieba" not in str(d[1]).replace("\\", "/")
           or Path(str(d[0])).name in _KEEP_JIEBA]

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="IntelBureau",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,                   # 无终端窗口
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="IntelBureau",
)

app = BUNDLE(
    coll,
    name="情报局.app",
    icon=str(ROOT / "pack" / "appicon.icns") if (ROOT / "pack" / "appicon.icns").is_file() else None,
    bundle_identifier="com.intelbureau.workbench",
    info_plist={
        "CFBundleName": "情报局",
        "CFBundleDisplayName": "情报局 · 作战大屏",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        # 只在菜单栏出现「◉」，不占 Dock、不抢焦点
        "LSUIElement": True,
        "NSHighResolutionCapable": True,
        "LSMinimumSystemVersion": "12.0",
        "NSHumanReadableCopyright": "本地运行 · 不上传任何数据",
    },
)
