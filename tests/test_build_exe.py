import importlib.util
import os
from pathlib import Path


def load_build_module():
    script = Path(__file__).resolve().parents[1] / "scripts" / "build_exe.py"
    spec = importlib.util.spec_from_file_location("build_exe", script)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_build_command_uses_platform_add_data_separator(tmp_path):
    build_exe = load_build_module()
    project = tmp_path / "project"
    (project / "assets").mkdir(parents=True)
    (project / "src" / "ncepu_cloud_client").mkdir(parents=True)

    command = build_exe.build_command(project, onefile=True)

    assert "--onefile" in command
    assert "--paths" in command
    assert str(project / "src") in command
    assert "--add-data" in command
    assert f"{project / 'assets'}{os.pathsep}assets" in command
    assert str(project / "src" / "ncepu_cloud_client" / "main.py") == command[-1]
    assert build_exe.valid_ico(project / "assets" / "app.ico")


def test_build_command_uses_uploaded_image_as_icon(tmp_path):
    build_exe = load_build_module()
    project = tmp_path / "project"
    (project / "assets").mkdir(parents=True)
    (project / "src" / "ncepu_cloud_client").mkdir(parents=True)
    image_dir = project / "image"
    image_dir.mkdir()
    png = b"\x89PNG\r\n\x1a\n" + (13).to_bytes(4, "big") + b"IHDR" + (256).to_bytes(4, "big") + (256).to_bytes(4, "big") + bytes([8, 6, 0, 0, 0])
    (image_dir / "图标.png").write_bytes(png)

    command = build_exe.build_command(project)

    assert f"{image_dir}{os.pathsep}image" in command
    assert build_exe.valid_ico(project / "assets" / "app.ico")
    assert (project / "assets" / "app.ico").read_bytes().endswith(png)


def test_build_command_accepts_custom_distpath(tmp_path):
    build_exe = load_build_module()
    project = tmp_path / "project"
    (project / "assets").mkdir(parents=True)
    (project / "src" / "ncepu_cloud_client").mkdir(parents=True)
    distpath = project / "dist-new"

    command = build_exe.build_command(project, distpath=distpath)

    assert "--distpath" in command
    assert str(distpath) in command
    assert command.index("--distpath") < command.index(str(distpath))


def test_build_exe_dry_run_does_not_call_subprocess(monkeypatch, capsys):
    build_exe = load_build_module()

    monkeypatch.setattr(build_exe.subprocess, "call", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("subprocess should not run")))
    monkeypatch.setattr(build_exe, "pyinstaller_available", lambda: False)
    monkeypatch.setattr(build_exe, "ensure_icon", lambda path: (_ for _ in ()).throw(AssertionError("icon should not be generated")))

    assert build_exe.main(["--dry-run", "--onedir"]) == 0

    output = capsys.readouterr().out
    assert "PyInstaller" in output
    assert "NCEPUCloudClient" in output


def test_build_exe_reports_missing_pyinstaller(monkeypatch, capsys):
    build_exe = load_build_module()

    monkeypatch.setattr(build_exe, "pyinstaller_available", lambda: False)
    monkeypatch.setattr(build_exe, "ensure_icon", lambda path: (_ for _ in ()).throw(AssertionError("icon should not be generated")))
    monkeypatch.setattr(build_exe.subprocess, "call", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("subprocess should not run")))

    assert build_exe.main(["--onedir"]) == 2
    assert "PyInstaller 未安装" in capsys.readouterr().out


def test_run_dev_scripts_add_src_to_pythonpath():
    project = Path(__file__).resolve().parents[1]

    for script_name in ("run_dev.bat", "run_dev.ps1", "run_dev.sh"):
        script = (project / "scripts" / script_name).read_text(encoding="utf-8")
        assert "PYTHONPATH" in script
        assert "src" in script
        assert "ncepu_cloud_client.main" in script
