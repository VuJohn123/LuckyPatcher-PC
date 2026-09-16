"""Modern dark theme cho LP-PC Suite."""

MATERIAL_DARK_STYLE = """
QMainWindow { background-color: #0d1117; color: #c9d1d9; }
QWidget {
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 13px;
}

/* ==================== SIDEBAR ==================== */
QWidget#sidebar {
    background-color: #161b22;
    border-right: 1px solid #30363d;
    min-width: 220px;
    max-width: 220px;
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
    border-left: 4px solid transparent;
}
QWidget#sidebar QPushButton:hover {
    background-color: #21262d;
    color: #f0f6fc;
}
QWidget#sidebar QPushButton:checked {
    background-color: #1f6feb;
    color: #ffffff;
    border-left: 4px solid #58a6ff;
}

/* ==================== TOOLBAR ==================== */
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

/* ==================== INPUTS ==================== */
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

/* ==================== LIST ==================== */
QListWidget {
    background-color: #0d1117;
    border: none;
    outline: none;
    padding: 6px;
}
QListWidget::item {
    background: transparent;
    border: none;
    padding: 0;
}
QListWidget::item:selected,
QListWidget::item:hover {
    background: transparent;
}

/* ==================== BUTTONS ==================== */
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

/* ==================== GROUP BOX ==================== */
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

/* ==================== TEXT EDIT ==================== */
QTextEdit, QPlainTextEdit {
    background-color: #0a0d12;
    border: none;
    border-radius: 0;
    padding: 10px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 12px;
    color: #c9d1d9;
}

/* ==================== SCROLLBAR ==================== */
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

/* ==================== PROGRESS BAR LP-style ==================== */
QWidget#progressContainer {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
}
QProgressBar {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 4px;
    text-align: center;
    color: #ffffff;
    font-weight: bold;
}
QProgressBar::chunk {
    background-color: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #238636, stop:1 #3fb950);
    border-radius: 3px;
}

/* ==================== SWITCHES PANEL ==================== */
QWidget#switchesPanel {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
}

/* ==================== STATUS BAR ==================== */
QStatusBar {
    background-color: #161b22;
    color: #8b949e;
    border-top: 1px solid #30363d;
}

/* ==================== SPLITTER ==================== */
QSplitter::handle { background-color: #30363d; width: 2px; }

/* ==================== TOOLTIP ==================== */
QToolTip {
    background-color: #21262d;
    color: #f0f6fc;
    border: 1px solid #58a6ff;
    border-radius: 4px;
    padding: 4px;
}

/* ==================== MENU ==================== */
QMenu {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
}
QMenu::item:selected { background-color: #1f6feb; }

/* ==================== DIALOG ==================== */
QDialog { background-color: #0d1117; }
QDialog QPushButton {
    min-height: 32px;
    padding: 6px 18px;
}
QDialog QLabel { color: #c9d1d9; }

/* ==================== CHECKBOX ==================== */
QCheckBox {
    color: #c9d1d9;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #30363d;
    border-radius: 4px;
    background-color: #0d1117;
}
QCheckBox::indicator:checked {
    background-color: #238636;
    border-color: #2ea043;
    image: none;
}
QCheckBox::indicator:hover {
    border-color: #58a6ff;
}

/* ==================== RADIO ==================== */
QRadioButton {
    color: #c9d1d9;
    spacing: 8px;
    padding: 4px;
}
QRadioButton::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #30363d;
    border-radius: 7px;
    background-color: #0d1117;
}
QRadioButton::indicator:checked {
    background-color: #1f6feb;
    border-color: #58a6ff;
}
"""