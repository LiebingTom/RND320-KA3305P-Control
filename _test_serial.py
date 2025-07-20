from src.ka3305p import KA3305P

if __name__ == "__main__":
    psu = KA3305P(port='COM5') 

    psu.disable_output()

    # print("IDN:", psu.identify())
    psu.set_voltage(1, 12.0)
    psu.set_current(1, 1.5)
    input("Continue...")
    psu.enable_output()
    # input("Continue...")
    # psu.lock_panel()
    # input("Continue...")
    # psu.unlock_panel()
    input("Continue...")
    print(f"Current setting of channel 1: {psu.get_current_setting(1)}")
    print(f"Voltage setting of channel 1: {psu.get_voltage_setting(1)}")
    print(f"Current of channel 1: {psu.read_current(1)}")
    print(f"Voltage of channel 1: {psu.read_voltage(1)}")

    psu.disable_output(1)
    # print("Set voltage CH1:", psu.get_voltage_setting(1))
    # print("Measured voltage CH1:", psu.get_measured_voltage(1))

    psu.disconnect()