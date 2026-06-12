from __future__ import annotations

from ncepu_cloud_client.config.settings import Settings
from ncepu_cloud_client.ui.pages.settings_page import SettingsPage

from PySide6.QtWidgets import QDialog, QVBoxLayout


class SettingsWindow(QDialog):
    def __init__(self, settings: Settings):
        super().__init__()
        self.setWindowTitle("设置")
        self.resize(680, 560)
        layout = QVBoxLayout(self)
        layout.addWidget(SettingsPage(settings))

