SET_VOLTAGE = "VSET{ch}:{value:.2f}\r"
SET_CURRENT = "ISET{ch}:{value:.3f}\r"
OUTPUT      = "OUT{enable}\r"
LOCK_PANEL = "LOCK{enable}\r"

GET_VOLTAGE_SETTING = "VSET{ch}?\r"
GET_CURRENT_SETTING = "ISET{ch}?\r"
READ_VOLTAGE = "VOUT{ch}?\r"
READ_CURRENT = "IOUT{ch}?\r"

IDN         = "*DIN?\r"
# IDN         = "*IDN?\r"