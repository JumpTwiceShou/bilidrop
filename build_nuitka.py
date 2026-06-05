from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Iterable


OUTPUT_DIR = Path("dist-nuitka")
ICON_PATH = Path("img/app.ico")

UNUSED_OPTIONAL_EXCLUDES = [
    "IPython",
    "jedi",
    "jinja2",
    "matplotlib",
    "numpy",
    "PIL",
    "prompt_toolkit",
    "pygments",
    "tkinter",
    "traitlets",
]


def format_cmd(cmd: list[str]) -> str:
    return subprocess.list2cmdline(cmd)


def extend_nofollow_args(cmd: list[str], modules: Iterable[str]) -> None:
    for module in modules:
        cmd.append(f"--nofollow-import-to={module}")


def build(
    entry: str,
    output_name: str,
    *,
    windowed: bool = False,
) -> None:
    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--standalone",
        "--assume-yes-for-downloads",
        f"--output-dir={OUTPUT_DIR}",
        f"--output-filename={output_name}.exe",
    ]

    if ICON_PATH.exists():
        cmd.append(f"--windows-icon-from-ico={ICON_PATH}")

    if windowed:
        cmd.extend(
            [
                "--windows-console-mode=disable",
                "--enable-plugin=pyside6",
                "--include-package=selenium",
            ]
        )

    extend_nofollow_args(cmd, UNUSED_OPTIONAL_EXCLUDES)
    cmd.append("--nofollow-import-to=apprise")

    cmd.append(entry)

    print(f"\nBuilding {output_name} with Nuitka ...")
    print(format_cmd(cmd))
    subprocess.check_call(cmd)

    source_dir = OUTPUT_DIR / f"{Path(entry).stem}.dist"
    target_dir = OUTPUT_DIR / output_name
    if source_dir == target_dir:
        return
    if not source_dir.exists():
        raise FileNotFoundError(f"Nuitka output not found: {source_dir}")
    if target_dir.exists():
        shutil.rmtree(target_dir)
    source_dir.rename(target_dir)
    print(f"Done: {target_dir}/")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build Bilibili Drops Miner with Nuitka."
    )
    parser.add_argument(
        "--target",
        choices=["gui", "cli", "all"],
        default="all",
        help="select which target to build.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.target in ("gui", "all"):
        build(
            "bilibili_gui.py",
            "bilibili-drops-miner-gui",
            windowed=True,
        )

    if args.target in ("cli", "all"):
        build(
            "bilibili.py",
            "bilibili-drops-miner-cli",
        )

    print("\nAll Nuitka builds complete. Output in dist-nuitka/")


if __name__ == "__main__":
    main()
