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
QWidget#ContentArea {
  background: #f8fafc;
}
QFrame#Sidebar {
  background: #edf4ff;
  border-right: 1px solid #dbe7fb;
}
QLabel#SidebarBrand {
  color: #17213f;
  font-size: 18px;
  font-weight: 700;
  background: transparent;
}
QLabel#SidebarCaption,
QLabel#SidebarSection,
QLabel#MutedText {
  color: #667085;
  background: transparent;
}
QLabel#SidebarSection {
  font-size: 12px;
  font-weight: 700;
  padding: 12px 10px 4px 10px;
}
QLabel#LibraryItem {
  color: #344054;
  background: transparent;
  border-radius: 7px;
  padding: 7px 12px;
}
QLabel#LibraryItemSelected {
  color: #1d4ed8;
  background: #dceaff;
  border-radius: 7px;
  padding: 7px 12px;
  font-weight: 600;
}
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
QPushButton#PrimaryButton:hover {
  background: #214de0;
  border-color: #214de0;
}
QPushButton#NavButton {
  border: none;
  border-radius: 8px;
  padding: 10px 12px;
  text-align: left;
  background: transparent;
  color: #344054;
}
QPushButton#NavButton:hover {
  background: #e3efff;
  border: none;
}
QPushButton#NavButton:checked {
  color: #1d4ed8;
  background: #ffffff;
  font-weight: 700;
  border: 1px solid #d7e6ff;
}
QPushButton#GhostButton {
  border-color: transparent;
  background: transparent;
  color: #475467;
}
QPushButton#GhostButton:hover {
  border-color: #dce2ee;
  background: #f6f8fc;
}
QFrame#LoginPanel {
  background: #ffffff;
  border: 1px solid #e7ebf2;
  border-radius: 8px;
}
QFrame#Surface,
QWidget#Surface,
QFrame#Card,
QWidget#Card {
  background: #ffffff;
  border: 1px solid #e7ebf2;
  border-radius: 8px;
}
QFrame#SubtleSurface {
  background: #f6f9ff;
  border: 1px solid #dce9ff;
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
QLineEdit#TopSearch {
  border-color: #d7e2f1;
  background: #ffffff;
  padding: 9px 12px;
}
QLabel#AppTitle {
  color: #17213f;
  font-size: 19px;
  font-weight: 700;
  background: transparent;
}
QLabel#PageTitle {
  color: #17213f;
  font-size: 22px;
  font-weight: 700;
  background: transparent;
}
QLabel#SectionTitle {
  color: #17213f;
  font-size: 15px;
  font-weight: 700;
  background: transparent;
}
QLabel#MetricValue {
  color: #17213f;
  font-size: 18px;
  font-weight: 700;
  background: transparent;
}
QLabel#SuccessText {
  color: #087443;
  background: transparent;
  font-weight: 700;
}
QLabel#WarningText {
  color: #b54708;
  background: transparent;
}
QTableWidget {
  background: #ffffff;
  border: 1px solid #e7ebf2;
  border-radius: 8px;
  gridline-color: #eef2f7;
  selection-background-color: #e8f0ff;
  selection-color: #17213f;
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
QScrollArea {
  border: none;
  background: transparent;
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
QPushButton#NavButton {
  border: none;
  border-radius: 8px;
  padding: 10px 12px;
  text-align: left;
  background: transparent;
  color: #cbd5e1;
}
QPushButton#NavButton:checked {
  color: #ffffff;
  background: #1e293b;
  font-weight: 700;
}
QFrame#LoginPanel {
  background: #172033;
  border: 1px solid #334155;
  border-radius: 8px;
}
QFrame#Sidebar {
  background: #111827;
  border-right: 1px solid #263449;
}
QFrame#Surface,
QWidget#Surface,
QFrame#Card,
QWidget#Card,
QFrame#SubtleSurface {
  background: #172033;
  border: 1px solid #334155;
  border-radius: 8px;
}
QLabel#SidebarBrand,
QLabel#AppTitle,
QLabel#PageTitle,
QLabel#SectionTitle,
QLabel#MetricValue {
  color: #e7ecf7;
  background: transparent;
  font-weight: 700;
}
QLabel#SidebarCaption,
QLabel#SidebarSection,
QLabel#MutedText {
  color: #a8b3cf;
  background: transparent;
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
