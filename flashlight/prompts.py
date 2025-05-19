import textwrap
from pydantic import BaseModel
from langchain.prompts.chat import ChatPromptTemplate


class FindNextClickOutput(BaseModel):
    target: str | None
    explanation: str | None
    complete: bool


# Construct a ChatPromptTemplate using structured image blocks
FIND_NEXT_CLICK_CHAT = ChatPromptTemplate.from_messages(
    [
        {
            "role": "system",
            "content": textwrap.dedent("""
                       You are a navigation expert and your _only_ information is the provided screenshot.
                       Your goal is to help a human navigate, _via clicks on on‐screen text_, to the target page.

                       - **Always** base your instructions strictly on what you can _see_ in the screenshot.  
                       - If you _recognize_ in the screenshot that the user is already on the target page, set `"complete": true` and both `"target"` and `"explanation"` to `null`.  
                       - Otherwise, identify the **exact** text on the page the user needs to click next, and explain why you chose it.

                       **Output JSON schema**:
                       ```
                       {{
                         "target": "<exact on-screen text to click>", 
                         "explanation": "<why that text?>", 
                         "complete": false
                       }}
                       ```
                       or, when done:
                       ```
                       {{
                         "target": null,
                         "explanation": null,
                         "complete": true
                       }}
                       ```
                   """),
        },
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "The user's goal is \"{goal}\". "},
                {"type": "image_url", "image_url": "{image_url}"},

            ]
        }
    ]
)
