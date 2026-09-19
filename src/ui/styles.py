"""Modern dark theme cho LP-PC Suite (v2 — bigger fonts)."""

MATERIAL_DARK_STYLE = """
QMainWindow { background-color: #0d1117; color: #c9d1d9; }
QWidget {
    font-family: "Segoe UI", "Roboto", sans-serif;
    font-size: 15px;
}

/* ==================== SIDEBAR ==================== */
QWidget#sidebar {
    background-color: #161b22;
    border-right: 1px solid #30363d;
    min-width: 230px;
    max-width: 230px;
}
QWidget#sidebar QPushButton {
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 12px 18px;
    text-align: left;
    color: #8b949e;
    font-weight: 600;
    font-size: 15px;
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
    padding: 6px 10px;
    spacing: 10px;
}
QToolBar QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 8px 14px;
    font-weight: bold;
    font-size: 14px;
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
    padding: 8px 12px;
    color: #c9d1d9;
    font-size: 14px;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QComboBox:focus { border-color: #58a6ff; }
QComboBox QAbstractItemView {
    background-color: #161b22;
    color: #c9d1d9;
    font-size: 14px;
    selection-background-color: #1f6feb;
}

/* ==================== LIST ==================== */
QListWidget {
    background-color: #0d1117;
    border: none;
    outline: none;
    padding: 8px;
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
    padding: 10px 18px;
    font-weight: bold;
    font-size: 14px;
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
    margin-top: 14px;
    padding-top: 16px;
    font-weight: bold;
    font-size: 14px;
    color: #58a6ff;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
}

/* ==================== TEXT EDIT ==================== */
QTextEdit, QPlainTextEdit {
    background-color: #0a0d12;
    border: none;
    border-radius: 0;
    padding: 12px;
    font-family: "Cascadia Code", "Consolas", monospace;
    font-size: 14px;
    color: #c9d1d9;
}

/* ==================== SCROLLBAR ==================== */
QScrollBar:vertical {
    background: #0d1117;
    width: 12px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 6px;
    min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #484f58; }

QScrollBar:horizontal {
    background: #0d1117;
    height: 12px;
    margin: 2px;
}
QScrollBar::handle:horizontal {
    background: #30363d;
    border-radius: 6px;
    min-width: 24px;
}
QScrollBar::handle:horizontal:hover { background: #484f58; }

/* ==================== PROGRESS BAR ==================== */
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
    font-size: 14px;
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
    font-size: 14px;
    border-top: 1px solid #30363d;
}

/* ==================== SPLITTER ==================== */
QSplitter::handle { background-color: #30363d; width: 2px; }

QSplitter#mainSplitter::handle:vertical {
    background-color: #30363d;
    height: 6px;
}
QSplitter#mainSplitter::handle:vertical:hover {
    background-color: #58a6ff;
}
QSplitter#mainSplitter::handle:vertical:pressed {
    background-color: #1f6feb;
}

/* ==================== TOOLTIP ==================== */
QToolTip {
    background-color: #21262d;
    color: #f0f6fc;
    border: 1px solid #58a6ff;
    border-radius: 4px;
    padding: 6px 10px;
    font-size: 14px;
}

/* ==================== MENU ==================== */
QMenu {
    background-color: #161b22;
    color: #c9d1d9;
    border: 1px solid #30363d;
    padding: 6px;
    font-size: 14px;
}
QMenu::item {
    padding: 8px 24px;
    border-radius: 4px;
}
QMenu::item:selected { background-color: #1f6feb; }

/* ==================== DIALOG ==================== */
QDialog { background-color: #0d1117; }
QDialog QPushButton {
    min-height: 36px;
    padding: 8px 20px;
}
QDialog QLabel {
    color: #c9d1d9;
    font-size: 14px;
}

/* ==================== CHECKBOX ==================== */
QCheckBox {
    color: #c9d1d9;
    font-size: 14px;
    spacing: 10px;
}
QCheckBox::indicator {
    width: 18px;
    height: 18px;
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
    font-size: 14px;
    spacing: 10px;
    padding: 6px;
}
QRadioButton::indicator {
    width: 16px;
    height: 16px;
    border: 1px solid #30363d;
    border-radius: 8px;
    background-color: #0d1117;
}
QRadioButton::indicator:checked {
    background-color: #1f6feb;
    border-color: #58a6ff;
}

/* ==================== TREE WIDGET ==================== */
QTreeWidget, QTreeView {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px;
    outline: none;
    color: #c9d1d9;
    font-size: 14px;
}
QTreeWidget::item, QTreeView::item {
    padding: 6px 4px;
    border-radius: 4px;
    min-height: 26px;
}
QTreeWidget::item:hover, QTreeView::item:hover {
    background-color: #161b22;
}
QTreeWidget::item:selected, QTreeView::item:selected {
    background-color: #1f6feb;
    color: #ffffff;
}
QTreeWidget QHeaderView::section,
QTreeView QHeaderView::section {
    background-color: #161b22;
    color: #8b949e;
    padding: 6px 10px;
    border: none;
    border-bottom: 1px solid #30363d;
    font-weight: bold;
    font-size: 14px;
}

/* ==================== TREE CHECKBOXES ==================== */
QTreeView::indicator,
QTreeWidget::indicator {
    width: 18px;
    height: 18px;
    border: 1px solid #30363d;
    border-radius: 3px;
    background-color: #0d1117;
}
QTreeView::indicator:hover,
QTreeWidget::indicator:hover {
    border-color: #58a6ff;
}
QTreeView::indicator:checked,
QTreeWidget::indicator:checked {
    background-color: #238636;
    border-color: #2ea043;
}
QTreeView::indicator:indeterminate,
QTreeWidget::indicator:indeterminate {
    background-color: #1f6feb;
    border-color: #388bfd;
}
"""