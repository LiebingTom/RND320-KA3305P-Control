"""Start the GUI: python -m src.gui"""

import logging
import sys

from PySide6.QtWidgets import QApplication

from src.gui.main_window import MainWindow
from src.gui.theme import STYLESHEET


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)
    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
