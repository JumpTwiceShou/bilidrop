from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable


PYINSTALLER_REQUIREMENT = "PyInstaller==6.20.0"


def ensure_pyinstaller() -> None:
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller not found, installing...")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", PYINSTALLER_REQUIREMENT]
        )


def format_cmd(cmd: list[str]) -> str:
    # Windows 下可读性更好
    return subprocess.list2cmdline(cmd)


def build(
    entry: str,
    name: str,
    *,
    windowed: bool = False,
    onefile: bool = False,
    clean: bool = False,
    noupx: bool = True,
    debug: bool = False,
    extra_args: Iterable[str] | None = None,
) -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--name",
        name,
    ]

    cmd.append("--onefile" if onefile else "--onedir")

    if clean:
        cmd.append("--clean")

    if noupx:
        cmd.append("--noupx")

    if windowed:
        cmd.append("--windowed")

    if debug:
        cmd.extend(["--log-level", "DEBUG"])

    if extra_args:
        cmd.extend(extra_args)

    cmd.append(entry)

    print(f"\nBuilding {name} ...")
    print(format_cmd(cmd))
    build_env = os.environ.copy()
    if sys.platform == "win32":
        # PyInstaller searches PATH for native dependencies. Other applications
        # may ship incompatible DLLs under system names (for example icuuc.dll),
        # which can make a successful build fail while importing QtCore.
        # Package hooks locate Python dependencies; only Python and Windows
        # runtime directories should participate in the fallback DLL search.
        windows_dir = Path(os.environ.get("SystemRoot", r"C:\Windows"))
        build_env["PATH"] = os.pathsep.join(
            str(path)
            for path in (
                Path(sys.executable).parent,
                windows_dir / "System32",
                windows_dir,
            )
        )
    subprocess.check_call(cmd, env=build_env)

    if onefile:
        print(f"Done: dist/{name}.exe")
    else:
        print(f"Done: dist/{name}/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Bilibili Drops Miner with PyInstaller."
    )
    parser.add_argument(
        "--release",
        action="store_true",
        help="compatibility flag; builds the default single-file output.",
    )
    parser.add_argument(
        "--onedir",
        action="store_true",
        help="build an unpacked development directory instead of the default single exe.",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="clean PyInstaller cache before build.",
    )
    parser.add_argument(
        "--target",
        choices=["gui", "cli", "all"],
        default="all",
        help="select which target to build.",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable PyInstaller debug log output.",
    )
    parser.add_argument(
        "--name-suffix",
        default="",
        help="append a suffix to output names so a running build is not overwritten.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_pyinstaller()

    onefile = not args.onedir
    suffix = args.name_suffix.strip().strip("-")
    if suffix and any(char in suffix for char in "\\/:*?\"<>|"):
        raise ValueError("--name-suffix 包含 Windows 文件名不支持的字符")
    gui_name = "bilibili-drops-miner-gui"
    cli_name = "bilibili-drops-miner-cli"
    if suffix:
        gui_name = f"{gui_name}-{suffix}"
        cli_name = f"{cli_name}-{suffix}"

    # 发布包使用 notifier.py 里的轻量内置通知，避免把 Apprise 的全量插件
    # 都塞进包里。源码环境仍可通过 Apprise 回退支持更多通知渠道。
    unused_optional_excludes = [
        "--exclude-module",
        "IPython",
        "--exclude-module",
        "jedi",
        "--exclude-module",
        "jinja2",
        "--exclude-module",
        "matplotlib",
        "--exclude-module",
        "numpy",
        "--exclude-module",
        "PIL",
        "--exclude-module",
        "prompt_toolkit",
        "--exclude-module",
        "pygments",
        "--exclude-module",
        "tkinter",
        "--exclude-module",
        "traitlets",
        "--exclude-module",
        "pytest",
        "--exclude-module",
        "_pytest",
    ]
    common_extra_args = unused_optional_excludes + ["--exclude-module", "apprise"]

    icon_png = Path("assets/bilibili.png")
    icon_ico = Path("assets/bilibili.ico")
    tray_icon_png = Path("assets/bilibili-tray.png")
    tray_icon_ico = Path("assets/bilibili-tray.ico")
    gui_extra_args = common_extra_args + [
        "--icon",
        str(icon_ico),
        "--add-data",
        f"{icon_png}{os.pathsep}assets",
        "--add-data",
        f"{tray_icon_png}{os.pathsep}assets",
        "--add-data",
        f"{tray_icon_ico}{os.pathsep}assets",
        # Selenium 4 lazy-loads browser classes. Include only the two browsers
        # this Windows GUI actually supports; the Selenium hook still carries
        # its required manager binary/data files.
        "--hidden-import",
        "selenium.webdriver.chrome.webdriver",
        "--hidden-import",
        "selenium.webdriver.chrome.options",
        "--hidden-import",
        "selenium.webdriver.chrome.service",
        "--hidden-import",
        "selenium.webdriver.edge.webdriver",
        "--hidden-import",
        "selenium.webdriver.edge.options",
        "--hidden-import",
        "selenium.webdriver.edge.service",
    ]

    if args.target in ("gui", "all"):
        build(
            "bilibili_gui.py",
            gui_name,
            windowed=True,
            onefile=onefile,
            clean=args.clean,
            noupx=True,
            debug=args.debug,
            extra_args=gui_extra_args,
        )

    if args.target in ("cli", "all"):
        build(
            "bilibili.py",
            cli_name,
            onefile=onefile,
            clean=False,  # 避免第二个目标再次清缓存
            noupx=True,
            debug=args.debug,
            extra_args=common_extra_args,
        )

    mode = "single-file" if onefile else "development-directory"
    print(f"\nAll builds complete. Mode: {mode}. Output in dist/")


if __name__ == "__main__":
    main()
