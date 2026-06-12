from __future__ import annotations

import sys


def main() -> int:
    try:
        from ncepu_cloud_client.ui.app import run_app
    except Exception as exc:
        print("华电云盘客户端 GUI 启动失败。")
        print("请确认已安装依赖：pip install -r requirements.txt")
        print(f"错误: {exc}")
        return 1
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())

