import textwrap
from typing import List, Optional

from pydantic import BaseModel
from langchain.prompts.chat import ChatPromptTemplate


class ContainsPrivacyIconOutput(BaseModel):
    """Output schema for navigation instructions."""
    uses_icon: bool
    explanation: str


# Prompt for screenshot-based navigation
CONTAINS_PRIVACY_ICON = ChatPromptTemplate.from_messages([
    {
        "role": "system",
        "content": textwrap.dedent(
            "You are a UI compliance expert. You should detect whether provided website footers display a blue and "
            "white ‘Privacy Choices’ icon shaped like a pill, featuring a checkmark and an ‘X’?"
        ),
    },
    {
        "role": "user",
        "content": [
            {"type": "image_url", "image_url": "{image_url}"},
        ]
    }
])

