from __future__ import annotations


def explain() -> str:
    return (
        "Windows 虚拟文件系统建议使用 WinFsp、Dokany 或 ProjFS。"
        "该扩展不作为主 exe 依赖，避免未安装系统组件时客户端无法启动。"
    )

