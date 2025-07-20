import serial

class RND320:
    def __init__(self, port: str = 'COM1'):
        self.port = port
        self.baudrate = 9600
        self.bytesize = serial.EIGHTBITS
        self.parity = serial.PARITY_NONE
        self.stopbits = serial.STOPBITS_ONE
        self.timeout = 1  # in seconds
        self.ser = None

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
                dsrdtr=False
            )
            if self.ser.is_open:
                print(f"Connected to {self.port}")
        except serial.SerialException as e:
            print(f"Failed to connect to {self.port}: {e}")

    def disconnect(self):
        """Close the serial connection."""
        if self.ser and self.ser.is_open:
            self.ser.close()
            print(f"Disconnected from {self.port}")

    def is_connected(self):
        """Check if the serial port is open."""
        return self.ser.is_open if self.ser else False
