from app.ai.providers.mock_provider import MockAIProvider


class ProviderFactory:

    @staticmethod
    def create():

        return MockAIProvider()

