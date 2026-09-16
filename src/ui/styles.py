"""Modern dark theme cho LP-PC Suite."""

MATERIAL_DARK_STYLE = """
QMainWindow { background-color: #0d1117; color: #c9d1d9; }
QWidget {
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 13px;
}
QWidget#sidebar {
    background-color: #161b22;
    border-right: 1px solid #30363d;
    min-width: 240px;
    max-width: 240px;
}
QWidget#sidebar QPushButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 10px 16px;
    text-align: left;
    color: #8b949e;
    font-weight: 600;
    font-size: 13px;
}
QWidget#sidebar QPushButton:hover {
    background-color: #21262d;
    color: #f0f6fc;
}
QWidget#sidebar QPushButton:checked {
    background-color: #1f6feb;
    color: #ffffff;
}
QToolBar {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 4px 8px;
    spacing: 8px;
}
QToolBar QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: bold;
}
QToolBar QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
}
QLineEdit, QComboBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 10px;
    color: #c9d1d9;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QComboBox:focus { border-color: #58a6ff; }
QComboBox QAbstractItemView {
    background-color: #161b22;
    color: #c9d1d9;
    selection-background-color: #1f6feb;
}
QListWidget {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 4px;
    outline: none;
}
QListWidget::item {
    padding: 8px 12px;
    border-bottom: 1px solid #21262d;
    color: #c9d1d9;
}
QListWidget::item:selected {
    background-color: #1f6feb;
    color: #ffffff;
    border-left: 3px solid #58a6ff;
}
QListWidget::item:hover { background-color: #161b22; }
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 16px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #58a6ff;
}
QPushButton:pressed { background-color: #0d1117; }
QPushButton:disabled {
    background-color: #161b22;
    color: #484f58;
}
QPushButton[cssClass="green"] {
    background-color: #238636;
    border: 1px solid #2ea043;
    color: #ffffff;
}
QPushButton[cssClass="green"]:hover { background-color: #2ea043; }
QPushButton[cssClass="blue"] {
    background-color: #1f6feb;
    border: 1px solid #388bfd;
    color: #ffffff;
}
QPushButton[cssClass="blue"]:hover { background-color: #388bfd; }
QPushButton[cssClass="orange"] {
    background-color: #d29922;
    border: 1px solid #e3b341;
    color: #000000;
}
QPushButton[cssClass="orange"]:hover { background-color: #e3b341; }
QPushButton[cssClass="yellow"] {
    background-color: #d29922;
    border: 1px solid #e3b341;
    color: #000000;
}
QPushButton[cssClass="purple"] {
    background-color: #8957e5;
    border: 1px solid #a371f7;
    color: #ffffff;
}
QGroupBox {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 14px;
    font-weight: bold;
    color: #58a6ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
}
QTextEdit {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 8px;
    padding: 10px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    color: #c9d1d9;
}
QScrollBar:vertical {
    background: #0d1117;
    width: 10px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 5px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #484f58; }
QProgressBar {
    background-color: #21262d;
    border: 1px solid #30363d;
    border-radius: 8px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: #238636;
    border-radius: 8px;
}
QStatusBar {
    background-color: #161b22;
    color: #8b949e;
    border-top: 1px solid #30363d;
}
QSplitter::handle { background-color: #30363d; width: 2px; }
QToolTip {
    background-color: #21262d;
    color: #f0f6fc;
    border: 1px solid #58a6ff;
    border-radius: 4px;
    padding: 4px;
}
QMenu {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
}
QMenu::item:selected { background-color: #1f6feb; }
QDialog { background-color: #0d1117; }

/* === Switches panel === */
QWidget#switchesPanel {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
}

/* === App list item hover/selected mạnh hơn === */
QListWidget::item {
    margin: 2px 4px;
    border-radius: 8px;
    border-left: 3px solid transparent;
}
QListWidget::item:selected {
    background-color: #1f6feb22;
    border-left: 3px solid #1f6feb;
    color: #f0f6fc;
}
QListWidget::item:hover {
    background-color: #21262d;
}

/* === Sidebar active state mạnh hơn === */
QWidget#sidebar QPushButton:checked {
    background-color: #1f6feb;
    color: #ffffff;
    border-left: 4px solid #58a6ff;
    padding-left: 12px;
}
QWidget#sidebar QPushButton {
    text-align: left;
    padding-left: 16px;
    border-left: 4px solid transparent;
}

/* === Log container === */
QPlainTextEdit {
    border: none;
    border-radius: 0;
    background-color: #0a0d12;
}

/* === Dialog styling === */
QDialog QPushButton {
    min-height: 32px;
    padding: 6px 18px;
}
"""