from dotenv import load_dotenv
from pathlib import Path
import os

BASE_DIR = Path(__file__).resolve().parent.parent

dotenv_path = BASE_DIR / '.env'
if dotenv_path.exists():
    load_dotenv(dotenv_path)

DB_HOST = os.getenv('DB_HOST')
DB_PORT = os.getenv('DB_PORT')
DB_NAME = os.getenv('DB_NAME')
DB_USER = os.getenv('DB_USER')
DB_PASSWORD = os.getenv('DB_PASSWORD')

BASE_URL = "https://opensky-network.org/api"
CLIENT_ID = os.getenv('CLIENT_ID')
CLIENT_SECRET = os.getenv('CLIENT_SECRET')
TOKEN_URL = "https://auth.opensky-network.org/auth/realms/opensky-network/protocol/openid-connect/token"

REQUEST_TIMEOUT = 10

env_items = {
    'DB_HOST': DB_HOST,
    'DB_PORT': DB_PORT,
    'DB_NAME': DB_NAME,
    'DB_USER': DB_USER,
    'DB_PASSWORD': DB_PASSWORD,
    'CLIENT_ID': CLIENT_ID,
    'CLIENT_SECRET': CLIENT_SECRET
}

empty_values = [key for key, value in env_items.items() if not value or value.strip() == '']
if empty_values:
    raise ValueError(f"Environment variables not set: {', '.join(empty_values)}")

DIRECTIONS = ["arrival", "departure"]
