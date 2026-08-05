import time
from threading import Thread


class AutonomousScheduler:

    def __init__(self):
        self.running = False

    def start(self):

        if self.running:
            return

        self.running = True

        Thread(
            target=self.loop,
            daemon=True,
        ).start()

    def stop(self):
        self.running = False

    def loop(self):

        while self.running:

            print()
            print("========== AI HEARTBEAT ==========")
            print("Scanning for work...")
            print("==================================")

            time.sleep(5)

