from __future__ import annotations

from PySide6.QtWidgets import QLabel


class StatusBadge(QLabel):
    def __init__(self, text: str = "未登录", color: str = "#8a94a6"):
        super().__init__(text)
        self.set_badge(text, color)

    def set_badge(self, text: str, color: str) -> None:
        self.setText(text)
        self.setStyleSheet(
            f"QLabel {{ color: {color}; background: rgba(47,95,255,0.08); border: 1px solid {color};"
            " border-radius: 10px; padding: 4px 10px; }}"
        )

