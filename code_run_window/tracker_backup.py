import os
import socket
from threading import Thread, Timer
from collections import defaultdict
import json
import time
import requests
import logging
import hashlib
from utils import *
import warnings
warnings.filterwarnings("ignore")

# implemented classes
from configs import CFG, Config
config = Config.from_json(CFG)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

next_call = time.time()
# Configuration for tracker backup
TRACKER_HOST = config.constants.TRACKER_ADDR_BACKUP[0]
TRACKER_PORT = config.constants.TRACKER_ADDR_BACKUP[1]
MAIN_TRACKER_IP = config.constants.TRACKER_ADDR[0]
MAIN_TRACKER_PORT = config.constants.TRACKER_ADDR[1]
TRACKER_PORT_LISTEN = config.constants.TRACKER_PORT_LISTEN
ADDRESS_INFO_PATH = config.directory.tracker_db_dir + "addrs_backup.json"
USERS_INFO_PATH=config.directory.tracker_db_dir + "users_backup.json"
class Tracker_Backup:
    def __init__(self):
        self.file_owners_list = defaultdict(list)
        self.send_freq_list = defaultdict(int)
        self.has_informed_tracker = defaultdict(bool)
        self.nodes_info_path = config.directory.tracker_db_dir + "nodes_backup.json"
        self.files_info_path = config.directory.tracker_db_dir + "files_backup.json"
        self.update_interval = 5  # Thời gian chờ giữa các lần yêu cầu cập nhật (giây)
        self.main_tracker_active = True  # Biến xác định trạng thái của tracker chính
        self.tracker_update_port = config.constants.tracker_update_port
        self.users = self.load_users()
        if os.path.exists(ADDRESS_INFO_PATH):
            with open(ADDRESS_INFO_PATH, 'w') as f:
                json.dump({}, f)  # Làm rỗng file bằng cách ghi một dictionary trống
                
                          
    def load_users(self):
        """Tải thông tin người dùng từ file JSON."""
        try:
            with open(USERS_INFO_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logging.warning("User data file is empty or corrupt; loading empty user data.")
            return {}  # Trả về dict rỗng nếu file trống hoặc không hợp lệ
        except FileNotFoundError:
            logging.warning("User data file not found; creating new user data.")
            return {}  # Trả về dict rỗng nếu file không tồn tại
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

        # Save nodes' information to nodes_backup.json
        with open(self.nodes_info_path, 'w') as nodes_json:
            json.dump({f'node{key}': value for key, value in self.send_freq_list.items()}, nodes_json, indent=4, sort_keys=True)

        # Save files' information to files_backup.json
        with open(self.files_info_path, 'w') as files_json:
            json.dump(self.file_owners_list, files_json, indent=4, sort_keys=True)

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
            if os.path.exists(ADDRESS_INFO_PATH):
                with open(ADDRESS_INFO_PATH, 'r') as addrs_json:
                    addresses = json.load(addrs_json)
            else:
                addresses = {}
            addresses.update(addr)
            with open(ADDRESS_INFO_PATH, 'w') as addrs_json:
                json.dump(addresses, addrs_json, indent=4)

            return {"status": "success", "message": "Success enter torrent"}
    
    def is_tracker_active(self):
        """Checks if the main tracker is online."""
        try:
            response = requests.get(f"http://{MAIN_TRACKER_IP}:{MAIN_TRACKER_PORT}/health", timeout=2)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
    
    def request_update_from_main_tracker(self):
        """Gửi yêu cầu cập nhật và nhận phản hồi trên cổng ngẫu nhiên."""
        max_attempts = 5  # Số lần thử tối đa với các cổng khác nhau
        successful_connection = False  # Biến để xác định xem có kết nối thành công hay không

        for attempt in range(max_attempts):
            random_port = generate_random_port()
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as send_socket:
                send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                send_socket.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)  # Giữ kết nối
                try:
                    send_socket.bind((TRACKER_HOST, random_port))
                    send_socket.connect((MAIN_TRACKER_IP, TRACKER_PORT_LISTEN))
                    logging.info(f"Connected to main tracker at {MAIN_TRACKER_IP}:{TRACKER_PORT_LISTEN}.")
                    successful_connection = True  # Đánh dấu kết nối thành công

                    # Gửi yêu cầu cập nhật
                    request = 'UPDATE_REQUEST'.encode()
                    send_socket.sendall(request)
                    logging.info("Sent update request to main tracker.")

                    # Nhận phản hồi từ tracker chính
                    data = send_socket.recv(4096)
                    if data:
                        logging.info("Received data from main tracker.")
                        try:
                            update = json.loads(data.decode())  # Giải mã JSON từ phản hồi
                            self.file_owners_list.update(update.get('file_owners_list', {}))
                            received_send_freq_list = update.get('send_freq_list', {})
                            self.send_freq_list.update({key.replace('node', ''): value for key, value in received_send_freq_list.items()})
                            self.save_db_as_json()

                            # Lưu thông tin user vào file backup JSON nếu có
                            user_data = update.get('user_list', {})
                            if user_data:
                                with open(USERS_INFO_PATH, 'w', encoding='utf-8') as backup_file:
                                    json.dump(user_data, backup_file, ensure_ascii=False, indent=4)
                            logging.info("Data successfully updated from main tracker.")
                        except json.JSONDecodeError as e:
                            logging.error(f"Failed to decode response: {e}")
                    else:
                        logging.warning("No data received from main tracker.")
                    break  # Thoát khỏi vòng lặp nếu thành công

                except OSError as e:
                    if e.errno == 10048:  # Lỗi địa chỉ socket bị chiếm
                        logging.warning(f"Port {random_port} is in use; trying another port.")
                        continue  # Thử lại với một cổng khác
                    else:
                        logging.error(f"Unexpected socket error: {e}")
                        break
                except Exception as e:
                    logging.error(f"Error communicating with main tracker: {e}")
                    self.main_tracker_active = False  # Đánh dấu tracker chính ngừng hoạt động
                    break

            # Dừng thử các cổng khác nếu đã kết nối thành công
            if successful_connection:
                break

        # Lên lịch cho lần cập nhật tiếp theo nếu tracker chính vẫn hoạt động
        if self.is_tracker_active():
            Timer(self.update_interval, self.request_update_from_main_tracker).start()
        else:
            self.main_tracker_active = False

    def run(self):
        log_content = "***************** Tracker Backup started *****************"
        logging.info(log_content)

        # Start periodic update requests to main tracker
        
        if self.main_tracker_active:
            if self.is_tracker_active():
                self.request_update_from_main_tracker()
            else:
                self.main_tracker_active=False

        # Start periodic node checking
        timer_thread = Thread(target=self.check_nodes_periodically, args=(config.constants.TRACKER_TIME_INTERVAL,))
        timer_thread.setDaemon(True)
        timer_thread.start()
         # Starting a Flask server for HTTP communication
        from flask import Flask, request, jsonify
        app = Flask(__name__)
        # Starting a Flask server for HTTP communication
        @app.route('/tracker', methods=['POST'])
        def tracker_route():
            if not self.main_tracker_active:
                response = self.handle_node_request(request)
                
                logging.info(f"Backup tracker acting as main tracker, sending response: {response}")
            else:
                response = {"status": "error", "message": "Tracker main is still active"}
            return jsonify(response)

        app.run(host=TRACKER_HOST, port=TRACKER_PORT)




if __name__ == '__main__':
    tracker_backup = Tracker_Backup()
    tracker_backup.run()




