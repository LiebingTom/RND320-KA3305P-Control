import serial
from src.commands import *
import time

class KA3305P:
    def __init__(self, port: str = 'COM1'):
        # Initialize the RND320 with the specified serial port. See data sheet page 10 for details.
        # Initialize using the correct COM port
        self.port = port
        self.baudrate = 9600
        self.bytesize = serial.EIGHTBITS
        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE
        self.timeout = 1    # in seconds
        self.ser = None     # Serial connection object will be created in connect method

        self.connect()      # connect to the device upon initialization

    def connect(self):
        """Open serial connection to the KA3305P."""
        try:
            self.ser = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout,  
                xonxoff=False,  # Software flow control
                rtscts=False,   # Hardware flow control
                dsrdtr=False    # DSR/DTR flow control
            )
            if self.ser.is_open:
                print(f"Connected to {self.port}")
        except serial.SerialException as e:
            print(f"Failed to connect to {self.port}: {e}")

    def disconnect(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            self.ser = None
            print(f"Disconnected from {self.port}")

    def is_connected(self):
        """Check if the serial port is open."""
        return self.ser.is_open if self.ser else False
    
    def send(self, cmd: str):
        print(f"Sending command: {cmd.encode("ascii").strip()}")
        self.ser.write(cmd.encode("ascii"))


    def enable_output(self):
        self._toggle_output(1)

    def disable_output(self, ch: int = 1):
        self._toggle_output(0)

    def _toggle_output(self, enable: int):
        enable = 1 if enable else 0
        self.send(OUTPUT.format(enable=enable))

    def lock_panel(self):
        self._toggle_lock_panel(1)

    def unlock_panel(self):
        self._toggle_lock_panel(0)

    def _toggle_lock_panel(self, enable: int):
        enable = 1 if enable else 0
        self.send(LOCK_PANEL.format(enable=enable)) 


    def set_voltage(self, ch: int, value: float):
        self.send(SET_VOLTAGE.format(ch=ch, value=value))

    def set_current(self, ch: int, value: float):
        self.send(SET_CURRENT.format(ch=ch, value=value))

    def get_voltage_setting(self, ch: int) -> float:
        return self.query(GET_VOLTAGE_SETTING.format(ch=ch))

    def get_current_setting(self, ch: int) -> float:
        return self.query(GET_CURRENT_SETTING.format(ch=ch))
    
    def read_voltage(self, ch: int) -> float:
        return self.query(READ_VOLTAGE.format(ch=ch))

    def read_current(self, ch: int) -> float:
        return self.query(READ_CURRENT.format(ch=ch))
    


    # def get_measured_voltage(self, ch: int) -> float:
    #     return float(self.query(READ_VOUT.format(ch=ch)))

    # def get_measured_current(self, ch: int) -> float:
    #     return float(self.query(READ_IOUT.format(ch=ch)))

    # def identify(self) -> str:
    #     return self.query(IDN)

    def query(self, cmd: str) -> str:
        self.send(cmd)
        time.sleep(0.3)  # Wait for the response to be ready
        response = self.ser.readline()
        # response = self.ser.read_until(b'\r')
        print(f"Received response: {response}")
        return response.decode("ascii").strip()