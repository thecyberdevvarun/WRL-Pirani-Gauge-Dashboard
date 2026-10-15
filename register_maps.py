"""Gauge register maps and Modbus read classification.

The one map defined here, ``pirani_default``, is exactly what the application
already used before this module existed: Modbus TCP, holding registers,
start address 3, 2 registers, vacuum = register[1] / 1000 (mbar), addressed to
the gauge's slave ID. It was moved here unchanged so the live poller and the
test runner decode readings from the same definition. A new gauge model is
supported by adding another entry and naming it in LINE_<KEY>_REGISTER_MAP.
"""

import math
from dataclasses import dataclass
from typing import NamedTuple, Optional

from pymodbus.exceptions import ConnectionException, ModbusIOException

# Communication status of one read attempt.
SUCCESS = "success"
TIMEOUT = "timeout"
CONNECTION_ERROR = "connection_error"
INVALID_RESPONSE = "invalid_response"
MODBUS_EXCEPTION = "modbus_exception"
DECODE_ERROR = "decode_error"

COMMUNICATION_STATUSES = (
    SUCCESS, TIMEOUT, CONNECTION_ERROR, INVALID_RESPONSE, MODBUS_EXCEPTION, DECODE_ERROR,
)


@dataclass(frozen=True)
class RegisterMap:
    id: str
    address: int        # first holding register
    count: int          # number of registers requested
    value_index: int    # which returned register holds the measurement
    scale: float        # measurement = register / scale
    unit: str


REGISTER_MAPS = {
    "pirani_default": RegisterMap(
        id="pirani_default", address=3, count=2, value_index=1, scale=1000.0, unit="mbar"
    ),
}
DEFAULT_REGISTER_MAP = REGISTER_MAPS["pirani_default"]


class ReadResult(NamedTuple):
    value: Optional[float]
    status: str
    error: Optional[str]


def decode_registers(registers, reg_map: RegisterMap) -> ReadResult:
    """Turn the raw registers of a successful response into a reading."""
    if not isinstance(registers, (list, tuple)) or len(registers) < reg_map.count:
        return ReadResult(None, INVALID_RESPONSE, "response has too few registers")
    try:
        value = registers[reg_map.value_index] / reg_map.scale
    except Exception as exc:  # non-numeric register, bad scale, ...
        return ReadResult(None, DECODE_ERROR, f"could not decode register: {exc}")
    if not math.isfinite(value):
        return ReadResult(None, DECODE_ERROR, "decoded value is not a finite number")
    return ReadResult(value, SUCCESS, None)


def read_gauge(client, slave_id: int, reg_map: RegisterMap = DEFAULT_REGISTER_MAP) -> ReadResult:
    """One read of one gauge, classified. Never raises for communication problems."""
    try:
        rr = client.read_holding_registers(
            address=reg_map.address, count=reg_map.count, unit=slave_id
        )
    except (ConnectionException, ConnectionError, OSError) as exc:
        return ReadResult(None, CONNECTION_ERROR, str(exc) or exc.__class__.__name__)
    except Exception as exc:
        return ReadResult(None, INVALID_RESPONSE, f"unexpected error: {exc}")

    if rr is None:
        return ReadResult(None, TIMEOUT, "no response from gauge")

    if isinstance(rr, ModbusIOException):
        text = str(rr)
        if "no response" in text.lower() or "timeout" in text.lower():
            return ReadResult(None, TIMEOUT, "no response from gauge")
        return ReadResult(None, INVALID_RESPONSE, text)

    if rr.isError():
        code = getattr(rr, "exception_code", None)
        if code is not None:
            return ReadResult(None, MODBUS_EXCEPTION, f"modbus exception code {code}")
        return ReadResult(None, INVALID_RESPONSE, str(rr))

    return decode_registers(getattr(rr, "registers", None), reg_map)
