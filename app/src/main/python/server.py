import os
import threading
from werkzeug.serving import make_server

_server = None
_server_thread = None

def start_server(data_dir):
    global _server, _server_thread
    os.makedirs(data_dir, exist_ok=True)
    os.environ["APP_DATA_DIR"] = data_dir

    from app import app, init_db
    init_db()

    if _server is None:
        _server = make_server("127.0.0.1", 5001, app, threaded=True)
        _server_thread = threading.Thread(target=_server.serve_forever, daemon=True)
        _server_thread.start()
    return True
