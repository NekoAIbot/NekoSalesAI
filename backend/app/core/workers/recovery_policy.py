class RecoveryPolicy:


    def analyze(self, error_message):

        error = error_message.lower()


        if "timeout" in error:
            return {
                "strategy": "RETRY",
                "reason": "Temporary timeout detected",
                "delay_seconds": 30
            }


        if "rate" in error or "limit" in error:
            return {
                "strategy": "BACKOFF",
                "reason": "API rate limit detected",
                "delay_seconds": 120
            }


        if "payload" in error or "missing" in error:
            return {
                "strategy": "FIX_PAYLOAD",
                "reason": "Invalid input detected"
            }


        return {
            "strategy": "QUARANTINE",
            "reason": "Unknown failure requires investigation"
        }



recovery_policy = RecoveryPolicy()
