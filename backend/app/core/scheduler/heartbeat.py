import threading
import time

from app.core.runtime import runtime
from app.core.scanners import scanner


class AIHeartbeat:

    def __init__(self):
        self.running = False

    def start(self):

        if self.running:
            return

        self.running = True

        thread = threading.Thread(
            target=self.loop,
            daemon=True,
        )

        thread.start()

        print("AI Heartbeat Started")

    def loop(self):

        counter = 0

        while self.running:

            #
            # Drain every queued worker before sleeping.
            #
            while runtime.process_next():
                pass

            counter += 1

            if counter >= 5:
                scanner.run()
                counter = 0

            time.sleep(1)


heartbeat = AIHeartbeat()
