from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                                QLineEdit, QLabel, QSplitter, QHeaderView, QSpinBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from bin.NetworkData import NetworkData
from bin.NetworkGraphView import NetworkGraphView


class NetworkMonitor(QMainWindow):
    """Interface principale"""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Network Monitor - Surveillance Locale")
        self.setGeometry(100, 100, 1400, 900)
        
        self.connections = []
        self.servers = {}
        self.clients = {}
        
        self.setup_ui()
        
    def setup_ui(self):
        """Construction de l'interface"""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Barre de contrôle
        control_layout = QHBoxLayout()
        
        self.refresh_btn = QPushButton("🔄 Rafraîchir")
        self.refresh_btn.clicked.connect(self.refresh_data)
        control_layout.addWidget(self.refresh_btn)
        
        control_layout.addWidget(QLabel("Filtrer par port:"))
        self.port_filter = QLineEdit()
        self.port_filter.setPlaceholderText("Ex: 8080")
        self.port_filter.setMaximumWidth(150)
        self.port_filter.textChanged.connect(self.apply_filter)
        control_layout.addWidget(self.port_filter)

        control_layout.addWidget(QLabel("Filtrer par PID:"))
        self.pid_filter = QLineEdit()
        self.pid_filter.setPlaceholderText("Ex: 24668")
        self.pid_filter.setMaximumWidth(150)
        self.pid_filter.textChanged.connect(self.apply_filter)
        control_layout.addWidget(self.pid_filter)
        
        self.clear_filter_btn = QPushButton("Effacer filtre")
        self.clear_filter_btn.clicked.connect(lambda: self.port_filter.clear())
        self.clear_filter_btn.clicked.connect(lambda: self.pid_filter.clear())
        control_layout.addWidget(self.clear_filter_btn)

        control_layout.addWidget(QLabel("Profondeur de visibilité:"))
        self.depth_spin = QSpinBox()
        self.depth_spin.setRange(1, 5)        # valeurs possibles : 1 à 5
        self.depth_spin.setValue(1)           # valeur par défaut
        self.depth_spin.setMaximumWidth(80)   # largeur max du champ
        self.depth_spin.valueChanged.connect(self.apply_filter)  # appeler ta fonction de filtrage

        control_layout.addWidget(self.depth_spin)
        
        control_layout.addStretch()
        
        self.status_label = QLabel("Prêt")
        control_layout.addWidget(self.status_label)
        
        layout.addLayout(control_layout)
        
        # Splitter pour tableau et graphique
        splitter = QSplitter(Qt.Vertical)
        
        # Tableau
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "PID", "Processus", "Rôle", "Adresse Locale", 
            "Port Local", "Adresse Distante", "Port Distant", "Statut", "Type"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.setAlternatingRowColors(True)
        splitter.addWidget(self.table)
        
        # Vue graphique
        self.graph_view = NetworkGraphView()
        splitter.addWidget(self.graph_view)
        
        splitter.setSizes([400, 400])
        layout.addWidget(splitter)
        
        # Légende
        legend_layout = QHBoxLayout()
        legend_layout.addWidget(QLabel("🟢 Serveur (écoute)"))
        legend_layout.addWidget(QLabel("🔵 Client (local)"))
        legend_layout.addWidget(QLabel("🔴 Client (distant)"))
        legend_layout.addStretch()
        layout.addLayout(legend_layout)
        
    def refresh_data(self):
        """Rafraîchit les données"""
        self.status_label.setText("Collecte des données...")
        QApplication.processEvents()
        
        self.connections = NetworkData.get_network_info()
        self.servers, self.clients = NetworkData.analyze_connections(self.connections)
        
        self.update_table()
        self.update_graph()
        
        self.status_label.setText(f"Actualisé - {len(self.connections)} connexions trouvées")
    
    def apply_filter(self):
        """Applique le filtre"""
        self.update_table()
        self.update_graph()
    
    def update_table(self):
        """Met à jour le tableau"""
        filter_port = self.port_filter.text().strip()
        filter_pid = self.pid_filter.text().strip()
        
        self.table.setRowCount(0)
        
        # Ajouter les serveurs
        for port, server_list in self.servers.items():
            if filter_port or filter_pid:
                port_ok = filter_port and str(port) == str(filter_port)
                pid = server_list and server_list[0].get("pid")
                pid_ok = filter_pid and pid is not None and str(pid) == str(filter_pid)

                if not (port_ok or pid_ok):
                    continue
                
            for server in server_list:
                row = self.table.rowCount()
                self.table.insertRow(row)
                self.table.setItem(row, 0, QTableWidgetItem(str(server['pid'])))
                self.table.setItem(row, 1, QTableWidgetItem(server['process']))
                self.table.setItem(row, 2, QTableWidgetItem("SERVEUR"))
                self.table.setItem(row, 3, QTableWidgetItem(server['address']))
                self.table.setItem(row, 4, QTableWidgetItem(str(port)))
                self.table.setItem(row, 5, QTableWidgetItem("-"))
                self.table.setItem(row, 6, QTableWidgetItem("-"))
                self.table.setItem(row, 7, QTableWidgetItem("LISTEN"))
                self.table.setItem(row, 8, QTableWidgetItem("TCP"))
                
                # Colorer en vert
                for col in range(9):
                    self.table.item(row, col).setBackground(QColor(200, 255, 200))
        
        # Ajouter les clients
        for (remote_port, client_pid, local_port), client_info in self.clients.items():
            if filter_port and str(remote_port) != filter_port:
                continue
                
            row = self.table.rowCount()
            self.table.insertRow(row)
            self.table.setItem(row, 0, QTableWidgetItem(str(client_pid)))
            self.table.setItem(row, 1, QTableWidgetItem(client_info['process']))
            
            role = "CLIENT (DISTANT)" if client_info['is_remote'] else "CLIENT"
            self.table.setItem(row, 2, QTableWidgetItem(role))
            self.table.setItem(row, 3, QTableWidgetItem(client_info['local_addr']))
            self.table.setItem(row, 4, QTableWidgetItem(str(local_port)))
            self.table.setItem(row, 5, QTableWidgetItem(client_info['remote_addr']))
            self.table.setItem(row, 6, QTableWidgetItem(str(remote_port)))
            self.table.setItem(row, 7, QTableWidgetItem("ESTABLISHED"))
            self.table.setItem(row, 8, QTableWidgetItem("TCP"))
            
            # Colorer selon local/distant
            color = QColor(255, 200, 200) if client_info['is_remote'] else QColor(200, 200, 255)
            for col in range(9):
                self.table.item(row, col).setBackground(color)
    
    def update_graph(self):
        """Met à jour le graphique"""
        filter_port = self.port_filter.text().strip()
        filter_pid = self.pid_filter.text().strip()
        depth = self.depth_spin.value()
        self.graph_view.draw_network_map(self.servers, self.clients, filter_port, filter_pid, depth)

