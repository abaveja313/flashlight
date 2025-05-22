import os
from typing import Optional

from dagster import ConfigurableResource, InitResourceContext
from pydantic import PrivateAttr
from langchain_core.language_models import BaseChatModel


class LLMResource(ConfigurableResource):
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
            from langchain_openai import ChatOpenAI

            self._client = ChatOpenAI(
                api_key=self.api_key,
                model=self.model_name,
                temperature=self.temperature,
            )
        elif self.provider == "google":
            from langchain_google_genai import ChatGoogleGenerativeAI

            self._client = ChatGoogleGenerativeAI(
                google_api_key=self.api_key,
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
