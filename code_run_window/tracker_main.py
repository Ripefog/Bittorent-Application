import os
import socket
from threading import Thread, Timer
from collections import defaultdict
import json
import logging
import warnings
import hashlib
import threading
from utils import *
from flask import Flask, request, jsonify
warnings.filterwarnings("ignore")
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext
import requests
from configs import CFG, Config
config = Config.from_json(CFG)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Đường dẫn các file JSON
NODES_INFO_PATH = config.directory.tracker_db_dir + "nodes.json"
FILES_INFO_PATH = config.directory.tracker_db_dir + "files.json"
USERS_INFO_PATH = config.directory.tracker_db_dir + "users.json"  
ADDRESS_INFO_PATH = config.directory.tracker_db_dir + "addrs.json"
# Cấu hình
TRACKER_HOST = 'localhost' #cần chỉnh
TRACKER_PORT = 12345
TRACKER_PORT_LISTEN = 23456

class Tracker:
    def __init__(self, root):
        self.file_owners_list = defaultdict(list)
        self.send_freq_list = defaultdict(int)
        self.has_informed_tracker = defaultdict(bool)
        self.users = self.load_users()
        # Xóa nội dung trong `addrs.json` khi khởi động nếu file đã tồn tại
        if os.path.exists(ADDRESS_INFO_PATH):
            with open(ADDRESS_INFO_PATH, 'w') as f:
                json.dump({}, f)  # Làm rỗng file bằng cách ghi một dictionary trống
        #for UI==========================
        self.root = root
        self.root.title("Tracker HTTP Interface")
        self.root.geometry("600x400")

        # Discover Section
        tk.Label(root, text="Tracker HTTP Interface", font=("Arial", 16)).pack(pady=10)
        tk.Button(root, text="Discover", command=self.discover).pack(pady=5)

        self.discover_text = scrolledtext.ScrolledText(root, width=70, height=10, state='disabled')
        self.discover_text.pack(pady=10)

       # Ping Section
        tk.Label(root, text="Node Ping", font=("Arial", 14)).pack(pady=10)
        self.node_id_entry = tk.Entry(root, width=10)
        self.node_id_entry.pack(pady=5)
        tk.Button(root, text="Ping Node", command=self.ping_node).pack(pady=5)
        self.ping_result = tk.Label(root, text="", font=("Arial", 12))
        self.ping_result.pack(pady=5)

    #discover
    def discover(self):
        try:
            # Mở file ở chế độ đọc để tải dữ liệu
            with open(FILES_INFO_PATH, 'r') as file:
                data = json.load(file)
            # Hiển thị dữ liệu lên giao diện
            self.discover_text.configure(state='normal')
            self.discover_text.delete(1.0, tk.END)
            self.discover_text.insert(tk.END, json.dumps(data, indent=4))
            self.discover_text.configure(state='disabled')
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load data: {e}")
    # Ping Node dựa trên ID nhập vào
    def ping_node(self):
        node_id = self.node_id_entry.get().strip()
        if not node_id:
            messagebox.showerror("Error", "Please enter a Node ID.")
            return

        try:
            # Đọc địa chỉ từ file addrs.json
            if os.path.exists(ADDRESS_INFO_PATH):
                with open(ADDRESS_INFO_PATH, 'r') as addr_file:
                    addresses = json.load(addr_file)

                node_key = f'node{node_id}'  # Định dạng tên key trong file JSON
                if node_key in addresses:
                    addr, port = addresses[node_key]
                    
                    try:
                        response = requests.get(f"http://{addr}:{port}/ping", timeout=5)
                        if response.status_code == 200:
                            self.ping_result.config(text="Node is active")
                        else:
                            self.ping_result.config(text="Node is not active")
                    except requests.ConnectionError:
                        # Node không thể kết nối hoặc không còn hoạt động
                        self.ping_result.config(text="Node is not active")

                else:
                    messagebox.showerror("Error", f"No address found for Node ID: {node_id}")
            else:
                messagebox.showerror("Error", "Address file not found.")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred: {e}")

    def load_users(self):
        """Load user data from JSON file."""
        if os.path.exists(USERS_INFO_PATH):
            with open(USERS_INFO_PATH, 'r') as f:
                return json.load(f)
        else:
            return {}

    def save_users(self):
        """Save user data to JSON file."""
        with open(USERS_INFO_PATH, 'w') as f:
            json.dump(self.users, f, indent=4)

    def hash_password(self, password):
        """Hash a password for secure storage."""
        return hashlib.sha256(password.encode()).hexdigest()

    def register_user(self, username, password):
        """Register a new user."""
        if username in self.users:
            return {"status": "error", "message": "Username already exists"}
        
        hashed_password = self.hash_password(password)
        self.users[username] = {"password": hashed_password}
        self.save_users()
        logging.info(f"User '{username}' registered successfully.")
        return {"status": "success", "message": "User registered successfully"}

    def authenticate_user(self, username, password):
        """Authenticate an existing user."""
        if username not in self.users:
            return {"status": "error", "message": "Username not found"}
        
        hashed_password = self.hash_password(password)
        if self.users[username]["password"] == hashed_password:
            logging.info(f"User '{username}' logged in successfully.")
            return {"status": "success", "message": "Login successful"}
        else:
            return {"status": "error", "message": "Incorrect password"}

    def add_file_owner(self, msg: dict): 
        
        entry = {
            'node_id': msg['node_id'],
            'addr': (msg['addr'][0], msg['listen_port']),
            'filename': msg['filename'],
            'filesize': msg['filesize']
        }
        log_content = f"Node {msg['node_id']} owns {msg['infohash']} and is ready to send."
        logging.info(log_content)

        self.file_owners_list[msg['infohash']].append(json.dumps(entry))
        self.file_owners_list[msg['infohash']] = list(set(self.file_owners_list[msg['infohash']]))
        self.send_freq_list[msg['node_id']] += 1
        self.save_db_as_json()
        
    def update_db_enter(self, msg: dict):
        self.send_freq_list[msg["node_id"]] = 0
        self.save_db_as_json()

    def search_file(self, msg: dict):
        log_content = f"Node {msg['node_id']} is searching for {msg['filename']}"
        logging.info(log_content)

        matched_entries = []
        if msg['infohash'] in self.file_owners_list:
            for json_entry in self.file_owners_list[msg['infohash']]:
                entry = json.loads(json_entry)
                matched_entries.append((entry, self.send_freq_list[entry['node_id']]))
        else:
            logging.info(f"File {msg['filename']} not found in torrent.")

        response = {
            'node_id': msg['node_id'],
            'search_result': matched_entries,
            'filename': msg['filename']
        }
        return response

    def remove_node(self, node_id: int, addr: tuple):
        # Chuyển entry sang dạng JSON để khớp với dữ liệu trong file_owners_list
        entry = json.dumps({
            'node_id': node_id,
            'addr': list(addr)
        })

        # Xóa thông tin về node_id khỏi send_freq_list và has_informed_tracker
        self.send_freq_list.pop(node_id, None)
        self.has_informed_tracker.pop((node_id, addr), None)

        # Duyệt qua từng infohash trong file_owners_list
        for infohash in list(self.file_owners_list.keys()):
            updated_nodes = []

            # Kiểm tra từng entry trong danh sách các node của infohash
            for node_json in self.file_owners_list[infohash]:
                try:
                    node_entry = json.loads(node_json)
                except json.JSONDecodeError as e:
                    logging.error(f"Failed to decode node entry: {e}")
                    continue
                
                # Giữ lại entry nếu node_id không khớp
                if node_entry.get('node_id') != node_id:
                    updated_nodes.append(node_json)

            # Cập nhật lại danh sách node cho infohash
            if updated_nodes:
                self.file_owners_list[infohash] = updated_nodes
            else:
                # Xóa infohash nếu không còn node nào sở hữu file
                del self.file_owners_list[infohash]

        # Lưu lại thay đổi vào file JSON
        self.save_db_as_json()

    def check_nodes_periodically(self, interval: int):
        alive_nodes_ids = set()
        dead_nodes_ids = set()
        for node, has_informed in list(self.has_informed_tracker.items()):
            node_id, node_addr = node
            if has_informed:
                self.has_informed_tracker[node] = False
                alive_nodes_ids.add(node_id)
            else:
                dead_nodes_ids.add(node_id)
                self.remove_node(node_id=node_id, addr=node_addr)

        if alive_nodes_ids or dead_nodes_ids:
            logging.info(f"Node(s) {list(alive_nodes_ids)} are alive, and node(s) {list(dead_nodes_ids)} have left.")

        Timer(interval, self.check_nodes_periodically, args=(interval,)).start()

    def save_db_as_json(self):
        if not os.path.exists(config.directory.tracker_db_dir):
            os.makedirs(config.directory.tracker_db_dir)

        with open(NODES_INFO_PATH, 'w') as nodes_json:
            json.dump({f'node{key}': value for key, value in self.send_freq_list.items()}, nodes_json, indent=4)

        with open(FILES_INFO_PATH, 'w') as files_json:
            json.dump(self.file_owners_list, files_json, indent=4)
  
    def handle_node_request(self, request):
        msg = request.json
        mode = msg['mode']

        if mode == 'OWN':
            self.add_file_owner(msg=msg)
            return {"status": "success", "message": "File owner added"}
        elif mode == 'NEED':
            return self.search_file(msg=msg)
        
        elif mode == 'LOGIN':
            # Xử lý đăng nhập
            username = msg.get('username')
            password = msg.get('password')
            if username and password:
                return self.authenticate_user(username, password)
            else:
                return {"status": "error", "message": "Username and password required"}
        elif mode == 'REGISTER':
            # Xử lý đăng ký
            username = msg.get('username')
            password = msg.get('password')
            if username and password:
                return self.register_user(username, password)
            else:
                return {"status": "error", "message": "Username and password required"}
        elif mode == 'EXIT': 
            addr=(msg['addr'][0], msg['listen_port'])
            self.remove_node(node_id=msg['node_id'], addr=tuple(addr))
            logging.info(f"Node {msg['node_id']} exited the torrent intentionally.")
            return {"status": "success", "message": "Node exited"}
        elif mode == 'ENTER':
            self.update_db_enter(msg=msg)
            addr = {f'node{msg["node_id"]}': (msg['addr'][0], msg['listen_tracker_port'])}
            

            # Tải dữ liệu hiện có từ addrs.json nếu file tồn tại
            if os.path.exists(ADDRESS_INFO_PATH):
                with open(ADDRESS_INFO_PATH, 'r') as addrs_json:
                    addresses = json.load(addrs_json)
            else:
                addresses = {}

            # Thêm địa chỉ mới vào danh sách địa chỉ hiện có
            addresses.update(addr)

            # Ghi lại toàn bộ dữ liệu vào addrs.json
            with open(ADDRESS_INFO_PATH, 'w') as addrs_json:
                json.dump(addresses, addrs_json, indent=4)

            return {"status": "success", "message": "Success enter torrent"}

    def handle_backup_connection(self, conn):
        """Hàm xử lý kết nối từ tracker_backup và gửi dữ liệu từ JSON."""
        try:
            while True:
                request = conn.recv(1024)
                if not request or request.decode() != 'UPDATE_REQUEST':
                    break
                
                # Đọc dữ liệu từ JSON
                with open(NODES_INFO_PATH, 'r') as nodes_file:
                    nodes_data = json.load(nodes_file)
                with open(FILES_INFO_PATH, 'r') as files_file:
                    files_data = json.load(files_file)
                with open(USERS_INFO_PATH, 'r') as users_file:
                    users_data = json.load(users_file)
                update_data = {
                    "file_owners_list": files_data,
                    "send_freq_list": nodes_data,
                    "user_list": users_data
                }

                conn.sendall(json.dumps(update_data).encode())
                logging.info("Sent data update to tracker_backup.")
                
                threading.Event().wait(5)
        except Exception as e:
            logging.error(f"Connection to tracker_backup failed: {e}")
        finally:
            conn.close()

    def listen_for_backup(self):
        """Lắng nghe kết nối từ tracker_backup."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listen_socket:
            listen_socket.bind((TRACKER_HOST, TRACKER_PORT_LISTEN))
            listen_socket.listen()
            logging.info(f"Tracker main is listening for backup on port {TRACKER_PORT_LISTEN}")
            
            while True:
                conn, addr = listen_socket.accept()
                logging.info(f"Connected to tracker_backup at {addr}")
                threading.Thread(target=self.handle_backup_connection, args=(conn,)).start()


    def run_flask(self):
        app = Flask(__name__)

        @app.route('/health', methods=['GET'])
        def health_check():
            return jsonify({"status": "ok"}), 200
        
        @app.route('/tracker', methods=['POST'])
        def tracker_route():
            logging.info("Received request from proxy at /tracker")
            response = self.handle_node_request(request)
            logging.info(f"Sending response: {response}")
            return jsonify(response)

        app.run(host=config.constants.TRACKER_ADDR[0], port=config.constants.TRACKER_ADDR[1])

    def run(self):
        logging.info("Tracker main started.")

        # Start threads for backup listener and periodic node check
        backup_listener_thread = threading.Thread(target=self.listen_for_backup, daemon=True)
        backup_listener_thread.start()

        timer_thread = threading.Thread(target=self.check_nodes_periodically, args=(config.constants.TRACKER_TIME_INTERVAL,), daemon=True)
        timer_thread.start()

        # Run Flask in separate thread
        flask_thread = threading.Thread(target=self.run_flask, daemon=True)
        flask_thread.start()

        # Start Tkinter GUI loop
        self.root.mainloop()

if __name__ == '__main__':
    root = tk.Tk()
    tracker = Tracker(root)
    tracker.run()
