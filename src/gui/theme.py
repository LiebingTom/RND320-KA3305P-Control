"""Colours and Qt stylesheet for the instrument look."""

BG = "#0e1014"
PANEL = "#161920"
PANEL_2 = "#1d212a"
BORDER = "#2a303c"
TEXT = "#e6e8ec"
DIM = "#8b93a1"
ON = "#22c55e"
OFF = "#ef4444"
WARN = "#f59e0b"

CHANNEL_COLORS = {1: "#facc15", 2: "#22d3ee", 3: "#e879f9"}

STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: "Segoe UI", sans-serif; font-size: 10pt; }}
QToolTip {{ background: {PANEL_2}; color: {TEXT}; border: 1px solid {BORDER}; }}
QFrame#card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 8px; }}
QFrame#card QWidget {{ background: transparent; }}
QLabel#dim {{ color: {DIM}; }}
QLabel#title {{ font-size: 13pt; font-weight: 600; }}
QLabel#badge {{ border-radius: 4px; padding: 1px 6px; font-weight: 700; font-size: 9pt; }}
QPushButton {{
    background: {PANEL_2}; border: 1px solid {BORDER}; border-radius: 5px; padding: 5px 12px;
}}
QPushButton:hover {{ border-color: {DIM}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: #555b66; border-color: #22262e; }}
QPushButton:checked {{ background: #12361f; border: 1px solid {ON}; color: {ON}; font-weight: 700; }}
QPushButton#outOn {{ background: #12361f; border: 1px solid {ON}; color: {ON}; font-weight: 700; }}
QPushButton#outOff {{ background: {PANEL_2}; border: 1px solid {BORDER}; color: {DIM}; font-weight: 700; }}
QPushButton#danger {{ background: #3a1414; border: 1px solid {OFF}; color: #fca5a5; font-weight: 700; }}
QPushButton#rec:checked {{ background: #3a1414; border-color: {OFF}; color: #fca5a5; }}
QDoubleSpinBox, QSpinBox, QComboBox, QLineEdit {{
    background: {BG}; border: 1px solid {BORDER}; border-radius: 4px; padding: 3px 6px;
    selection-background-color: #334155;
}}
QDoubleSpinBox:focus, QSpinBox:focus, QComboBox:focus {{ border-color: {DIM}; }}
QComboBox QAbstractItemView {{ background: {PANEL_2}; border: 1px solid {BORDER}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 6px; top: -1px; }}
QTabBar::tab {{ background: {PANEL}; border: 1px solid {BORDER}; padding: 6px 16px; margin-right: 2px;
               border-top-left-radius: 6px; border-top-right-radius: 6px; }}
QTabBar::tab:selected {{ background: {PANEL_2}; border-bottom-color: {PANEL_2}; }}
QTableWidget {{ background: {BG}; gridline-color: {BORDER}; border: none; }}
QHeaderView::section {{ background: {PANEL_2}; border: none; border-right: 1px solid {BORDER}; padding: 4px; }}
QStatusBar {{ background: {PANEL}; border-top: 1px solid {BORDER}; color: {DIM}; }}
QCheckBox::indicator {{ width: 14px; height: 14px; }}
QSplitter::handle {{ background: {BG}; }}
"""
