class RetryManager:

    DEFAULT_MAX_RETRIES = 3

    def should_retry(self, execution):

        retry_count = getattr(execution, "retry_count", 0)
        max_retries = getattr(
            execution,
            "max_retries",
            self.DEFAULT_MAX_RETRIES,
        )

        return retry_count < max_retries

    def increment_retry(self, execution):

        current = getattr(execution, "retry_count", 0)
        execution.retry_count = current + 1

        return execution.retry_count

    def next_status(self, execution):

        if self.should_retry(execution):
            return "RETRYING"

        return "FAILED"


retry_manager = RetryManager()
