"""
Network Monitor Tool - Visualisation des connexions réseau locales
Requis: pip install PySide6 psutil
"""

import sys
import psutil
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                                QHBoxLayout, QPushButton, QTableWidget, QTableWidgetItem,
                                QLineEdit, QLabel, QSplitter, QHeaderView, QGraphicsView,
                                QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
                                QGraphicsTextItem)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QBrush, QColor, QPainter


class NetworkData:
    """Collecte et structure les données réseau"""
    
    @staticmethod
    def get_network_info():
        connections = []
        processes = {}
        
        # Récupérer toutes les connexions
        for conn in psutil.net_connections(kind='inet'):
            try:
                if conn.pid:
                    if conn.pid not in processes:
                        try:
                            proc = psutil.Process(conn.pid)
                            processes[conn.pid] = proc.name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            processes[conn.pid] = "Unknown"
                    
                    local_addr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else "N/A"
                    remote_addr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else "N/A"
                    
                    connections.append({
                        'pid': conn.pid,
                        'process': processes[conn.pid],
                        'local_addr': local_addr,
                        'local_ip': conn.laddr.ip if conn.laddr else "",
                        'local_port': conn.laddr.port if conn.laddr else "",
                        'remote_addr': remote_addr,
                        'remote_ip': conn.raddr.ip if conn.raddr else "",
                        'remote_port': conn.raddr.port if conn.raddr else "",
                        'status': conn.status,
                        'type': conn.type.name if hasattr(conn.type, 'name') else str(conn.type)
                    })
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
                
        return connections
    
    @staticmethod
    def analyze_connections(connections):
        """Identifie serveurs et clients"""
        servers = {}  # port -> liste de PIDs serveurs
        clients = {}  # (server_port, client_pid) -> info
        
        for conn in connections:
            # Serveur = écoute (LISTEN) ou a une adresse locale
            if conn['status'] == 'LISTEN':
                port = conn['local_port']
                if port not in servers:
                    servers[port] = []
                server_info = {
                    'pid': conn['pid'],
                    'process': conn['process'],
                    'address': conn['local_addr']
                }
                if server_info not in servers[port]:
                    servers[port].append(server_info)
            
            # Client = connexion établie vers un serveur
            elif conn['status'] == 'ESTABLISHED':
                # Vérifier si c'est local ou distant
                is_remote = not (conn['remote_ip'].startswith('127.') or 
                               conn['remote_ip'].startswith('192.168.') or
                               conn['remote_ip'].startswith('10.') or
                               conn['remote_ip'] == '::1')
                
                key = (conn['remote_port'], conn['pid'], conn['local_port'])
                clients[key] = {
                    'pid': conn['pid'],
                    'process': conn['process'],
                    'local_addr': conn['local_addr'],
                    'remote_addr': conn['remote_addr'],
                    'remote_port': conn['remote_port'],
                    'is_remote': is_remote
                }
        
        return servers, clients


class NetworkGraphView(QGraphicsView):
    """Vue graphique des connexions réseau"""
    
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(400)
        
    def draw_network_map(self, servers, clients, filter_port=None):
        """Dessine le graphique réseau"""
        self.scene.clear()
        
        # Filtrer si nécessaire
        if filter_port:
            try:
                filter_port = int(filter_port)
                servers = {k: v for k, v in servers.items() if k == filter_port}
                clients = {k: v for k, v in clients.items() if k[0] == filter_port}
            except ValueError:
                pass
        
        x_offset = 50
        y_server = 50
        y_client = 300
        spacing = 200
        
        server_positions = {}
        
        # Dessiner les serveurs
        for idx, (port, server_list) in enumerate(servers.items()):
            x = x_offset + idx * spacing
            
            for server in server_list:
                # Cercle serveur
                server_item = QGraphicsEllipseItem(x - 30, y_server - 30, 60, 60)
                server_item.setBrush(QBrush(QColor(100, 200, 100)))
                server_item.setPen(QPen(QColor(0, 100, 0), 2))
                self.scene.addItem(server_item)
                
                # Texte serveur
                text = f"Port {port}\n{server['process']}\nPID: {server['pid']}"
                text_item = QGraphicsTextItem(text)
                text_item.setPos(x - 40, y_server - 80)
                text_item.setDefaultTextColor(QColor(0, 0, 0))
                self.scene.addItem(text_item)
                
                server_positions[port] = (x, y_server)
        
        # Dessiner les clients
        client_x = x_offset
        drawn_clients = set()
        
        for (remote_port, client_pid, local_port), client_info in clients.items():
            if remote_port not in server_positions:
                continue
                
            client_key = (client_pid, local_port)
            if client_key in drawn_clients:
                continue
            drawn_clients.add(client_key)
            
            # Cercle client
            client_item = QGraphicsEllipseItem(client_x - 20, y_client - 20, 40, 40)
            color = QColor(200, 100, 100) if client_info['is_remote'] else QColor(100, 100, 200)
            client_item.setBrush(QBrush(color))
            client_item.setPen(QPen(QColor(100, 0, 0) if client_info['is_remote'] else QColor(0, 0, 100), 2))
            self.scene.addItem(client_item)
            
            # Texte client
            remote_label = " (DISTANT)" if client_info['is_remote'] else ""
            text = f"{client_info['process']}{remote_label}\nPID: {client_pid}\n:{local_port} → :{remote_port}"
            text_item = QGraphicsTextItem(text)
            text_item.setPos(client_x - 50, y_client + 25)
            text_item.setDefaultTextColor(QColor(0, 0, 0))
            self.scene.addItem(text_item)
            
            # Ligne de connexion
            server_x, server_y = server_positions[remote_port]
            line = QGraphicsLineItem(client_x, y_client - 20, server_x, server_y + 30)
            line.setPen(QPen(QColor(150, 150, 150), 1, Qt.DashLine))
            self.scene.addItem(line)
            
            client_x += spacing
        
        # Ajuster la vue
        self.scene.setSceneRect(self.scene.itemsBoundingRect())


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
        
        self.clear_filter_btn = QPushButton("Effacer filtre")
        self.clear_filter_btn.clicked.connect(lambda: self.port_filter.clear())
        control_layout.addWidget(self.clear_filter_btn)
        
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
        
        self.table.setRowCount(0)
        
        # Ajouter les serveurs
        for port, server_list in self.servers.items():
            if filter_port and str(port) != filter_port:
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
        self.graph_view.draw_network_map(self.servers, self.clients, filter_port)


def main():
    app = QApplication(sys.argv)
    window = NetworkMonitor()
    window.show()
    window.refresh_data()  # Chargement initial
    sys.exit(app.exec())


if __name__ == "__main__":
    main()