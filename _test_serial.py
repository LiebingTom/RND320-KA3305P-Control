from src.RND320 import RND320

if __name__ == "__main__":
    psu = RND320(port='COM5') 
    psu.connect()

    if psu.is_connected():
        # Ready to send commands
        pass

    psu.disconnect()