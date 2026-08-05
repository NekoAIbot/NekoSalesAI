class WorkerRegistry:

    def __init__(self):
        self._workers = {}

    def register(self, name, handler):
        self._workers[name] = handler

    def execute(self, worker_name, payload):

        worker = self._workers.get(worker_name)

        if worker is None:
            print(f"[WORKER REGISTRY] No worker registered for '{worker_name}'")
            return False

        print(f"[WORKER REGISTRY] Executing {worker_name}")

        return worker(payload)


worker_registry = WorkerRegistry()
