import sys
from pathlib import Path

root_dir = Path(__file__).parent.absolute()

if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from PyQt6.QtWidgets import QApplication
from ui.main_window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet("""
QMainWindow {
    background: #0f1117;
}

QWidget {
    background: #0f1117;
    color: white;
}

QLineEdit {
    background: #1c1f26;
    border: 1px solid #2b313d;
    border-radius: 8px;
    padding: 8px;
}

QPushButton {
    background: #2d6cdf;
    border: none;
    border-radius: 8px;
    padding: 8px;
}

QPushButton:hover {
    background: #3b7cff;
}

QListWidget {
    background: #151922;
    border: none;
}

QComboBox {
    background: #1c1f26;
    padding: 6px;
}
""")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()