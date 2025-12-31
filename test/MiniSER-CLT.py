"""
Test Network Monitor - Serveur et clients TCP
Lance un serveur et plusieurs clients pour tester l'outil de visualisation
"""

import socket
import threading
import time
import random


class SimpleServer:
    """Serveur TCP simple"""
    
    def __init__(self, host='127.0.0.1', port=8888):
        self.host = host
        self.port = port
        self.running = False
        self.clients_count = 0
        
    def handle_client(self, client_socket, address):
        """Gère un client connecté"""
        self.clients_count += 1
        client_id = self.clients_count
        print(f"[SERVEUR] Client #{client_id} connecté depuis {address}")
        
        try:
            while self.running:
                data = client_socket.recv(1024)
                if not data:
                    break
                    
                message = data.decode('utf-8')
                print(f"[SERVEUR] Reçu de client #{client_id}: {message}")
                
                # Répondre au client
                response = f"Serveur a reçu: {message}"
                client_socket.send(response.encode('utf-8'))
                
        except Exception as e:
            print(f"[SERVEUR] Erreur avec client #{client_id}: {e}")
        finally:
            client_socket.close()
            print(f"[SERVEUR] Client #{client_id} déconnecté")
    
    def start(self):
        """Démarre le serveur"""
        self.running = True
        server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        try:
            server_socket.bind((self.host, self.port))
            server_socket.listen(5)
            print(f"[SERVEUR] En écoute sur {self.host}:{self.port}")
            
            while self.running:
                server_socket.settimeout(1.0)
                try:
                    client_socket, address = server_socket.accept()
                    # Gérer chaque client dans un thread séparé
                    client_thread = threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, address),
                        daemon=True
                    )
                    client_thread.start()
                except socket.timeout:
                    continue
                    
        except Exception as e:
            print(f"[SERVEUR] Erreur: {e}")
        finally:
            server_socket.close()
            print("[SERVEUR] Arrêté")
    
    def stop(self):
        """Arrête le serveur"""
        self.running = False


class SimpleClient:
    """Client TCP simple"""
    
    def __init__(self, client_id, host='127.0.0.1', port=8888):
        self.client_id = client_id
        self.host = host
        self.port = port
        self.running = False
        
    def start(self):
        """Démarre le client"""
        self.running = True
        
        try:
            # Connexion au serveur
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((self.host, self.port))
            print(f"[CLIENT {self.client_id}] Connecté au serveur {self.host}:{self.port}")
            
            message_count = 0
            
            while self.running:
                # Envoyer un message
                message_count += 1
                message = f"Message {message_count} du client {self.client_id}"
                client_socket.send(message.encode('utf-8'))
                print(f"[CLIENT {self.client_id}] Envoyé: {message}")
                
                # Recevoir la réponse
                response = client_socket.recv(1024).decode('utf-8')
                print(f"[CLIENT {self.client_id}] Réponse: {response}")
                
                # Attendre un peu avant le prochain message
                time.sleep(random.uniform(2, 5))
                
        except Exception as e:
            print(f"[CLIENT {self.client_id}] Erreur: {e}")
        finally:
            client_socket.close()
            print(f"[CLIENT {self.client_id}] Déconnecté")
    
    def stop(self):
        """Arrête le client"""
        self.running = False


class MultiServerTest:
    """Lance plusieurs serveurs pour tester"""
    
    def __init__(self):
        self.servers = []
        
    def start_servers(self, ports=[8888, 9000, 9001]):
        """Démarre plusieurs serveurs sur différents ports"""
        for port in ports:
            server = SimpleServer(port=port)
            thread = threading.Thread(target=server.start, daemon=True)
            thread.start()
            self.servers.append(server)
            time.sleep(0.5)


def run_test(num_clients=3, num_servers=2, duration=60):
    """
    Lance un test complet
    
    Args:
        num_clients: Nombre de clients par serveur
        num_servers: Nombre de serveurs à lancer
        duration: Durée du test en secondes
    """
    print("=" * 60)
    print("TEST NETWORK MONITOR")
    print("=" * 60)
    print(f"Configuration:")
    print(f"  - {num_servers} serveur(s)")
    print(f"  - {num_clients} client(s) par serveur")
    print(f"  - Durée: {duration} secondes")
    print("=" * 60)
    
    # Définir les ports des serveurs
    base_port = 8888
    server_ports = [base_port + i for i in range(num_servers)]
    
    # Lancer les serveurs
    print("\n[MAIN] Démarrage des serveurs...")
    servers = []
    for port in server_ports:
        server = SimpleServer(port=port)
        thread = threading.Thread(target=server.start, daemon=True)
        thread.start()
        servers.append(server)
        time.sleep(0.5)
    
    print(f"[MAIN] {len(servers)} serveur(s) démarré(s)")
    
    # Attendre que les serveurs soient prêts
    time.sleep(2)
    
    # Lancer les clients
    print(f"\n[MAIN] Démarrage de {num_clients * num_servers} clients...")
    clients = []
    client_id = 1
    
    for port in server_ports:
        for _ in range(num_clients):
            client = SimpleClient(client_id=client_id, port=port)
            thread = threading.Thread(target=client.start, daemon=True)
            thread.start()
            clients.append(client)
            client_id += 1
            time.sleep(0.3)
    
    print(f"[MAIN] {len(clients)} client(s) démarré(s)")
    
    print("\n" + "=" * 60)
    print("TEST EN COURS - Lancez maintenant votre Network Monitor!")
    print("=" * 60)
    print(f"\nPorts des serveurs: {', '.join(map(str, server_ports))}")
    print(f"Le test s'arrêtera dans {duration} secondes...")
    print("\nAppuyez sur Ctrl+C pour arrêter avant\n")
    
    # Laisser tourner pendant la durée spécifiée
    try:
        time.sleep(duration)
    except KeyboardInterrupt:
        print("\n[MAIN] Interruption manuelle")
    
    # Arrêter tout
    print("\n[MAIN] Arrêt des clients...")
    for client in clients:
        client.stop()
    
    time.sleep(1)
    
    print("[MAIN] Arrêt des serveurs...")
    for server in servers:
        server.stop()
    
    time.sleep(1)
    print("\n[MAIN] Test terminé!")


def run_simple_test():
    """Test simple avec 1 serveur et 3 clients"""
    run_test(num_clients=3, num_servers=1, duration=120)


def run_complex_test():
    """Test complexe avec plusieurs serveurs"""
    run_test(num_clients=4, num_servers=3, duration=120)


if __name__ == "__main__":
    import sys
    
    print("\nChoisissez un test:")
    print("1. Test simple (1 serveur, 3 clients)")
    print("2. Test complexe (3 serveurs, 4 clients chacun)")
    print("3. Test personnalisé")
    
    choice = input("\nVotre choix (1-3): ").strip()
    
    if choice == "1":
        run_simple_test()
    elif choice == "2":
        run_complex_test()
    elif choice == "3":
        try:
            num_servers = int(input("Nombre de serveurs: "))
            num_clients = int(input("Nombre de clients par serveur: "))
            duration = int(input("Durée en secondes: "))
            run_test(num_clients, num_servers, duration)
        except ValueError:
            print("Valeurs invalides, lancement du test simple")
            run_simple_test()
    else:
        print("Choix invalide, lancement du test simple")
        run_simple_test()