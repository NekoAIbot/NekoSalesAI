from app.ai.providers.base_provider import BaseAIProvider


class MockAIProvider(BaseAIProvider):

    def generate(
        self,
        system_prompt,
        user_prompt,
    ):

        return (
            "Hello! "
            "This is a placeholder AI response while the real "
            "provider is being connected."
        )

