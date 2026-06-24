from pymodbus.client.sync import ModbusTcpClient

GAUGE_IP = "192.168.1.3"
PORT = 502

UNIT_IDS = [1, 2, 3, 4]

START_ADDR = 0
END_ADDR = 50

def print_response(rr, reg_type, addr):
    try:
        if rr is None:
            return

        if rr.isError():
            return

        if hasattr(rr, "registers"):
            print(f"{reg_type} Addr {addr:03d}: {rr.registers}")

    except Exception as e:
        print(f"{reg_type} Addr {addr:03d}: Exception {e}")


def scan_holding_registers(client, unit):
    print(f"\n===== UNIT ID {unit} : HOLDING REGISTERS =====")

    for addr in range(START_ADDR, END_ADDR):
        try:
            rr = client.read_holding_registers(
                address=addr,
                count=2,
                unit=unit
            )

            print_response(rr, "HR", addr)

        except Exception as e:
            print(f"HR Addr {addr:03d}: {e}")


def scan_input_registers(client, unit):
    print(f"\n===== UNIT ID {unit} : INPUT REGISTERS =====")

    for addr in range(START_ADDR, END_ADDR):
        try:
            rr = client.read_input_registers(
                address=addr,
                count=2,
                unit=unit
            )

            print_response(rr, "IR", addr)

        except Exception as e:
            print(f"IR Addr {addr:03d}: {e}")


def main():

    print("=" * 60)
    print("MODBUS TCP PIRANI GAUGE DIAGNOSTIC")
    print("=" * 60)
    print(f"IP Address : {GAUGE_IP}")
    print(f"Port       : {PORT}")
    print()

    client = ModbusTcpClient(
        host=GAUGE_IP,
        port=PORT,
        timeout=2
    )

    if not client.connect():
        print("ERROR: Unable to connect to device")
        return

    print("SUCCESS: TCP Connection Established")

    for unit in UNIT_IDS:

        print("\n" + "=" * 60)
        print(f"SCANNING UNIT ID = {unit}")
        print("=" * 60)

        scan_holding_registers(client, unit)
        scan_input_registers(client, unit)

    client.close()

    print("\n" + "=" * 60)
    print("SCAN COMPLETED")
    print("=" * 60)


if __name__ == "__main__":
    main()