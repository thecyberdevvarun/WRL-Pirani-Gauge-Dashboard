"""Test environment: small fake lines, independent of the real .env.

The real .env must never influence a test run (it would add settings and
change results depending on whose machine runs the tests), so loading it is
switched off before the application is imported. Everything the application
reads is then set explicitly below.
"""
import os

import dotenv

dotenv.load_dotenv = lambda *args, **kwargs: False   # applies to every `from dotenv import load_dotenv`

# Drop anything the surrounding shell may have set for the application, so the
# values below are the only configuration the tests ever see.
for _name in list(os.environ):
    if _name.startswith(("LINE_", "USER_", "POLL", "MODBUS_", "STALE_", "SESSION_")) or _name in (
        "LINES", "USERS", "SECRET_KEY", "DB_SERVER", "DB_NAME", "DB_USER",
    ):
        del os.environ[_name]

os.environ["DISABLE_WORKERS"] = "1"
os.environ["DB_PASSWORD"] = "test-only"
os.environ["SECRET_KEY"] = "test-secret-key"

os.environ["LINES"] = "ALPHA,BETA"

# Poll every line from this process (the tests drive the service directly).
os.environ["POLLING_MODE"] = "centralized"

# Extra logins: an admin for every line, and an operator for two of them.
os.environ["USERS"] = "ROOT,DUAL"
os.environ["USER_ROOT_USERNAME"] = "root"
os.environ["USER_ROOT_PASSWORD"] = "root-pw"
os.environ["USER_ROOT_LINES"] = "ALL"
os.environ["USER_ROOT_ROLE"] = "admin"
os.environ["USER_DUAL_USERNAME"] = "dual"
os.environ["USER_DUAL_PASSWORD"] = "dual-pw"
os.environ["USER_DUAL_LINES"] = "ALPHA,BETA"

os.environ["LINE_ALPHA_LABEL"] = "Alpha Line"
os.environ["LINE_ALPHA_USERNAME"] = "alpha"
os.environ["LINE_ALPHA_PASSWORD"] = "alpha-pw"
os.environ["LINE_ALPHA_GAUGES"] = "6"
os.environ["LINE_ALPHA_GATEWAYS"] = "10.0.0.1:502:1-3,10.0.0.2:5020:4-6"
os.environ["LINE_ALPHA_UPPER_LIMIT"] = "1.0"
os.environ["LINE_ALPHA_SUBNET"] = "10.0.0.0/24"
os.environ["LINE_ALPHA_PC_IP"] = "10.0.0.254"
os.environ["LINE_ALPHA_ROUTER_IP"] = "10.0.0.253"
os.environ["LINE_ALPHA_COMPANY_PC_IP"] = "172.16.0.5"

os.environ["LINE_BETA_LABEL"] = "Beta Line"
os.environ["LINE_BETA_USERNAME"] = "beta"
os.environ["LINE_BETA_PASSWORD"] = "beta-pw"
os.environ["LINE_BETA_GAUGES"] = "4"
os.environ["LINE_BETA_GATEWAYS"] = "10.0.1.1"
os.environ["LINE_BETA_UPPER_LIMIT"] = "2.0"
os.environ["LINE_BETA_DISABLED_GAUGES"] = "2"
