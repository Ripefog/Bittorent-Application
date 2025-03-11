# 🎯 BitTorrent-like Network System

## 🚀 Giới thiệu
Dự án này mô phỏng hệ thống mạng P2P (Peer-to-Peer) tương tự như BitTorrent, nơi các node có thể chia sẻ, tìm kiếm và tải xuống tệp từ mạng. Hệ thống bao gồm các thành phần chính như Node, Tracker, Tracker Backup và Proxy để quản lý kết nối và đảm bảo tính sẵn sàng của dịch vụ.

---

## 🏗 Thành phần chính
Dự án bao gồm các module sau:

📌 **configs.py** - Cấu hình hệ thống bằng JSON.
📌 **node_tcp.py** - Định nghĩa Node tham gia vào mạng.
📌 **tracker_main.py** - Tracker chính quản lý các node và chia sẻ file.
📌 **tracker_backup.py** - Tracker dự phòng để đảm bảo tính liên tục của hệ thống.
📌 **tracker_proxy.py** - Proxy trung gian để định tuyến các yêu cầu giữa node và tracker.
📌 **utils.py** - Các hàm tiện ích hỗ trợ việc xử lý mạng và ghi log.

---

## 🛠 Cách sử dụng

### 📌 1. Cài đặt môi trường
Dự án yêu cầu Python 3.7 trở lên. Trước khi chạy, hãy cài đặt các thư viện cần thiết:

```bash
pip install -r requirements.txt
```

### 📌 2. Chạy các thành phần

#### ▶ Chạy Tracker Chính
```bash
python tracker_main.py
```

#### ▶ Chạy Tracker Backup
```bash
python tracker_backup.py
```

#### ▶ Chạy Proxy
```bash
python tracker_proxy.py
```

#### ▶ Chạy Node
Mỗi node có thể được khởi chạy trên các máy khác nhau hoặc cùng một máy nhưng trên cổng khác nhau.
```bash
python node_tcp.py
```

---

## 🔄 Cách Hoạt Động

### 🔑 1. **Đăng ký / Đăng nhập**
✅ Mỗi Node cần đăng ký hoặc đăng nhập để tham gia mạng.
✅ Xác thực thực hiện qua `tracker_proxy.py`, sử dụng `tracker_main.py` làm cơ sở dữ liệu người dùng.

### 📤 2. **Chia sẻ tệp**
✅ Node có thể đăng ký file với tracker bằng cách đặt chế độ "OWN".
✅ Khi một Node khác tìm kiếm file, tracker sẽ trả về danh sách các Node sở hữu tệp đó.

### 📥 3. **Tải tệp xuống**
✅ Node tải tệp xuống từ nhiều nguồn cùng lúc để tăng tốc độ tải.
✅ Sau khi tải xong, file sẽ được chia sẻ lại với mạng.

### 🛡 4. **Cơ chế dự phòng**
✅ Nếu tracker chính bị lỗi, proxy sẽ tự động chuyển sang tracker dự phòng.
✅ Tracker dự phòng định kỳ cập nhật dữ liệu từ tracker chính.

---

## ⚙ Cấu Hình
Các cài đặt quan trọng được lưu trong `configs.py`, bao gồm:
- 📁 Thư mục lưu trữ file và log.
- 🌐 Địa chỉ IP và cổng của tracker, proxy.
- ⚡ Các tham số liên quan đến chia sẻ file (kích thước buffer, số lượng peer tối đa, v.v.).

## 📜 Ghi Log
📝 Mỗi node và tracker sẽ ghi log vào thư mục `logs/` giúp theo dõi hoạt động hệ thống.

## 📌 Lưu ý
❗ Hệ thống hiện chỉ hỗ trợ kết nối nội bộ (`localhost`).
❗ Để triển khai trên nhiều máy tính, cần chỉnh sửa địa chỉ IP trong `configs.py`.

---

© 2024 - BitTorrent-like Network System 🎉

