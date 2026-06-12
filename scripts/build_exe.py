from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


def valid_ico(path: Path) -> bool:
    if not path.exists():
        return False
    data = path.read_bytes()[:4]
    return data == b"\x00\x00\x01\x00"


def png_dimensions(data: bytes) -> tuple[int, int] | None:
    if data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        return None
    return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")


def write_ico_from_png(source_png: Path, target_ico: Path) -> Path:
    png = source_png.read_bytes()
    dimensions = png_dimensions(png)
    if dimensions is None:
        raise ValueError(f"{source_png} 不是有效 PNG 文件")
    width, height = dimensions
    width_byte = width if 0 < width < 256 else 0
    height_byte = height if 0 < height < 256 else 0
    header = bytearray(b"\x00\x00\x01\x00\x01\x00")
    header.extend(bytes([width_byte, height_byte, 0, 0]))
    header.extend((1).to_bytes(2, "little"))
    header.extend((32).to_bytes(2, "little"))
    header.extend(len(png).to_bytes(4, "little"))
    header.extend((22).to_bytes(4, "little"))
    target_ico.parent.mkdir(parents=True, exist_ok=True)
    target_ico.write_bytes(bytes(header) + png)
    return target_ico


def ensure_icon(path: Path, source_png: Path | None = None) -> Path:
    if source_png and source_png.exists():
        return write_ico_from_png(source_png, path)
    if valid_ico(path):
        return path
    width = 16
    height = 16
    pixels = bytearray()
    for y in range(height):
        for x in range(width):
            if 4 <= x <= 11 and 4 <= y <= 11:
                pixels.extend([255, 255, 255, 255])
            else:
                pixels.extend([255, 95, 47, 255])
    xor_bitmap = bytes(pixels)
    and_mask = b"\x00" * (((width + 31) // 32) * 4 * height)
    dib_size = 40 + len(xor_bitmap) + len(and_mask)
    dib = bytearray()
    dib.extend((40).to_bytes(4, "little"))
    dib.extend(width.to_bytes(4, "little"))
    dib.extend((height * 2).to_bytes(4, "little"))
    dib.extend((1).to_bytes(2, "little"))
    dib.extend((32).to_bytes(2, "little"))
    dib.extend((0).to_bytes(4, "little"))
    dib.extend(len(xor_bitmap).to_bytes(4, "little"))
    dib.extend((0).to_bytes(4, "little"))
    dib.extend((0).to_bytes(4, "little"))
    dib.extend((0).to_bytes(4, "little"))
    dib.extend((0).to_bytes(4, "little"))
    dib.extend(xor_bitmap)
    dib.extend(and_mask)
    ico = bytearray()
    ico.extend(b"\x00\x00\x01\x00\x01\x00")
    ico.extend(bytes([width, height, 0, 0]))
    ico.extend((1).to_bytes(2, "little"))
    ico.extend((32).to_bytes(2, "little"))
    ico.extend(dib_size.to_bytes(4, "little"))
    ico.extend((22).to_bytes(4, "little"))
    ico.extend(dib)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(bytes(ico))
    return path


def build_command(project: Path, onefile: bool = False, ensure_icon_file: bool = True, distpath: Path | None = None) -> list[str]:
    source_png = project / "image" / "图标.png"
    icon = ensure_icon(project / "assets" / "app.ico", source_png) if ensure_icon_file else project / "assets" / "app.ico"
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--name",
        "NCEPUCloudClient",
        "--paths",
        str(project / "src"),
        "--hidden-import",
        "PySide6.QtWebEngineWidgets",
        "--hidden-import",
        "PySide6.QtWebEngineCore",
        "--add-data",
        f"{project / 'assets'}{os.pathsep}assets",
        "--icon",
        str(icon),
        str(project / "src" / "ncepu_cloud_client" / "main.py"),
    ]
    if (project / "image").exists():
        icon_data = ["--add-data", f"{project / 'image'}{os.pathsep}image"]
        command[command.index("--icon"):command.index("--icon")] = icon_data
    if distpath is not None:
        command.insert(-1, str(distpath))
        command.insert(-2, "--distpath")
    if onefile:
        command.insert(-1, "--onefile")
    return command


def pyinstaller_available() -> bool:
    return importlib.util.find_spec("PyInstaller") is not None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--onefile", action="store_true")
    mode.add_argument("--onedir", action="store_true")
    parser.add_argument("--distpath", type=Path, help="Custom PyInstaller output directory, useful when dist is locked.")
    parser.add_argument("--dry-run", action="store_true", help="Print the PyInstaller command without executing it.")
    args = parser.parse_args(argv)
    project = Path(__file__).resolve().parents[1]
    if args.dry_run:
        command = build_command(project, onefile=args.onefile, ensure_icon_file=False, distpath=args.distpath)
        print(" ".join(command))
        return 0
    if not pyinstaller_available():
        print("错误: PyInstaller 未安装，请先执行 pip install -r requirements.txt")
        return 2
    command = build_command(project, onefile=args.onefile, distpath=args.distpath)
    return subprocess.call(command, cwd=project)


if __name__ == "__main__":
    raise SystemExit(main())
