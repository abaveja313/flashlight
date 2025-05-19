import os
from typing import Optional

from dagster import ConfigurableResource, InitResourceContext
from pydantic import PrivateAttr
from langchain_core.language_models import BaseChatModel


class LLMResource(ConfigurableResource):
    """
    Represents a resource configuration for language model-based services.

    This class is designed to configure, initialize, and manage a language model
    service client. It abstracts setup and access to the underlying chat service
    client based on the specified provider. The supported providers include
    OpenAI and Google, configured via the `provider` attribute, along with other
    parameters such as API key, model name, and temperature.

    :ivar provider: The name of the service provider (e.g., "openai", "google").
    :type provider: str
    :ivar api_key: The API key used for authenticating with the provider.
    :type api_key: str
    :ivar model_name: The name of the model to use from the provider's offerings.
    :type model_name: str
    :ivar temperature: The temperature parameter for the language model, controlling
        randomness in output. Defaults to 0.7.
    :type temperature: float
    """
    provider: str
    api_key: str
    model_name: str
    temperature: float = 0.7

    # Internal, mutable chat client
    _client: Optional[BaseChatModel] = PrivateAttr(default=None)

    def setup_for_execution(self, context: InitResourceContext) -> None:
        """
        Initialize the chat client according to the configured provider.
        """
        if self.provider == "openai":
            os.environ["OPENAI_API_KEY"] = self.api_key
            from langchain_openai import ChatOpenAI

            self._client = ChatOpenAI(
                model=self.model_name,
                temperature=self.temperature,
            )
        elif self.provider == "google":
            os.environ["GOOGLE_API_KEY"] = self.api_key
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._client = ChatGoogleGenerativeAI(
                model=self.model_name,
                temperature=self.temperature,
            )
        else:
            raise ValueError(f"Unsupported provider: {self.provider}")

    @property
    def client(self) -> BaseChatModel:
        """
        Property accessor for the initialized chat client.
        Raises if accessed before setup.
        """
        if self._client is None:
            raise RuntimeError("LLMResource client accessed before initialization")
        return self._client