import os
os.environ.setdefault("APP_DATA_DIR", os.environ.get("APP_DATA_DIR", "/var/data"))
from app import app, init_db
init_db()
