import psutil

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
                    # if conn.pid not in processes:
                    try:
                        proc = psutil.Process(conn.pid)
                        processes[conn.pid] = proc.name()
                    except (psutil.NoSuchProcess, psutil.AccessDenied):
                        processes[conn.pid] = "Unknown"
                    # else:
                        # print("Processus non-pris en compte :")
                        # print(conn)
                    
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
    
    def analyze_connections_old(connections):
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
    
    @staticmethod
    def analyze_connections(connections):
        servers = {}  # port -> liste de PIDs serveurs
        clients = {}  # (server_port, client_pid, client_port) -> info
        ephemer_port_min = 49152
        ephemer_port_max = 65535

        # 1Indexer toutes les adresses locales
        local_index = {}
        for conn in connections:
            if conn['local_ip'] and conn['local_port']:
                key = (conn['local_ip'], conn['local_port'])
                local_index.setdefault(key, []).append(conn)

        # Détecter les serveurs via correspondance remote → local
        for conn in connections:
            if conn['status'] != 'ESTABLISHED':
                continue

            remote_key = (conn['remote_ip'], conn['remote_port'])

            if remote_key in local_index:
                # serveur local trouvé
                for server_conn in local_index[remote_key]:
                    port = server_conn['local_port']
                    servers.setdefault(port, [])

                    server_info = {
                        'pid': server_conn['pid'],
                        'process': server_conn['process'],
                        'address': server_conn['local_addr']
                    }

                    # if ephemer_port_min < port and ephemer_port_max > port:
                    #    pass
                    #if servers.get(local_index[remote_key][0]["remote_port"]):
                    #    pass

                    if server_info not in servers[port]:
                        servers[port].append(server_info)

                    # enregistrer le client
                    key = (port, conn['pid'], conn['local_port'])
                    clients[key] = {
                        'pid': conn['pid'],
                        'process': conn['process'],
                        'local_addr': conn['local_addr'],
                        'remote_addr': conn['remote_addr'],
                        'remote_port': conn['remote_port'],
                        'is_remote': False
                    }

            else:
                # serveur externe
                key = (conn['remote_port'], conn['pid'], conn['local_port'])
                clients[key] = {
                    'pid': conn['pid'],
                    'process': conn['process'],
                    'local_addr': conn['local_addr'],
                    'remote_addr': conn['remote_addr'],
                    'remote_port': conn['remote_port'],
                    'is_remote': True
                }

        return servers, clients

