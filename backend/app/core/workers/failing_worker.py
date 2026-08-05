class FailingWorker:

    def run(self, payload):
        raise RuntimeError("Intentional retry test")


failing_worker = FailingWorker()
