from src.ka3305p import KA3305P

if __name__ == "__main__":
    with KA3305P(port="COM10") as psu:
        print("IDN:", psu.idn, "| protocol:", psu.protocol.name)
        print("Status:", psu.status())

        psu.disable_output()
        psu.set_voltage(1, 0.40)
        psu.set_current(1, 0.500)
        print(f"Setpoint CH1: {psu.get_voltage_setting(1)} V, {psu.get_current_setting(1)} A")
        input("Enable output? Enter to continue...")
        psu.set_channel_output(1, True)
        input("Enter to read back...")
        print(psu.measure())
        psu.disable_output()
