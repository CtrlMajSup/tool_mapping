from PySide6.QtWidgets import ( QGraphicsView,
                                QGraphicsScene, QGraphicsEllipseItem, QGraphicsLineItem,
                                QGraphicsTextItem, QGraphicsRectItem)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPen, QBrush, QColor, QPainter
from collections import defaultdict, deque

class NetworkGraphView(QGraphicsView):
    """Vue graphique des connexions réseau"""
    
    def __init__(self):
        super().__init__()
        self.scene = QGraphicsScene()
        self.setScene(self.scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setMinimumHeight(400)

    def draw_network_map(self, servers, clients, filter_port=None, filter_pid=None, depth=1):
        """Dessine le graphique réseau avec rectangles et points d'ancrage multiples"""
        self.scene.clear()

        # --- Pré-traitement : cast filtre port / pid ---
        try:
            if filter_port:
                filter_port = int(filter_port)
        except ValueError:
            filter_port = None

        try:
            if filter_pid:
                filter_pid = int(filter_pid)
        except ValueError:
            filter_pid = None

        # --- Étape 1 : Construire l'index PID → informations ---
        pid_info = {}  # {pid: {'process': str, 'server_ports': set, 'client_connections': list}}
        
        # Collecter infos des serveurs
        for port, server_list in servers.items():
            for server in server_list:
                pid = server.get("pid")
                if pid is None:
                    continue
                if pid not in pid_info:
                    pid_info[pid] = {
                        'process': server.get('process', 'Unknown'),
                        'server_ports': set(),
                        'client_connections': []
                    }
                pid_info[pid]['server_ports'].add(port)
        
        # Collecter infos des clients
        for (server_port, client_pid, local_port), client_info in clients.items():
            if client_pid is None:
                continue
            if client_pid not in pid_info:
                pid_info[client_pid] = {
                    'process': client_info.get('process', 'Unknown'),
                    'server_ports': set(),
                    'client_connections': []
                }
            pid_info[client_pid]['client_connections'].append({
                'local_port': local_port,
                'remote_port': server_port,
                'is_remote': client_info.get('is_remote', False)
            })

        # --- Étape 2 : Construire le graphe PID → PID avec les connexions ---
        # Structure : {(pid1, pid2): [{'local_port': x, 'remote_port': y, 'is_remote': bool}, ...]}
        # On utilise toujours (min_pid, max_pid) pour éviter les doublons
        bidirectional_connections = defaultdict(list)
        pid_connections = defaultdict(list)  # Pour le BFS
        
        for (server_port, client_pid, local_port), client_info in clients.items():
            server_list = servers.get(server_port, [])
            for server in server_list:
                server_pid = server.get("pid")
                if server_pid is not None and client_pid is not None:
                    # Pour le BFS (direction serveur → client)
                    pid_connections[server_pid].append({
                        'client_pid': client_pid,
                        'local_port': local_port,
                        'remote_port': server_port,
                        'is_remote': client_info.get('is_remote', False)
                    })
                    
                    # Pour l'affichage bidirectionnel (clé normalisée)
                    pid_pair = tuple(sorted([server_pid, client_pid]))
                    already_saved =  False
                    for bidirectional_connection in bidirectional_connections[pid_pair]:
                        if server_port == bidirectional_connection["local_port"] and local_port == bidirectional_connection["remote_port"]:
                            already_saved = True

                    if not already_saved:
                        bidirectional_connections[pid_pair].append({
                            'server_pid': server_pid,
                            'client_pid': client_pid,
                            'local_port': local_port,
                            'remote_port': server_port,
                            'is_remote': client_info.get('is_remote', False)
                        })

        # --- Étape 3 : Filtrage initial et BFS pour profondeur ---
        root_pids = set()
        
        if filter_pid:
            root_pids.add(filter_pid)
        elif filter_port:
            for port, server_list in servers.items():
                if port == filter_port:
                    for server in server_list:
                        pid = server.get("pid")
                        if pid:
                            root_pids.add(pid)
        else:
            # Tous les PIDs serveurs comme racines
            root_pids = {pid for pid in pid_info.keys() if pid_info[pid]['server_ports']}

        # BFS pour déterminer les PIDs visibles
        visible_pids = set()
        pid_depth = {}
        
        if root_pids:
            queue = deque([(pid, 0) for pid in root_pids])
            while queue:
                pid, level = queue.popleft()
                if pid in visible_pids:
                    continue
                if level >= depth:
                    continue
                
                visible_pids.add(pid)
                pid_depth[pid] = level
                
                # Ajouter les clients de ce PID
                for conn in pid_connections.get(pid, []):
                    child_pid = conn['client_pid']
                    if child_pid not in visible_pids:
                        queue.append((child_pid, level + 1))

        # --- Étape 4 : Organisation par niveaux ---
        levels = defaultdict(list)  # {depth: [pid, ...]}
        for pid in visible_pids:
            level = pid_depth.get(pid, 0)
            levels[level].append(pid)

        # --- Étape 5 : Calcul des ports uniques par PID pour les connexions visibles ---
        # On regroupe par couple de PIDs
        pid_pair_ports = defaultdict(lambda: {'server_ports': set(), 'client_ports': set()})
        
        for pid_pair, connections in bidirectional_connections.items():
            pid1, pid2 = pid_pair
            if pid1 not in visible_pids or pid2 not in visible_pids:
                continue
            
            for conn in connections:
                # On collecte tous les ports utilisés dans cette relation
                pid_pair_ports[pid_pair]['server_ports'].add(conn['remote_port'])
                pid_pair_ports[pid_pair]['client_ports'].add(conn['local_port'])

        # Calculer les points d'ancrage nécessaires par PID
        pid_anchor_ports = defaultdict(lambda: {'top': set(), 'bottom': set()})
        
        for (pid1, pid2), ports_info in pid_pair_ports.items():
            # Déterminer qui est au-dessus (plus petit depth)
            depth1 = pid_depth.get(pid1, 0)
            depth2 = pid_depth.get(pid2, 0)
            
            if depth1 < depth2:
                # pid1 est au-dessus, pid2 en dessous
                upper_pid, lower_pid = pid1, pid2
            elif depth2 < depth1:
                upper_pid, lower_pid = pid2, pid1
            else:
                # Même niveau, on utilise l'ordre naturel
                upper_pid, lower_pid = pid1, pid2
            

            # Les ports du PID supérieur vont en bas
            for port in ports_info['server_ports']:
                pid_anchor_ports[upper_pid]['bottom'].add(port)
            
            # Les ports du PID inférieur vont en haut
            for port in ports_info['client_ports']:
                pid_anchor_ports[lower_pid]['top'].add(port)

        # --- Étape 6 : Calcul des positions et dimensions des rectangles ---
        spacing_x = 300
        spacing_y = 220
        start_x = 150
        start_y = 100
        
        rect_width = 250
        base_rect_height = 80
        
        node_positions = {}  # {pid: {'x': x, 'y': y, 'width': w, 'height': h, 'top_ports': {port: (x,y)}, 'bottom_ports': {port: (x,y)}}}
        
        for level in sorted(levels.keys()):
            pids = levels[level]
            y = start_y + level * spacing_y
            
            for idx, pid in enumerate(pids):
                x = start_x + idx * spacing_x
                
                rect_height = base_rect_height
                
                # Calculer les positions des points d'ancrage
                top_ports_pos = {}
                bottom_ports_pos = {}
                
                # Points d'ancrage en haut
                top_ports = sorted(pid_anchor_ports[pid]['top'])
                if top_ports:
                    for i, port in enumerate(top_ports):
                        port_x = x + (i + 1) * (rect_width / (len(top_ports) + 1))
                        top_ports_pos[port] = (port_x, y)
                
                # Points d'ancrage en bas
                bottom_ports = sorted(pid_anchor_ports[pid]['bottom'])
                if bottom_ports:
                    for i, port in enumerate(bottom_ports):
                        port_x = x + (i + 1) * (rect_width / (len(bottom_ports) + 1))
                        bottom_ports_pos[port] = (port_x, y + rect_height)
                
                node_positions[pid] = {
                    'x': x,
                    'y': y,
                    'width': rect_width,
                    'height': rect_height,
                    'top_ports': top_ports_pos,
                    'bottom_ports': bottom_ports_pos
                }

        # --- Étape 8 : Dessin des connexions (une seule ligne par couple de PIDs) ---
        drawn_pairs = set()
        
        for (pid1, pid2), connections in bidirectional_connections.items():
            if pid1 not in visible_pids or pid2 not in visible_pids:
                continue
            
            if (pid1, pid2) in drawn_pairs or (pid2, pid1) in drawn_pairs:
                continue
            drawn_pairs.add((pid1, pid2))
            
            # Déterminer qui est au-dessus
            depth1 = pid_depth.get(pid1, 0)
            depth2 = pid_depth.get(pid2, 0)
            
            if depth1 < depth2:
                upper_pid, lower_pid = pid1, pid2
            elif depth2 < depth1:
                upper_pid, lower_pid = pid2, pid1
            else:
                upper_pid, lower_pid = pid1, pid2
            
            upper_pos = node_positions.get(upper_pid)
            lower_pos = node_positions.get(lower_pid)
            
            if not upper_pos or not lower_pos:
                continue
            
            # Collecter tous les ports utilisés pour cette connexion
            ports_used = set()
            has_remote = False
            for conn in connections:
                ports_used.add((conn['remote_port'], conn['local_port']))
                if conn['is_remote']:
                    has_remote = True
            
            # Dessiner une ligne par couple de ports
            for remote_port, local_port in ports_used:
                # Point de départ (bas du upper_pid)
                if remote_port in upper_pos['bottom_ports']:
                    x1, y1 = upper_pos['bottom_ports'][remote_port]
                else:
                    x1 = upper_pos['x'] + upper_pos['width'] / 2
                    y1 = upper_pos['y'] + upper_pos['height']
                
                # Point d'arrivée (haut du lower_pid)
                if local_port in lower_pos['top_ports']:
                    x2, y2 = lower_pos['top_ports'][local_port]
                else:
                    x2 = lower_pos['x'] + lower_pos['width'] / 2
                    y2 = lower_pos['y']
                
                # Couleur de la ligne
                line_color = QColor(200, 80, 80) if has_remote else QColor(80, 80, 200)
                
                # Ligne de connexion
                line = QGraphicsLineItem(x1, y1, x2, y2)
                pen_style = Qt.DashLine if has_remote else Qt.SolidLine
                line.setPen(QPen(line_color, 2, pen_style))
                self.scene.addItem(line)
                
                # Flèche
                import math
                angle = math.atan2(y2 - y1, x2 - x1)
                arrow_size = 10
                
                arrow_p1_x = x2 - arrow_size * math.cos(angle - math.pi / 6)
                arrow_p1_y = y2 - arrow_size * math.sin(angle - math.pi / 6)
                arrow_p2_x = x2 - arrow_size * math.cos(angle + math.pi / 6)
                arrow_p2_y = y2 - arrow_size * math.sin(angle + math.pi / 6)
                
                arrow1 = QGraphicsLineItem(x2, y2, arrow_p1_x, arrow_p1_y)
                arrow1.setPen(QPen(line_color, 2, Qt.SolidLine))
                self.scene.addItem(arrow1)
                
                arrow2 = QGraphicsLineItem(x2, y2, arrow_p2_x, arrow_p2_y)
                arrow2.setPen(QPen(line_color, 2, Qt.SolidLine))
                self.scene.addItem(arrow2)


        # --- Étape 7 : Dessin des rectangles (nodes) ---
        for pid in visible_pids:
            if pid not in node_positions:
                continue
            
            pos = node_positions[pid]
            x, y = pos['x'], pos['y']
            width, height = pos['width'], pos['height']
            
            info = pid_info.get(pid, {})
            
            # Déterminer la couleur
            is_server = len(info.get('server_ports', set())) > 0
            is_remote_client = any(c.get('is_remote', False) for c in info.get('client_connections', []))
            
            if is_server:
                color = QColor(100, 200, 100)
                border_color = QColor(0, 100, 0)
            elif is_remote_client:
                color = QColor(200, 100, 100)
                border_color = QColor(100, 0, 0)
            else:
                color = QColor(100, 100, 200)
                border_color = QColor(0, 0, 100)
            
            # Rectangle node
            rect_item = QGraphicsRectItem(x, y, width, height)
            rect_item.setBrush(QBrush(color))
            rect_item.setPen(QPen(border_color, 3))
            self.scene.addItem(rect_item)
            
            # Texte principal (centré)
            process_name = info.get('process', 'Unknown')
            server_ports = info.get('server_ports', set())
            
            text_lines = [f"PID: {pid}", process_name]
            if server_ports:
                ports_str = ", ".join(f":{p}" for p in sorted(server_ports))
                text_lines.append(f"Listen: {ports_str}")
            
            text = "\n".join(text_lines)
            text_item = QGraphicsTextItem(text)
            text_item.setPos(x + 10, y + 10)
            text_item.setDefaultTextColor(QColor(0, 0, 0))
            
            font = text_item.font()
            font.setPointSize(9)
            font.setBold(True)
            text_item.setFont(font)
            
            self.scene.addItem(text_item)
            
            # Dessiner les points d'ancrage TOP
            for port, (port_x, port_y) in pos['top_ports'].items():
                anchor = QGraphicsEllipseItem(port_x - 4, port_y - 4, 8, 8)
                anchor.setBrush(QBrush(border_color.darker()))
                anchor.setPen(QPen(Qt.NoPen))
                self.scene.addItem(anchor)
                
                port_label = QGraphicsTextItem(f":{port}")
                port_label.setPos(port_x - 15, port_y - 25)
                font = port_label.font()
                font.setPointSize(7)
                port_label.setFont(font)
                port_label.setDefaultTextColor(border_color)
                self.scene.addItem(port_label)
            
            # Dessiner les points d'ancrage BOTTOM
            for port, (port_x, port_y) in pos['bottom_ports'].items():
                anchor = QGraphicsEllipseItem(port_x - 4, port_y - 4, 8, 8)
                anchor.setBrush(QBrush(border_color.darker()))
                anchor.setPen(QPen(Qt.NoPen))
                self.scene.addItem(anchor)
                
                port_label = QGraphicsTextItem(f":{port}")
                port_label.setPos(port_x - 15, port_y + 5)
                font = port_label.font()
                font.setPointSize(7)
                port_label.setFont(font)
                port_label.setDefaultTextColor(border_color)
                self.scene.addItem(port_label)

    

        # --- Étape 9 : Légende ---
        legend_x = 20
        legend_y = 20
        
        legend_items = [
            (QColor(100, 200, 100), "Serveur"),
            (QColor(100, 100, 200), "Client local"),
            (QColor(200, 100, 100), "Client distant")
        ]
        
        for idx, (color, label) in enumerate(legend_items):
            y_pos = legend_y + idx * 30
            
            rect = QGraphicsRectItem(legend_x, y_pos, 20, 15)
            rect.setBrush(QBrush(color))
            rect.setPen(QPen(color.darker(), 2))
            self.scene.addItem(rect)
            
            text = QGraphicsTextItem(label)
            text.setPos(legend_x + 25, y_pos - 3)
            font = text.font()
            font.setPointSize(8)
            text.setFont(font)
            self.scene.addItem(text)

        # Ajuster la vue
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80))

    def draw_network_map_old3(self, servers, clients, filter_port=None, filter_pid=None, depth=1):
        """Dessine le graphique réseau avec rectangles et points d'ancrage multiples"""
        self.scene.clear()

        # --- Pré-traitement : cast filtre port / pid ---
        try:
            if filter_port:
                filter_port = int(filter_port)
        except ValueError:
            filter_port = None

        try:
            if filter_pid:
                filter_pid = int(filter_pid)
        except ValueError:
            filter_pid = None

        # --- Étape 1 : Construire l'index PID → informations ---
        pid_info = {}  # {pid: {'process': str, 'server_ports': set, 'client_connections': list}}
        
        # Collecter infos des serveurs
        for port, server_list in servers.items():
            for server in server_list:
                pid = server.get("pid")
                if pid is None:
                    continue
                if pid not in pid_info:
                    pid_info[pid] = {
                        'process': server.get('process', 'Unknown'),
                        'server_ports': set(),
                        'client_connections': []
                    }
                pid_info[pid]['server_ports'].add(port)
        
        # Collecter infos des clients
        for (server_port, client_pid, local_port), client_info in clients.items():
            if client_pid is None:
                continue
            if client_pid not in pid_info:
                pid_info[client_pid] = {
                    'process': client_info.get('process', 'Unknown'),
                    'server_ports': set(),
                    'client_connections': []
                }
            pid_info[client_pid]['client_connections'].append({
                'local_port': local_port,
                'remote_port': server_port,
                'is_remote': client_info.get('is_remote', False)
            })

        # --- Étape 2 : Construire le graphe PID → PID avec les connexions ---
        pid_connections = defaultdict(list)  # {server_pid: [(client_pid, local_port, remote_port, is_remote), ...]}
        
        for (server_port, client_pid, local_port), client_info in clients.items():
            server_list = servers.get(server_port, [])
            for server in server_list:
                server_pid = server.get("pid")
                if server_pid is not None and client_pid is not None:
                    pid_connections[server_pid].append({
                        'client_pid': client_pid,
                        'local_port': local_port,
                        'remote_port': server_port,
                        'is_remote': client_info.get('is_remote', False)
                    })

        # --- Étape 3 : Filtrage initial et BFS pour profondeur ---
        root_pids = set()
        
        if filter_pid:
            root_pids.add(filter_pid)
        elif filter_port:
            for port, server_list in servers.items():
                if port == filter_port:
                    for server in server_list:
                        pid = server.get("pid")
                        if pid:
                            root_pids.add(pid)
        else:
            # Tous les PIDs serveurs comme racines
            root_pids = {pid for pid in pid_info.keys() if pid_info[pid]['server_ports']}

        # BFS pour déterminer les PIDs visibles
        visible_pids = set()
        pid_depth = {}
        
        if root_pids:
            queue = deque([(pid, 0) for pid in root_pids])
            while queue:
                pid, level = queue.popleft()
                if pid in visible_pids:
                    continue
                if level >= depth:
                    continue
                
                visible_pids.add(pid)
                pid_depth[pid] = level
                
                # Ajouter les clients de ce PID
                for conn in pid_connections.get(pid, []):
                    child_pid = conn['client_pid']
                    if child_pid not in visible_pids:
                        queue.append((child_pid, level + 1))

        # --- Étape 4 : Organisation par niveaux ---
        levels = defaultdict(list)  # {depth: [pid, ...]}
        for pid in visible_pids:
            level = pid_depth.get(pid, 0)
            levels[level].append(pid)

        # --- Étape 5 : Calcul du nombre de connexions par PID ---
        incoming_ports = defaultdict(set)  # {pid: {remote_port, ...}}
        outgoing_ports = defaultdict(set)  # {pid: {local_port, ...}}
        
        for server_pid in visible_pids:
            for conn in pid_connections.get(server_pid, []):
                client_pid = conn['client_pid']
                if client_pid in visible_pids:
                    incoming_ports[server_pid].add(conn['remote_port'])
                    outgoing_ports[client_pid].add(conn['local_port'])

        # --- Étape 6 : Calcul des positions et dimensions des rectangles ---
        spacing_x = 300
        spacing_y = 220
        start_x = 150
        start_y = 100
        
        rect_width = 180
        base_rect_height = 80
        port_spacing = 20  # Espacement vertical pour chaque port
        
        node_positions = {}  # {pid: {'x': x, 'y': y, 'width': w, 'height': h, 'in_ports': {port: y}, 'out_ports': {port: y}}}
        
        for level in sorted(levels.keys()):
            pids = levels[level]
            y = start_y + level * spacing_y
            
            for idx, pid in enumerate(pids):
                x = start_x + idx * spacing_x
                
                # Calculer la hauteur nécessaire
                in_count = len(incoming_ports.get(pid, set()))
                out_count = len(outgoing_ports.get(pid, set()))
                max_ports = max(in_count, out_count, 1)
                rect_height = base_rect_height + (max_ports - 1) * port_spacing
                
                # Calculer les positions des points d'ancrage
                in_ports_pos = {}
                out_ports_pos = {}
                
                # Points d'ancrage en haut (incoming)
                if in_count > 0:
                    in_ports_list = sorted(incoming_ports.get(pid, set()))
                    for i, port in enumerate(in_ports_list):
                        port_x = x + (i + 1) * (rect_width / (in_count + 1))
                        in_ports_pos[port] = (port_x, y)
                
                # Points d'ancrage en bas (outgoing)
                if out_count > 0:
                    out_ports_list = sorted(outgoing_ports.get(pid, set()))
                    for i, port in enumerate(out_ports_list):
                        port_x = x + (i + 1) * (rect_width / (out_count + 1))
                        out_ports_pos[port] = (port_x, y + rect_height)
                
                node_positions[pid] = {
                    'x': x,
                    'y': y,
                    'width': rect_width,
                    'height': rect_height,
                    'in_ports': in_ports_pos,
                    'out_ports': out_ports_pos
                }

        # --- Étape 7 : Dessin des rectangles (nodes) ---
        for pid in visible_pids:
            if pid not in node_positions:
                continue
            
            pos = node_positions[pid]
            x, y = pos['x'], pos['y']
            width, height = pos['width'], pos['height']
            
            info = pid_info.get(pid, {})
            
            # Déterminer la couleur
            is_server = len(info.get('server_ports', set())) > 0
            is_remote_client = any(c.get('is_remote', False) for c in info.get('client_connections', []))
            
            if is_server:
                color = QColor(100, 200, 100)
                border_color = QColor(0, 100, 0)
            elif is_remote_client:
                color = QColor(200, 100, 100)
                border_color = QColor(100, 0, 0)
            else:
                color = QColor(100, 100, 200)
                border_color = QColor(0, 0, 100)
            
            # Rectangle node
            rect_item = QGraphicsRectItem(x, y, width, height)
            rect_item.setBrush(QBrush(color))
            rect_item.setPen(QPen(border_color, 3))
            self.scene.addItem(rect_item)
            
            # Texte principal (centré)
            process_name = info.get('process', 'Unknown')
            server_ports = info.get('server_ports', set())
            
            text_lines = [f"PID: {pid}", process_name]
            if server_ports:
                ports_str = ", ".join(f":{p}" for p in sorted(server_ports))
                text_lines.append(f"Listen: {ports_str}")
            
            text = "\n".join(text_lines)
            text_item = QGraphicsTextItem(text)
            text_item.setPos(x + 10, y + 10)
            text_item.setDefaultTextColor(QColor(0, 0, 0))
            
            font = text_item.font()
            font.setPointSize(9)
            font.setBold(True)
            text_item.setFont(font)
            
            self.scene.addItem(text_item)
            
            # Dessiner les points d'ancrage IN (en haut)
            for port, (port_x, port_y) in pos['in_ports'].items():
                # Petit cercle pour le point d'ancrage
                anchor = QGraphicsEllipseItem(port_x - 4, port_y - 4, 8, 8)
                anchor.setBrush(QBrush(border_color.darker()))
                anchor.setPen(QPen(Qt.NoPen))
                self.scene.addItem(anchor)
                
                # Label du port (au-dessus)
                port_label = QGraphicsTextItem(f":{port}")
                port_label.setPos(port_x - 15, port_y - 25)
                font = port_label.font()
                font.setPointSize(7)
                port_label.setFont(font)
                port_label.setDefaultTextColor(border_color)
                self.scene.addItem(port_label)
            
            # Dessiner les points d'ancrage OUT (en bas)
            for port, (port_x, port_y) in pos['out_ports'].items():
                # Petit cercle pour le point d'ancrage
                anchor = QGraphicsEllipseItem(port_x - 4, port_y - 4, 8, 8)
                anchor.setBrush(QBrush(border_color.darker()))
                anchor.setPen(QPen(Qt.NoPen))
                self.scene.addItem(anchor)
                
                # Label du port (en-dessous)
                port_label = QGraphicsTextItem(f":{port}")
                port_label.setPos(port_x - 15, port_y + 5)
                font = port_label.font()
                font.setPointSize(7)
                port_label.setFont(font)
                port_label.setDefaultTextColor(border_color)
                self.scene.addItem(port_label)

        # --- Étape 8 : Dessin des connexions (lignes entre points d'ancrage) ---
        drawn_connections = set()
        
        for server_pid in visible_pids:
            if server_pid not in node_positions:
                continue
            
            server_pos = node_positions[server_pid]
            
            for conn in pid_connections.get(server_pid, []):
                client_pid = conn['client_pid']
                if client_pid not in visible_pids or client_pid not in node_positions:
                    continue
                
                client_pos = node_positions[client_pid]
                
                # Clé unique
                conn_key = (server_pid, client_pid, conn['local_port'], conn['remote_port'])
                if conn_key in drawn_connections:
                    continue
                drawn_connections.add(conn_key)
                
                # Trouver les points d'ancrage
                remote_port = conn['remote_port']
                local_port = conn['local_port']
                
                # Point de départ (bas du serveur)
                if remote_port in server_pos['in_ports']:
                    x1, y1 = server_pos['in_ports'][remote_port]
                    y1 = server_pos['y'] + server_pos['height']  # Partir du bas
                else:
                    # Fallback au centre bas
                    x1 = server_pos['x'] + server_pos['width'] / 2
                    y1 = server_pos['y'] + server_pos['height']
                
                # Point d'arrivée (haut du client)
                if local_port in client_pos['out_ports']:
                    x2, y2 = client_pos['out_ports'][local_port]
                    y2 = client_pos['y']  # Arriver en haut
                else:
                    # Fallback au centre haut
                    x2 = client_pos['x'] + client_pos['width'] / 2
                    y2 = client_pos['y']
                
                # Couleur de la ligne
                line_color = QColor(200, 80, 80) if conn['is_remote'] else QColor(80, 80, 200)
                
                # Ligne de connexion avec flèche
                line = QGraphicsLineItem(x1, y1, x2, y2)
                pen_style = Qt.DashLine if conn['is_remote'] else Qt.SolidLine
                line.setPen(QPen(line_color, 2, pen_style))
                self.scene.addItem(line)
                
                # Flèche à la fin (optionnel)
                # Calcul de l'angle pour la flèche
                import math
                angle = math.atan2(y2 - y1, x2 - x1)
                arrow_size = 10
                
                arrow_p1_x = x2 - arrow_size * math.cos(angle - math.pi / 6)
                arrow_p1_y = y2 - arrow_size * math.sin(angle - math.pi / 6)
                arrow_p2_x = x2 - arrow_size * math.cos(angle + math.pi / 6)
                arrow_p2_y = y2 - arrow_size * math.sin(angle + math.pi / 6)
                
                arrow1 = QGraphicsLineItem(x2, y2, arrow_p1_x, arrow_p1_y)
                arrow1.setPen(QPen(line_color, 2, Qt.SolidLine))
                self.scene.addItem(arrow1)
                
                arrow2 = QGraphicsLineItem(x2, y2, arrow_p2_x, arrow_p2_y)
                arrow2.setPen(QPen(line_color, 2, Qt.SolidLine))
                self.scene.addItem(arrow2)

        # --- Étape 9 : Légende ---
        legend_x = 20
        legend_y = 20
        
        legend_items = [
            (QColor(100, 200, 100), "Serveur"),
            (QColor(100, 100, 200), "Client local"),
            (QColor(200, 100, 100), "Client distant")
        ]
        
        for idx, (color, label) in enumerate(legend_items):
            y_pos = legend_y + idx * 30
            
            # Petit rectangle
            rect = QGraphicsRectItem(legend_x, y_pos, 20, 15)
            rect.setBrush(QBrush(color))
            rect.setPen(QPen(color.darker(), 2))
            self.scene.addItem(rect)
            
            # Texte
            text = QGraphicsTextItem(label)
            text.setPos(legend_x + 25, y_pos - 3)
            font = text.font()
            font.setPointSize(8)
            text.setFont(font)
            self.scene.addItem(text)

        # Ajuster la vue
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-80, -80, 80, 80))

    def draw_network_map_old2(self, servers, clients, filter_port=None, filter_pid=None, depth=1):
        """Dessine le graphique réseau avec une node par PID et lignes pour les connexions"""
        self.scene.clear()

        # --- Pré-traitement : cast filtre port / pid ---
        try:
            if filter_port:
                filter_port = int(filter_port)
        except ValueError:
            filter_port = None

        try:
            if filter_pid:
                filter_pid = int(filter_pid)
        except ValueError:
            filter_pid = None

        # --- Étape 1 : Construire l'index PID → informations ---
        pid_info = {}  # {pid: {'process': str, 'server_ports': set, 'client_connections': list}}
        
        # Collecter infos des serveurs
        for port, server_list in servers.items():
            for server in server_list:
                pid = server.get("pid")
                if pid is None:
                    continue
                if pid not in pid_info:
                    pid_info[pid] = {
                        'process': server.get('process', 'Unknown'),
                        'server_ports': set(),
                        'client_connections': []
                    }
                pid_info[pid]['server_ports'].add(port)
        
        # Collecter infos des clients
        for (server_port, client_pid, local_port), client_info in clients.items():
            if client_pid is None:
                continue
            if client_pid not in pid_info:
                pid_info[client_pid] = {
                    'process': client_info.get('process', 'Unknown'),
                    'server_ports': set(),
                    'client_connections': []
                }
            pid_info[client_pid]['client_connections'].append({
                'local_port': local_port,
                'remote_port': server_port,
                'is_remote': client_info.get('is_remote', False)
            })

        # --- Étape 2 : Construire le graphe PID → PID avec les connexions ---
        pid_connections = defaultdict(list)  # {server_pid: [(client_pid, local_port, remote_port, is_remote), ...]}
        
        for (server_port, client_pid, local_port), client_info in clients.items():
            server_list = servers.get(server_port, [])
            for server in server_list:
                server_pid = server.get("pid")
                if server_pid is not None and client_pid is not None:
                    pid_connections[server_pid].append({
                        'client_pid': client_pid,
                        'local_port': local_port,
                        'remote_port': server_port,
                        'is_remote': client_info.get('is_remote', False)
                    })

        # --- Étape 3 : Filtrage initial et BFS pour profondeur ---
        root_pids = set()
        
        if filter_pid:
            root_pids.add(filter_pid)
        elif filter_port:
            for port, server_list in servers.items():
                if port == filter_port:
                    for server in server_list:
                        pid = server.get("pid")
                        if pid:
                            root_pids.add(pid)
        else:
            # Tous les PIDs serveurs comme racines
            root_pids = {pid for pid in pid_info.keys() if pid_info[pid]['server_ports']}

        # BFS pour déterminer les PIDs visibles
        visible_pids = set()
        pid_depth = {}
        
        if root_pids:
            queue = deque([(pid, 0) for pid in root_pids])
            while queue:
                pid, level = queue.popleft()
                if pid in visible_pids:
                    continue
                if level >= depth:
                    continue
                
                visible_pids.add(pid)
                pid_depth[pid] = level
                
                # Ajouter les clients de ce PID
                for conn in pid_connections.get(pid, []):
                    child_pid = conn['client_pid']
                    if child_pid not in visible_pids:
                        queue.append((child_pid, level + 1))

        # --- Étape 4 : Organisation par niveaux ---
        levels = defaultdict(list)  # {depth: [pid, ...]}
        for pid in visible_pids:
            level = pid_depth.get(pid, 0)
            levels[level].append(pid)

        # --- Étape 5 : Calcul des positions ---
        spacing_x = 250
        spacing_y = 180
        start_x = 100
        start_y = 80
        
        node_positions = {}  # {pid: (x, y)}
        
        for level in sorted(levels.keys()):
            pids = levels[level]
            y = start_y + level * spacing_y
            
            # Centrer les nodes horizontalement
            total_width = len(pids) * spacing_x
            offset_x = start_x
            
            for idx, pid in enumerate(pids):
                x = offset_x + idx * spacing_x
                node_positions[pid] = (x, y)

        # --- Étape 6 : Dessin des nodes (une par PID) ---
        for pid in visible_pids:
            if pid not in node_positions:
                continue
                
            x, y = node_positions[pid]
            info = pid_info.get(pid, {})
            
            # Déterminer la couleur : vert si serveur, bleu/rouge si client seulement
            is_server = len(info.get('server_ports', set())) > 0
            is_remote_client = any(c.get('is_remote', False) for c in info.get('client_connections', []))
            
            if is_server:
                color = QColor(100, 200, 100)
                border_color = QColor(0, 100, 0)
            elif is_remote_client:
                color = QColor(200, 100, 100)
                border_color = QColor(100, 0, 0)
            else:
                color = QColor(100, 100, 200)
                border_color = QColor(0, 0, 100)
            
            # Cercle node
            node_item = QGraphicsEllipseItem(x - 35, y - 35, 70, 70)
            node_item.setBrush(QBrush(color))
            node_item.setPen(QPen(border_color, 3))
            self.scene.addItem(node_item)
            
            # Texte node
            process_name = info.get('process', 'Unknown')
            server_ports = info.get('server_ports', set())
            
            text_lines = [f"PID: {pid}", process_name]
            if server_ports:
                ports_str = ", ".join(str(p) for p in sorted(server_ports))
                text_lines.append(f"Ports: {ports_str}")
            
            text = "\n".join(text_lines)
            text_item = QGraphicsTextItem(text)
            text_item.setPos(x - 60, y - 75)
            text_item.setDefaultTextColor(QColor(0, 0, 0))
            
            # Mise en forme du texte
            font = text_item.font()
            font.setPointSize(9)
            text_item.setFont(font)
            
            self.scene.addItem(text_item)

        # --- Étape 7 : Dessin des connexions (lignes avec labels de ports) ---
        drawn_connections = set()  # Pour éviter les doublons
        
        for server_pid in visible_pids:
            if server_pid not in node_positions:
                continue
                
            for conn in pid_connections.get(server_pid, []):
                client_pid = conn['client_pid']
                if client_pid not in visible_pids or client_pid not in node_positions:
                    continue
                
                # Clé unique pour cette connexion
                conn_key = (server_pid, client_pid, conn['local_port'], conn['remote_port'])
                if conn_key in drawn_connections:
                    continue
                drawn_connections.add(conn_key)
                
                # Positions
                x1, y1 = node_positions[server_pid]
                x2, y2 = node_positions[client_pid]
                
                # Couleur de la ligne
                line_color = QColor(200, 100, 100) if conn['is_remote'] else QColor(100, 100, 200)
                
                # Ligne de connexion
                line = QGraphicsLineItem(x1, y1 + 35, x2, y2 - 35)
                line.setPen(QPen(line_color, 2, Qt.SolidLine if not conn['is_remote'] else Qt.DashLine))
                self.scene.addItem(line)
                
                # Label de connexion (ports)
                label_text = f":{conn['local_port']} → :{conn['remote_port']}"
                label_item = QGraphicsTextItem(label_text)
                
                # Position au milieu de la ligne
                mid_x = (x1 + x2) / 2
                mid_y = (y1 + y2) / 2
                label_item.setPos(mid_x - 30, mid_y - 10)
                
                # Style du label
                font = label_item.font()
                font.setPointSize(7)
                label_item.setFont(font)
                label_item.setDefaultTextColor(line_color)
                
                self.scene.addItem(label_item)

        # --- Étape 8 : Légende ---
        legend_x = 20
        legend_y = 20
        
        legend_items = [
            (QColor(100, 200, 100), "Serveur"),
            (QColor(100, 100, 200), "Client local"),
            (QColor(200, 100, 100), "Client distant")
        ]
        
        for idx, (color, label) in enumerate(legend_items):
            y_pos = legend_y + idx * 25
            
            # Petit cercle
            circle = QGraphicsEllipseItem(legend_x, y_pos, 15, 15)
            circle.setBrush(QBrush(color))
            circle.setPen(QPen(color.darker(), 2))
            self.scene.addItem(circle)
            
            # Texte
            text = QGraphicsTextItem(label)
            text.setPos(legend_x + 20, y_pos - 5)
            font = text.font()
            font.setPointSize(8)
            text.setFont(font)
            self.scene.addItem(text)

        # Ajuster la vue
        self.scene.setSceneRect(self.scene.itemsBoundingRect().adjusted(-50, -50, 50, 50))

    def draw_network_map_old1(self, servers, clients, filter_port=None, filter_pid=None, depth=1):
        """Dessine le graphique réseau avec gestion de profondeur hiérarchique"""
        self.scene.clear()

        # --- Pré-traitement : cast filtre port / pid ---
        try:
            if filter_port:
                filter_port = int(filter_port)
        except ValueError:
            filter_port = None

        try:
            if filter_pid:
                filter_pid = int(filter_pid)
        except ValueError:
            filter_pid = None

        # --- Étape 1 : Construire le graphe complet PID → clients PID (tous ports) ---
        pid_to_clients = defaultdict(set)  # {server_pid: {client_pid, ...}}
        pid_to_servers = defaultdict(set)  # {pid: {port, ...}}
        
        # Index des serveurs par PID
        for port, server_list in servers.items():
            for server in server_list:
                server_pid = server.get("pid")
                if server_pid is not None:
                    pid_to_servers[server_pid].add(port)
        
        # Construire le graphe de connexions PID → PID
        for (server_port, client_pid, local_port), client_info in clients.items():
            server_list = servers.get(server_port)
            if not server_list:
                continue
            for server in server_list:
                server_pid = server.get("pid")
                if server_pid is not None and client_pid is not None:
                    pid_to_clients[server_pid].add(client_pid)

        # --- Étape 2 : Filtrage initial (profondeur 0) ---
        initial_servers = servers.copy()
        initial_clients = clients.copy()
        
        if filter_port:
            initial_servers = {k: v for k, v in initial_servers.items() if k == filter_port}
            initial_clients = {k: v for k, v in initial_clients.items() if k[0] == filter_port}

        if filter_pid:
            initial_servers = {
                p: [s for s in sl if s.get("pid") == filter_pid]
                for p, sl in initial_servers.items()
                if any(s.get("pid") == filter_pid for s in sl)
            }
            allowed_ports = {p for p in initial_servers.keys()}
            initial_clients = {
                k: v for k, v in initial_clients.items() if k[0] in allowed_ports
            }

        # --- Étape 3 : BFS pour déterminer tous les PIDs visibles selon profondeur ---
        visible_pids = set()
        pid_depth_map = {}  # {pid: profondeur}
        
        # PIDs de départ (serveurs filtrés)
        root_pids = {s.get("pid") for sl in initial_servers.values() for s in sl if s.get("pid")}
        
        if root_pids:
            queue = deque([(pid, 0) for pid in root_pids])
            while queue:
                pid, level = queue.popleft()
                if pid in visible_pids:
                    continue
                if level >= depth:
                    continue
                    
                visible_pids.add(pid)
                pid_depth_map[pid] = level
                
                # Ajouter tous les clients de ce PID
                for child_pid in pid_to_clients.get(pid, set()):
                    if child_pid not in visible_pids:
                        queue.append((child_pid, level + 1))

        # --- Étape 4 : Filtrer servers et clients selon visible_pids ---
        filtered_servers = {}
        for port, server_list in servers.items():
            filtered = [s for s in server_list if s.get("pid") in visible_pids]
            if filtered:
                filtered_servers[port] = filtered

        filtered_clients = {}
        for (server_port, client_pid, local_port), client_info in clients.items():
            # Client visible si son PID est visible ET le serveur est visible
            if client_pid in visible_pids:
                server_list = servers.get(server_port, [])
                if any(s.get("pid") in visible_pids for s in server_list):
                    filtered_clients[(server_port, client_pid, local_port)] = client_info

        # --- Étape 5 : Organisation hiérarchique par profondeur ---
        nodes_by_depth = defaultdict(list)  # {depth: [(pid, port, type, info), ...]}
        
        # Serveurs (profondeur 0)
        for port, server_list in filtered_servers.items():
            for server in server_list:
                pid = server.get("pid")
                nodes_by_depth[0].append({
                    'type': 'server',
                    'pid': pid,
                    'port': port,
                    'process': server.get('process', 'Unknown'),
                    'info': server
                })
        
        # Clients organisés par profondeur
        for (server_port, client_pid, local_port), client_info in filtered_clients.items():
            client_depth = pid_depth_map.get(client_pid, depth)
            nodes_by_depth[client_depth].append({
                'type': 'client',
                'pid': client_pid,
                'local_port': local_port,
                'remote_port': server_port,
                'process': client_info.get('process', 'Unknown'),
                'is_remote': client_info.get('is_remote', False),
                'info': client_info
            })

        # --- Étape 6 : Dessin avec positionnement hiérarchique ---
        spacing_x = 200
        spacing_y = 200
        start_x = 50
        start_y = 50
        
        node_positions = {}  # {(type, pid, port): (x, y)}
        drawn_nodes = set()
        
        for level in sorted(nodes_by_depth.keys()):
            nodes = nodes_by_depth[level]
            y = start_y + level * spacing_y
            
            for idx, node in enumerate(nodes):
                x = start_x + idx * spacing_x
                
                if node['type'] == 'server':
                    key = ('server', node['pid'], node['port'])
                    if key in drawn_nodes:
                        continue
                    drawn_nodes.add(key)
                    
                    # Cercle serveur
                    server_item = QGraphicsEllipseItem(x - 30, y - 30, 60, 60)
                    server_item.setBrush(QBrush(QColor(100, 200, 100)))
                    server_item.setPen(QPen(QColor(0, 100, 0), 2))
                    self.scene.addItem(server_item)
                    
                    # Texte serveur
                    text = f"Port {node['port']}\n{node['process']}\nPID: {node['pid']}"
                    text_item = QGraphicsTextItem(text)
                    text_item.setPos(x - 40, y - 80)
                    text_item.setDefaultTextColor(QColor(0, 0, 0))
                    self.scene.addItem(text_item)
                    
                    node_positions[key] = (x, y)
                    
                else:  # client
                    key = ('client', node['pid'], node['local_port'])
                    if key in drawn_nodes:
                        continue
                    drawn_nodes.add(key)
                    
                    # Cercle client
                    client_item = QGraphicsEllipseItem(x - 20, y - 20, 40, 40)
                    color = QColor(200, 100, 100) if node['is_remote'] else QColor(100, 100, 200)
                    client_item.setBrush(QBrush(color))
                    client_item.setPen(QPen(QColor(100, 0, 0) if node['is_remote'] else QColor(0, 0, 100), 2))
                    self.scene.addItem(client_item)
                    
                    # Texte client
                    remote_label = " (DISTANT)" if node['is_remote'] else ""
                    text = f"{node['process']}{remote_label}\nPID: {node['pid']}\n:{node['local_port']} → :{node['remote_port']}"
                    text_item = QGraphicsTextItem(text)
                    text_item.setPos(x - 50, y + 25)
                    text_item.setDefaultTextColor(QColor(0, 0, 0))
                    self.scene.addItem(text_item)
                    
                    node_positions[key] = (x, y)
                    
                    # Ligne vers le serveur parent
                    parent_key = None
                    for (server_port, sl) in filtered_servers.items():
                        if server_port == node['remote_port']:
                            for srv in sl:
                                if srv.get('pid') in visible_pids:
                                    parent_key = ('server', srv.get('pid'), server_port)
                                    break
                    
                    if parent_key and parent_key in node_positions:
                        parent_x, parent_y = node_positions[parent_key]
                        line = QGraphicsLineItem(x, y - 20, parent_x, parent_y + 30)
                        line.setPen(QPen(QColor(150, 150, 150), 1, Qt.DashLine))
                        self.scene.addItem(line)

        # Ajuster la vue
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
