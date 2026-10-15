"""Every way a Modbus read can go wrong is classified, never raised."""
import pytest
from pymodbus.exceptions import ConnectionException, ModbusIOException
from pymodbus.pdu import ExceptionResponse

from register_maps import (
    CONNECTION_ERROR, DECODE_ERROR, DEFAULT_REGISTER_MAP, INVALID_RESPONSE, MODBUS_EXCEPTION,
    REGISTER_MAPS, SUCCESS, TIMEOUT, decode_registers, read_gauge,
)


class _Resp:
    def __init__(self, registers):
        self.registers = registers

    def isError(self):
        return False


class _Client:
    def __init__(self, result=None, raises=None):
        self.result, self.raises, self.calls = result, raises, []

    def read_holding_registers(self, address, count, unit):
        self.calls.append((address, count, unit))
        if self.raises:
            raise self.raises
        return self.result


def test_default_map_is_the_one_the_app_always_used():
    m = DEFAULT_REGISTER_MAP
    assert (m.address, m.count, m.value_index, m.scale, m.unit) == (3, 2, 1, 1000.0, "mbar")
    assert REGISTER_MAPS["pirani_default"] is m


def test_success_decodes_the_second_register_in_mbar_and_addresses_the_slave():
    c = _Client(_Resp([0, 123]))
    r = read_gauge(c, 7)
    assert (r.status, r.value, r.error) == (SUCCESS, 0.123, None)
    assert c.calls == [(3, 2, 7)]


def test_timeout_is_classified():
    r = read_gauge(_Client(ModbusIOException("No Response received from the remote unit")), 1)
    assert (r.status, r.value) == (TIMEOUT, None)
    assert read_gauge(_Client(None), 1).status == TIMEOUT


def test_other_io_problems_are_invalid_responses():
    r = read_gauge(_Client(ModbusIOException("Unable to decode response")), 1)
    assert r.status == INVALID_RESPONSE


def test_modbus_exception_response_is_classified_with_its_code():
    r = read_gauge(_Client(ExceptionResponse(0x03, 2)), 1)
    assert r.status == MODBUS_EXCEPTION and "2" in r.error


def test_lost_connection_is_a_connection_error_not_a_crash():
    for exc in (ConnectionException("gone"), ConnectionResetError("reset"), OSError("net down")):
        assert read_gauge(_Client(raises=exc), 1).status == CONNECTION_ERROR


def test_too_few_registers_is_an_invalid_response():
    assert read_gauge(_Client(_Resp([5])), 1).status == INVALID_RESPONSE
    assert read_gauge(_Client(_Resp(None)), 1).status == INVALID_RESPONSE


def test_undecodable_register_is_a_decode_error():
    assert read_gauge(_Client(_Resp([0, "garbage"])), 1).status == DECODE_ERROR
    assert decode_registers([0, float("nan")], DEFAULT_REGISTER_MAP).status == DECODE_ERROR
    assert decode_registers([0, float("inf")], DEFAULT_REGISTER_MAP).status == DECODE_ERROR


def test_unexpected_errors_do_not_escape():
    assert read_gauge(_Client(raises=RuntimeError("boom")), 1).status == INVALID_RESPONSE


@pytest.mark.parametrize("raw,expected", [(0, 0.0), (1, 0.001), (65535, 65.535)])
def test_scaling(raw, expected):
    assert decode_registers([0, raw], DEFAULT_REGISTER_MAP).value == pytest.approx(expected)
