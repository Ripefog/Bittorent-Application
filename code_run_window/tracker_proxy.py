from flask import Flask, request, jsonify
import requests
from configs import CFG, Config
config = Config.from_json(CFG)
TRACKER_HOST = config.constants.TRACKER_ADDR_BACKUP[0]
TRACKER_PORT = config.constants.TRACKER_ADDR_BACKUP[1]
MAIN_TRACKER_IP = config.constants.TRACKER_ADDR[0]
MAIN_TRACKER_PORT = config.constants.TRACKER_ADDR[1]

# Configuration
MAIN_TRACKER_URL = f"http://{MAIN_TRACKER_IP}:{MAIN_TRACKER_PORT}/tracker"
BACKUP_TRACKER_URL = f"http://{TRACKER_HOST}:{TRACKER_PORT}/tracker"

app = Flask(__name__)
use_backup = False  # Flag to switch to backup tracker if main tracker is down


def is_tracker_active(host=f"http://{config.constants.TRACKER_ADDR[0]}", port=config.constants.TRACKER_ADDR[1], timeout=2):
    """Checks if the main tracker is active."""
    try:
        response = requests.get(f"{host}:{port}/health", timeout=timeout)
        return response.status_code == 200
    except requests.exceptions.RequestException:
        return False

@app.route('/proxy', methods=['POST'])
def handle_node_request():
    global use_backup
    try:
        # Get JSON data from the node request
        node_data = request.json
        client_ip = request.remote_addr
        client_port = request.environ.get('REMOTE_PORT')
        node_data['addr'] = (client_ip, int(client_port))
        
        if use_backup:
            print("Main tracker failed. Switching to backup tracker.")
            tracker_url = BACKUP_TRACKER_URL
        else:
            if is_tracker_active():
                tracker_url = MAIN_TRACKER_URL
                use_backup=False
            else:
                print("Main tracker failed. Switching to backup tracker.")
                tracker_url = BACKUP_TRACKER_URL
                use_backup=True
        
        tracker_response = requests.post(tracker_url, json=node_data)
        
        # Relay response to node
        tracker_data = tracker_response.json()
        return jsonify(tracker_data), tracker_response.status_code

    except requests.exceptions.RequestException as e:
        print(f"Error forwarding to tracker: {e}")
        return jsonify({"error": "Tracker request failed"}), 503
    except Exception as e:
        print(f"Error handling node request: {e}")
        return jsonify({"error": "Internal proxy error"}), 500



if __name__ == '__main__':
    app.run(host=TRACKER_HOST, port=12367) #cần chỉnh
