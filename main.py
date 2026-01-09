"""
Network Monitor Tool - Visualisation des connexions réseau locales
Requis: pip install PySide6 psutil
"""

import sys
from PySide6.QtWidgets import (QApplication)
from ui.NetworkMonitor import NetworkMonitor

def main():
    app = QApplication(sys.argv)
    window = NetworkMonitor()
    window.show()
    window.refresh_data()  # Chargement initial
    sys.exit(app.exec())


if __name__ == "__main__":
    main()