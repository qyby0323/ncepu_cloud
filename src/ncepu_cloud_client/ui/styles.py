from __future__ import annotations

from ncepu_cloud_client.ui.resources import qss_path

FALLBACK_LIGHT = """
QWidget {
  font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
  font-size: 14px;
  color: #17213f;
  background: #ffffff;
}
QMainWindow, QDialog { background: #f8fafc; }
QPushButton {
  border: 1px solid #dce2ee;
  border-radius: 8px;
  padding: 8px 14px;
  background: #ffffff;
}
QPushButton:hover { background: #f3f7ff; border-color: #b7c7ff; }
QPushButton#PrimaryButton {
  color: white;
  background: #2f5fff;
  border-color: #2f5fff;
}
QFrame#LoginPanel {
  background: #ffffff;
  border: 1px solid #e7ebf2;
  border-radius: 8px;
}
QPushButton#ModeButton:checked {
  color: white;
  background: #2f5fff;
  border-color: #2f5fff;
}
QLineEdit, QComboBox, QTextEdit, QSpinBox {
  border: 1px solid #dce2ee;
  border-radius: 8px;
  padding: 8px;
  background: #ffffff;
}
QTableWidget {
  background: #ffffff;
  border: 1px solid #e7ebf2;
  border-radius: 8px;
  gridline-color: #eef2f7;
}
QHeaderView::section {
  background: #f6f8fc;
  border: none;
  padding: 8px;
  color: #667085;
}
QProgressBar {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f1f5f9;
  text-align: center;
}
QProgressBar::chunk {
  border-radius: 6px;
  background: #2f5fff;
}
"""

FALLBACK_DARK = """
QWidget {
  font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif;
  font-size: 14px;
  color: #e7ecf7;
  background: #111827;
}
QMainWindow, QDialog { background: #0f172a; }
QPushButton {
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 8px 14px;
  background: #1e293b;
}
QPushButton:hover { background: #263449; }
QPushButton#PrimaryButton {
  color: white;
  background: #5b7cff;
  border-color: #5b7cff;
}
QFrame#LoginPanel {
  background: #172033;
  border: 1px solid #334155;
  border-radius: 8px;
}
QPushButton#ModeButton:checked {
  color: white;
  background: #5b7cff;
  border-color: #5b7cff;
}
QLineEdit, QComboBox, QTextEdit, QSpinBox {
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 8px;
  background: #172033;
}
QTableWidget {
  background: #111827;
  border: 1px solid #334155;
  border-radius: 8px;
}
QHeaderView::section {
  background: #172033;
  border: none;
  padding: 8px;
  color: #a8b3cf;
}
"""


def load_styles(theme: str = "light") -> str:
    path = qss_path(theme)
    if path.exists():
        return path.read_text(encoding="utf-8")
    return FALLBACK_DARK if theme == "dark" else FALLBACK_LIGHT
