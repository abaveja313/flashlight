import textwrap
from typing import List, Optional

from pydantic import BaseModel
from langchain.prompts.chat import ChatPromptTemplate


class ContainsPrivacyIconOutput(BaseModel):
    """Output schema for navigation instructions."""

    uses_icon: bool
    explanation: str


class ContainsCCPARightsOutput(BaseModel):
    """Output schema for CCPA rights output"""

    contains_ccpa_rights: bool
    start_line: int
    end_line: int
    explanation: str


class ExtractedPrivacyPolicyOutput(BaseModel):
    """
    Output schema for extracted privacy policy.
    """
    start_line: int
    end_line: int
    explanation: str


# Prompt for screenshot-based navigation
CONTAINS_PRIVACY_ICON = ChatPromptTemplate.from_messages(
    [
        {
            "role": "system",
            "content": (
                "You are a UI compliance expert. You should detect whether provided website footers display a blue and "
                "white ‘Privacy Choices’ icon shaped like a pill, featuring a checkmark and an ‘X’?"
            ),
        },
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": "{image_url}"},
            ],
        },
    ]
)

EXTRACT_PRIVACY_POLICY_TEXT = ChatPromptTemplate.from_messages(
    [
        {
            "role": "system",
            "content": textwrap.dedent("""
        You are a data extraction assistant. You will be provided with all the text extracted from the privacy policy
        page of a website. Provide the starting line and ending line of the privacy policy text.
        
        Data will be provided in pairs: [(line_no, content)...]
        """),
        },
        {"role": "user", "content": "{contents}"},
    ]
)

EXTRACT_CCPA_RIGHTS = ChatPromptTemplate.from_messages(
    [
        {
            "role": "system",
            "content": textwrap.dedent(
                """
            You are a privacy expert. Detect whether the provided website text contains specific 
            information for California residents. If it seems like the rights are on another page,
            the detection yields no results. If it contains relevant information, provide the start and end lines.
            
            Data will be provided in pairs: [(line_no, content)...]
            """
            ),
        },
        {"role": "user", "content": "{contents}"},
    ]
)
