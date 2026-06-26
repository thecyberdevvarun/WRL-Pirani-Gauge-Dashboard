import os

from dotenv import load_dotenv

load_dotenv()

MODBUS = {
    "HOST": os.environ.get("MODBUS_HOST", "192.168.1.3"),
    "PORT": int(os.environ.get("MODBUS_PORT", "502")),
}
