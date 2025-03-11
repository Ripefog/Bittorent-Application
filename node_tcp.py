import socket
import requests
import sys
import argparse
from threading import Thread, Timer
from operator import itemgetter
import os
import json
import time
import hashlib
from utils import *
import mmap
import warnings
import tkinter as tk
from tkinter import messagebox, scrolledtext, filedialog
from flask import Flask, jsonify
import logging
import time  # Import time module
warnings.filterwarnings("ignore")

from configs import CFG, Config
config = Config.from_json(CFG)

PROXY_ADDRESS = "http://localhost:12367/proxy" #cần chỉnh

class Node:
    def __init__(self):
        # self.node_id = node_id
        self.root = tk.Tk()
        self.root.title("BitTorrent-like Network System")
        self.root.geometry("400x300")
        
        # Đầu tiên, hiển thị giao diện đăng nhập
        self.show_login_screen()

        # Các biến được khởi tạo sau khi đăng nhập thành công
      
        self.rcv_socket = None
        self.send_socket = None
        self.files = []
        self.is_in_send_mode = False
        self.downloaded_files = {}
        self.listen_port = None
        
        self.file_entry_list = []  # Danh sách lưu các file cần tải
        
        # Khởi tạo Flask app trong __init__ để dùng trong các method khác
        self.app = Flask(__name__)
        self.listen_tracker_port = generate_random_port()
        self.next_call = time.time()
        # Định nghĩa endpoint cho Flask app
        @self.app.route('/ping', methods=['GET'])
        def ping():
            return jsonify({"status": "active"}), 200
        
        
        self.root.mainloop()


    def run_flask(self): #cần chỉnh
        """Chạy Flask server"""
        self.app.run(host="127.0.0.1", port=self.listen_tracker_port, debug=False, use_reloader=False)

    def login(self):
        node_id = self.node_id_entry.get()
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not node_id or not username or not password:
            messagebox.showerror("Error", "Please enter node ID, username, and password.")
            return

        self.node_id = int(node_id)  # Set the node ID

        # Gửi yêu cầu đăng nhập đến tracker
        payload = {
            'username': username,
            'password': password,
            'mode': 'LOGIN'
        }
        response = requests.post(PROXY_ADDRESS, json=payload)

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('status') == 'success':
                if self.node_id is not None:
                    messagebox.showinfo("Login", "Login successful!")
                    self.initialize_node()  # Khởi tạo node và chuyển sang giao diện chính
                else:
                    messagebox.showerror("Login Failed", "Invalid response: missing node ID.")
            else:
                messagebox.showerror("Login Failed", response_data.get('message', "Unknown error."))
        else:
            messagebox.showerror("Error", "Failed to connect to tracker.")

    def register(self):
        username = self.username_entry.get()
        password = self.password_entry.get()

        if not username or not password:
            messagebox.showerror("Error", "Please enter both username and password.")
            return

        # Gửi yêu cầu đăng ký đến tracker
        payload = {
            'username': username,
            'password': password,
            'mode': 'REGISTER'
        }
        response = requests.post(PROXY_ADDRESS, json=payload)

        if response.status_code == 200:
            response_data = response.json()
            if response_data.get('status') == 'success':
                messagebox.showinfo("Registration", "Account created successfully. Please login.")
            else:
                messagebox.showerror("Registration Failed", response_data.get('message', "Unknown error."))
        else:
            messagebox.showerror("Error", "Failed to connect to tracker.")
   
    def show_login_screen(self):
        """Hiển thị giao diện đăng nhập."""
        # Xóa mọi thành phần giao diện cũ
        for widget in self.root.winfo_children():
            widget.destroy()

        # Tạo giao diện đăng nhập
        self.root.geometry("400x300")
        login_frame = tk.Frame(self.root)
        login_frame.pack(pady=20)

        tk.Label(login_frame, text="Node ID:").grid(row=0, column=0, padx=5, pady=5)
        self.node_id_entry = tk.Entry(login_frame)
        self.node_id_entry.grid(row=0, column=1, padx=5, pady=5)

        tk.Label(login_frame, text="Username:").grid(row=1, column=0, padx=5, pady=5)
        self.username_entry = tk.Entry(login_frame)
        self.username_entry.grid(row=1, column=1, padx=5, pady=5)

        tk.Label(login_frame, text="Password:").grid(row=2, column=0, padx=5, pady=5)
        self.password_entry = tk.Entry(login_frame, show="*")
        self.password_entry.grid(row=2, column=1, padx=5, pady=5)

        tk.Button(login_frame, text="Login", command=self.login).grid(row=3, column=0, padx=5, pady=5)
        tk.Button(login_frame, text="Register", command=self.register).grid(row=3, column=1, padx=5, pady=5)

    def initialize_node(self):
        """Khởi tạo node sau khi đăng nhập thành công và hiển thị giao diện chính."""
        # Xóa giao diện đăng nhập
        for widget in self.root.winfo_children():
            widget.destroy()

        # Khởi tạo các thuộc tính cho Node
        self.rcv_socket = self.set_socket(generate_random_port())
        self.send_socket = self.set_socket(generate_random_port())
        self.files = self.fetch_owned_files()
        self.listen_port = self.send_socket.getsockname()[1]
        
        # Hiển thị giao diện chính
        self.show_main_screen()

        # Gửi yêu cầu đăng ký node vào mạng torrent
        self.enter_torrent()
        
        # Khởi động Flask server trong luồng riêng
        flask_thread = Thread(target=self.run_flask)
        flask_thread.setDaemon(True)
        flask_thread.start()
        # Tạo luồng để thông báo trạng thái "sống" với tracker
        timer_thread = Thread(target=self.inform_tracker_periodically, args=(config.constants.NODE_TIME_INTERVAL,))
        timer_thread.setDaemon(True)
        timer_thread.start()

    def show_main_screen(self):
        """Hiển thị giao diện chính của Node sau khi đăng nhập thành công."""
        self.root.geometry("800x600")

        # Node Registration Panel
        self.node_frame = tk.Frame(self.root)
        self.node_frame.pack(pady=10)

        # File Search, Upload, and Download Panel
        self.file_frame = tk.Frame(self.root)
        self.file_frame.pack(pady=10)

        tk.Label(self.file_frame, text="File Name:").grid(row=0, column=0, padx=5)
        self.file_entry = tk.Entry(self.file_frame)
        self.file_entry.grid(row=0, column=1, padx=5)

        tk.Button(self.file_frame, text="Search File", command=lambda: self.search_torrent(self.file_entry.get())).grid(row=0, column=2, padx=5)
        tk.Button(self.file_frame, text="Upload File", command=self.set_send_mode).grid(row=0, column=3, padx=5)
        tk.Button(self.file_frame, text="Download File", command=lambda: self.set_download_mode(self.file_entry.get())).grid(row=0, column=4, padx=5)
        tk.Button(self.file_frame, text="Logout", command=self.exit_node).grid(row=0, column=5, padx=5)
        # Download Status
        self.download_frame = tk.Frame(self.root)
        self.download_frame.pack(pady=10)
        tk.Label(self.download_frame, text="Download Progress:").grid(row=0, column=0, padx=5)

        self.progress_text = scrolledtext.ScrolledText(self.download_frame, width=60, height=10, state='disabled')
        self.progress_text.grid(row=1, column=0, padx=5, pady=5)

        # Log Console
        self.log_frame = tk.Frame(self.root)
        self.log_frame.pack(pady=10)
        tk.Label(self.log_frame, text="Log Console:").grid(row=0, column=0, padx=5)

        self.log_text = scrolledtext.ScrolledText(self.log_frame, width=80, height=10, state='disabled')
        self.log_text.grid(row=1, column=0, padx=5, pady=5)
        


    def log_message(self, message):
        """Log message to UI log console with rate limiting"""
        current_time = time.time()
        if current_time - self.last_log_time >= self.log_delay:
            self.log_text.configure(state='normal')
            self.log_text.insert(tk.END, f"[Node {self.node_id}] {message}\n")
            self.log_text.configure(state='disabled')
            self.log_text.see(tk.END)
            self.last_log_time = current_time
            # Force UI update
            self.root.update_idletasks()

    def update_progress(self, message):
        """Update download progress in UI"""
        self.progress_text.configure(state='normal')
        self.progress_text.insert(tk.END, f"[Node {self.node_id}] {message}\n")
        self.progress_text.configure(state='disabled')
        self.progress_text.see(tk.END)
        # Force UI update
        self.root.update_idletasks()
   
    def hash_filename(self, filename: str) -> str:
        """Băm tên tệp bằng SHA-256"""
        return hashlib.sha256(filename.encode()).hexdigest()

    def set_socket(self, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Using TCP
        sock.bind(('localhost', port)) #cần chỉnh
        return sock
    
    def log_message(self, message):
        self.log_text.configure(state='normal')
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.configure(state='disabled')
        self.log_text.see(tk.END)

    def register_node(self):
        node_id = self.node_id_entry.get()
        if node_id:
            self.enter_torrent()
            self.log_message(f"Node {node_id} registered successfully.")
        else:
            messagebox.showerror("Input Error", "Node ID is required.")

    def exit_node(self):
        self.exit_torrent()
        self.log_message(f"Node {self.node_id} exited successfully.")
        self.root.quit()     # Close the Tkinter window
        sys.exit()
    def send_segment(self, sock: socket.socket, data: bytes, addr: tuple):
        """Gửi dữ liệu trực tiếp qua kết nối TCP"""
        try:
            # Không cần connect lại nếu socket đã được kết nối
            sock.sendall(data)
        except OSError as e:
            if e.errno == 10056:  # Lỗi đã kết nối
                pass  # Bỏ qua lỗi này
            else:
                raise e  # Ném lại lỗi nếu không phải lỗi đã kết nối

    def split_file_to_chunks(self, file_path: str, rng: tuple) -> list:
        with open(file_path, "r+b") as f:
            mm = mmap.mmap(f.fileno(), 0)[rng[0]: rng[1]]
            piece_size = config.constants.CHUNK_PIECES_SIZE
            return [mm[p: p + piece_size] for p in range(0, rng[1] - rng[0], piece_size)]

    def reassemble_file(self, chunks: list, file_path: str):
        with open(file_path, "wb+") as f:  # Open in binary write mode
            for ch in chunks:
                if isinstance(ch, int):
                    ch = str(ch).encode()  # Chuyển đổi int sang chuỗi rồi encode thành bytes nếu cần thiết
                elif isinstance(ch, str):
                    ch = ch.encode()  # Chuyển đổi chuỗi thành bytes nếu cần
                f.write(ch)
            f.flush()
            f.close()

    def send_chunk(self, conn, filename: str, rng: tuple, dest_node_id: int):
        file_path = f"{config.directory.node_files_dir}node{self.node_id}/{filename}"
        chunk_pieces = self.split_file_to_chunks(file_path=file_path, rng=rng)
        # Lấy địa chỉ của node được gửi đến thông qua kết nối conn
        peer_address = conn.getpeername()  # Trả về tuple (IP, cổng)
        print(f"Sending chunks to node {dest_node_id} at address {peer_address[0]}:{peer_address[1]}")
        
        for i, p in enumerate(chunk_pieces):
            # Chuẩn bị dữ liệu để gửi
            idx = rng[0] + i  # `idx` được tính theo vị trí thực tế trong file
            msg = {
                "src_node_id": self.node_id,
                "dest_node_id": dest_node_id,
                "filename": filename,
                "range": rng,
                "idx": idx,
                "chunk": p.decode() if isinstance(p, bytes) else p
            }
            
            # Gửi chunk qua kết nối đã có
            conn.sendall(json.dumps(msg).encode())  # Chuyển đổi message thành JSON rồi gửi
            
            log_content = f"The chunk of file {filename} has been sent to node {dest_node_id}!"
            self.log_message(log_content)

        # Thông báo rằng tất cả các chunk đã được gửi xong (idx = -1)
        end_msg = {
            "src_node_id": self.node_id,
            "dest_node_id": dest_node_id,
            "filename": filename,
            "range": rng,
            "idx": -1
        }
        conn.sendall(json.dumps(end_msg).encode())  # Gửi thông báo kết thúc
        
        log_content = f"All chunks of {filename} have been sent to node {dest_node_id}."
        self.log_message(log_content)

    def handle_requests(self, conn, msg: str, addr: tuple):
        try:
            # Chuyển đổi chuỗi JSON thành dictionary
            msg_dict = json.loads(msg)
        except json.JSONDecodeError:
            print(f"Error: Không thể chuyển đổi thông điệp thành JSON: {msg}")
            return
        
        if msg_dict.get("type") == "SIZE_REQUEST":
            # Xử lý yêu cầu kích thước file
            self.tell_file_size(conn=conn, msg=msg_dict)
            print("Xử lý yêu cầu SIZE_REQUEST thành công")
        
        elif msg_dict.get("type") == "CHUNK_REQUEST":
            # Xử lý yêu cầu gửi chunk của file
            # Lấy thông tin từ msg_dict thay vì msg
            self.send_chunk(conn=conn, filename=msg_dict["filename"], rng=msg_dict["range"], dest_node_id=msg_dict["src_node_id"])
            print("Xử lý yêu cầu CHUNK_REQUEST thành công")
        
        else:
            print(f"Yêu cầu không hợp lệ: {msg}")

    def listen(self):
        self.send_socket.listen(5)
        print(f"Node {self.node_id} is now listening on port {self.send_socket.getsockname()[1]}")
        while True:
            conn, addr = self.send_socket.accept()
            print(f"Accepted connection from {addr}")

            # Nhận toàn bộ dữ liệu
            data = conn.recv(config.constants.BUFFER_SIZE)  # Nhận dữ liệu từ kết nối
            if not data:
                print("Không thể nhận được dữ liệu")
                break

            print(f"Received data: {data.decode()}")  # Hiển thị dữ liệu nhận được
            self.handle_requests(conn=conn, msg=data.decode(), addr=addr)  # Gọi hàm handle_requests để xử lý yêu cầu

    def set_send_mode(self):
        file_path = filedialog.askopenfilename(title="Select file to upload")
        filename = os.path.basename(file_path)
        if filename not in self.files:
            self.log_message(f"You don't have {filename}")
            return

        # Send HTTP request to the tracker to announce file ownership
        file_size = os.path.getsize(file_path)
        hashed_filename = self.hash_filename(filename)
        payload = {
            'node_id': self.node_id,
            'mode': 'OWN',
            'infohash': hashed_filename,
            'filename': filename,
            'filesize': file_size,
            'listen_port': self.listen_port
        }
        response = requests.post(PROXY_ADDRESS, json=payload)
        if response.status_code == 200:
            self.log_message(f"Announced ownership of {filename} to tracker.")
        else:
            self.log_message(f"Failed to announce ownership of {filename} to tracker.")

        if self.is_in_send_mode:
            log_content = f"Already in send mode!"
            self.log_message(log_content)
            return
        else:
            self.is_in_send_mode = True
            log_content = f"Waiting for requests..."
            self.log_message(log_content)
            t = Thread(target=self.listen, args=())
            t.setDaemon(True)
            t.start()

    def ask_file_size(self, filename, file_owner):
        peer_ip = file_owner[0]['addr'][0]
        peer_port = file_owner[0]['addr'][1]
        
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.connect((peer_ip, peer_port))
                
                # Tạo yêu cầu dưới dạng JSON
                request = {
                    "type": "SIZE_REQUEST",
                    "filename": filename
                }
                request_str = json.dumps(request)
                s.sendall(request_str.encode())
                

                # Nhận phản hồi kích thước file
                file_size_data = s.recv(config.constants.BUFFER_SIZE)
                file_size_data = file_size_data.decode()
                

                if not file_size_data or not file_size_data.isdigit():
                    print(f"Error: Received invalid file size: {file_size_data}")
                    return -1
                return int(file_size_data)
        except Exception as e:
            print(f"Error during file size request: {e}")
            return -1

    def tell_file_size(self, conn, msg: dict):
        try:
            
            filename = msg["filename"]
            file_path = f"{config.directory.node_files_dir}node{self.node_id}/{filename}"
            file_size = os.path.getsize(file_path)
            response_msg = str(file_size).encode()
            
            # Sử dụng kết nối hiện có từ `ask_file_size`
            conn.sendall(response_msg)
            print(f"Sent file size: {file_size} for file {filename}")
        except Exception as e:
            print(f"Error sending file size: {e}")

    def receive_chunk(self, filename: str, range: tuple, file_owner: tuple):
        dest_node = file_owner[0]

        # Create the request message in plain dictionary format
        request = {
            "type": "CHUNK_REQUEST",
            "src_node_id": self.node_id,
            "filename": filename,
            "range": range
        }

        # Convert the dictionary to JSON string for sending
        request_str = json.dumps(request)

        # Create a socket and connect directly to the destination node
        temp_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        
        try:
            temp_sock.connect(tuple(dest_node["addr"]))  # Connect to the destination node's address
            log_content = f"Connected to node {dest_node['node_id']} at {dest_node['addr']}"
            self.update_progress(f"Connected to node {dest_node['node_id']} at {dest_node['addr']}")

            # Send the request message for chunk data
            temp_sock.sendall(request_str.encode())
            log_content = f"Sent request for chunk of {filename} to node {dest_node['node_id']} at {dest_node['addr']}"
            self.update_progress(f"Sent request for chunk of {filename} to node {dest_node['node_id']}")

            chunks_received = b""  # Buffer for storing the received chunks

            while True:
                # Receive data from the socket
                data = temp_sock.recv(config.constants.BUFFER_SIZE)
                if not data:
                    break  # If no data is received, exit the loop

                chunks_received += data  # Concatenate received data to the buffer

                # Split the chunks based on JSON message boundaries
                try:
                    # Attempt to decode complete messages from the buffer
                    while True:
                        # Find the next valid JSON object
                        message_boundary = chunks_received.find(b"}") + 1
                        if message_boundary == 0:
                            break  # No complete JSON object in the buffer yet
                        json_data = chunks_received[:message_boundary]
                        chunks_received = chunks_received[message_boundary:]

                        # Decode the JSON object
                        chunk_msg = json.loads(json_data.decode())

                        # Check for end-of-transfer signal (idx == -1)
                        if chunk_msg["idx"] == -1:
                            log_content = f"Finished receiving chunks for {filename} from node {dest_node['node_id']}"
                            self.update_progress(f"Finished receiving chunks for {filename} from node {dest_node['node_id']}")
                            # Close socket here only if it's still open
                            if temp_sock and not temp_sock._closed:
                                temp_sock.close()
                            return  # Exit the function after receiving all chunks
                        else: 
                            self.update_progress(f"Received chunk for {filename} from node {dest_node['node_id']}")

                        # Convert chunk to bytes if it's not already
                        chunk = {
                            "idx": chunk_msg["idx"],
                            "chunk": chunk_msg["chunk"].encode() if isinstance(chunk_msg["chunk"], str) else chunk_msg["chunk"]
                        }

                        # Ensure filename exists in downloaded_files as a list
                        if filename not in self.downloaded_files:
                            self.downloaded_files[filename] = []

                        self.downloaded_files[filename].append(chunk)  # Store the chunk in the downloaded files

                except json.JSONDecodeError:
                    # In case the received data is incomplete, wait for more data
                    pass

            self.log_message(f"All chunks for {filename} have been received and saved.")

        except Exception as e:
            self.log_message(f"Error while receiving chunk: {e}")


        finally:
            # Ensure the socket is not closed twice
            if temp_sock and not temp_sock._closed:
                try:
                    temp_sock.close()  # Only close if not already closed
                    self.log_message(f"Socket to node {dest_node['node_id']} closed successfully")
                except OSError as e:
                    self.log_message(f"Error closing socket: {e}")

    def sort_downloaded_chunks(self, filename: str) -> list:
        # Sắp xếp các chunk theo chỉ số idx đã nhận được trong self.downloaded_files
        
        sorted_chunks = sorted(self.downloaded_files[filename], key=itemgetter("idx"))
        # Duyệt qua từng chunk đã sắp xếp theo idx và lưu vào danh sách mới
        sorted_downloaded_chunks = [chunk["chunk"] for chunk in sorted_chunks]
        
        return sorted_downloaded_chunks

    def split_file_owners(self, file_owners: list, filename: str):
        owners = []
        for owner in file_owners:
            if owner[0]['node_id'] != self.node_id:
                owners.append(owner)
        if len(owners) == 0:
            log_content = f"No one has {filename}"
            self.log_message(f"No one has {filename}")
            return
        # sort owners based on their sending frequency
        owners = sorted(owners, key=lambda x: x[1], reverse=True)

        to_be_used_owners = owners[:config.constants.MAX_SPLITTNES_RATE]
        # 1. first ask the size of the file from peers
        log_content = f"You are going to download {filename} from Node(s) {[o[0]['node_id'] for o in to_be_used_owners]}"
        self.log_message(f"You are going to download {filename} from Node(s) {[o[0]['node_id'] for o in to_be_used_owners]}")
        
        file_size = self.ask_file_size(filename=filename, file_owner=to_be_used_owners[0])
        log_content = f"The file {filename} which you are about to download, has size of {file_size} bytes"
        self.log_message(f"The file {filename} which you are about to download, has size of {file_size} bytes")

        # Start timing the download process
        start_time = time.time()

        # 2. Now, we know the size, let's split it equally among peers to download chunks of it from them
        step = file_size / len(to_be_used_owners)
        chunks_ranges = [(round(step*i), round(step*(i+1))) for i in range(len(to_be_used_owners))]

        # 3. Create a thread for each neighbor peer to get a chunk from it
        self.downloaded_files[filename] = []
        neighboring_peers_threads = []
        for idx, obj in enumerate(to_be_used_owners):
            t = Thread(target=self.receive_chunk, args=(filename, chunks_ranges[idx], obj))
            t.setDaemon(True)
            t.start()
            neighboring_peers_threads.append(t)
            # In ra số lượng neighboring_peers_threads
            print(f"Number of threads created: {len(neighboring_peers_threads)}")
        for t in neighboring_peers_threads:
            t.join()


        # print(f"Downloaded chunks for {filename}: {self.downloaded_files[filename]}")
        log_content = "All the chunks of {} has downloaded from neighboring peers. But they must be reassembled!".format(filename)
        self.log_message(f"All chunks of {filename} downloaded and reassembled successfully!")
        print("All the chunks of {} has downloaded from neighboring peers. But they mus")
        
        # 4. Now we have downloaded all the chunks of the file. It's time to sort them.
        sorted_chunks = self.sort_downloaded_chunks(filename=filename)
        
        log_content = f"All the pieces of the {filename} is now sorted and ready to be reassembled."
        self.log_message(log_content)

        # Calculate and log the time taken for the download process
        end_time = time.time()
        download_duration = end_time - start_time
        log_content = f"Download of {filename} completed in {download_duration:.2f} seconds."
        self.log_message(log_content)
        
        # 5. Finally, we assemble the chunks to re-build the file
        total_file = []
        file_path = f"{config.directory.node_files_dir}node{self.node_id}/{filename}"
        for chunk in sorted_chunks:
            total_file.append(chunk)
            
        self.reassemble_file(chunks=total_file,
                             file_path=file_path)
        
        log_content = f"{filename} has successfully downloaded and saved in my files directory."
        self.log_message(log_content)
        self.files.append(filename)
        
        # 6. Sau khi tải xong gửi thông báo đến tracker, sẵn sàng chia sẽ tệp vừa tải
        hashed_filename = self.hash_filename(filename)
        payload = {
            'node_id': self.node_id,
            'mode': 'OWN',
            'infohash': hashed_filename,
            'filename': filename,
            'filesize': file_size,
            'listen_port': self.listen_port
        }
        response = requests.post(PROXY_ADDRESS, json=payload)
        if response.status_code == 200:
            self.log_message(f"Announced ownership of {filename} to tracker.")
        else:
            self.log_message(f"Failed to announce ownership of {filename} to tracker.")

        if self.is_in_send_mode:
            log_content = f"Already in send mode!"
            self.log_message(log_content)
            return
        else:
            self.is_in_send_mode = True
            log_content = f"Waiting for requests..."
            self.log_message(log_content)
            t = Thread(target=self.listen, args=())
            t.setDaemon(True)
            t.start()
        
    #mới cập nhật
    def set_download_mode(self, filename: str):
        # Start a new thread for each file in `file_entry_list`
        for file in self.file_entry_list:
            thread = Thread(target=self.download_file, args=(file,))
            thread.daemon = True  # Make thread a daemon to prevent blocking the main thread
            thread.start()

    def download_file(self, filename: str):
        
        file_path = f"{config.directory.node_files_dir}node{self.node_id}/{filename}"
        if os.path.isfile(file_path):
            log_content = f"You already have this file!"
            self.log_message(log_content)
            return
        else:
            log_content = f"You just started to download {filename}. Let's search it in torrent!"
            self.log_message(log_content)

            tracker_response = self.search_torrent(filename=filename)
            self.log_message(f"Tracker response: {tracker_response}")

            if tracker_response is None:
                self.log_message("No response from tracker!")
                return

            if 'search_result' in tracker_response:
                file_owners = tracker_response['search_result']
                self.split_file_owners(file_owners=file_owners, filename=filename)
            else:
                self.log_message("File not found in torrent!")
             # Sau khi tải xong, xóa file khỏi danh sách
            if filename in self.file_entry_list:
                self.file_entry_list.remove(filename)

    def search_torrent(self, filename: str) -> dict:
        # Gửi yêu cầu HTTP đến tracker để tìm kiếm file
  
        hashed_filename = self.hash_filename(filename)
        payload = {
            'node_id': self.node_id,
            'mode': 'NEED',
            'infohash': hashed_filename,
            'filename': filename,
        }
        
        #mới cập nhật
        if filename and filename not in self.file_entry_list:
            self.file_entry_list.append(filename)  # Thêm file vào danh sách nếu chưa có
        
        try:
            response = requests.post(PROXY_ADDRESS, json=payload)
            if response.status_code == 200:
                tracker_msg = response.json()  # Chuyển đổi phản hồi từ JSON sang dict
                self.log_message(f"Tracker response: {tracker_msg}")  # In ra phản hồi từ tracker
                return tracker_msg
            else:
                self.log_message(f"Failed to search torrent for {filename}.")
                return {}
        except Exception as e:
            self.log_message(f"Error while searching torrent: {e}")
            return {}

    def fetch_owned_files(self) -> list:
        files = []
        node_files_dir = config.directory.node_files_dir + 'node' + str(self.node_id)
        if os.path.isdir(node_files_dir):
            _, _, files = next(os.walk(node_files_dir))
        else:
            os.makedirs(node_files_dir)
        print("FILES: " f'{files}')
        return files

    def exit_torrent(self):
        
        payload = {
            'node_id': self.node_id,
            'mode': 'EXIT',
            'listen_port': self.listen_port
        }
        response = requests.post(PROXY_ADDRESS, json=payload)
        if response.status_code == 200:
            log_content = f"Successfully exited the torrent."
        else:
            log_content = f"Failed to exit the torrent."
        self.log_message(log_content)

    def enter_torrent(self):
        # Using HTTP to register with the tracker
        
        payload = {
            'node_id': self.node_id,
            'mode': 'ENTER',
            'listen_tracker_port': self.listen_tracker_port
        }
        response = requests.post(PROXY_ADDRESS, json=payload)
        if response.status_code == 200:
            log_content = f"Successfully entered the torrent."
        else:
            log_content = f"Failed to enter the torrent."
        self.log_message(log_content)

    def inform_tracker_periodically(self, interval: int):
        log_content = f"I informed the tracker that I'm still alive in the torrent!"
        self.log_message(log_content)

        # Inform tracker via HTTP
        
        payload = {
            'node_id': self.node_id,
            'mode': 'ALIVE'
        }

        requests.post(PROXY_ADDRESS, json=payload)

        # Use the instance variable `self.next_call` for the timing
        self.next_call = self.next_call + interval
        Timer(self.next_call - time.time(), self.inform_tracker_periodically, args=(interval,)).start()

def run():
    # Khởi tạo Node
    node = Node()
    # Chạy mainloop Tkinter
    node.root.mainloop()
    

if __name__ == '__main__':

    run()
