import pprint
import re
from typing import Literal

from dagster import ConfigurableResource

from flashlight.resources import LLMResource


class TextExtractor(ConfigurableResource):
    strategy: Literal['main_only', 'unformatted', 'markdown']

    @staticmethod
    def prep_llm_input(text: str) -> str:
        lines = text.splitlines()
        contents = pprint.pformat([
            (i, lines[i]) for i in range(len(lines))
        ])
        return pprint.pformat(contents)

    @staticmethod
    def parse_region(text: str, start_line: int, end_line: int):
        lines = text.splitlines()
        return '\n'.join(lines[start_line: end_line + 1])

    def from_html(self, html: str, *args, **kwargs) -> str:
        match self.strategy.lower():
            case 'main_only':
                from trafilatura import extract
                return extract(html, *args, favor_recall=True, **kwargs)
            case 'unformatted':
                from trafilatura import html2txt
                return html2txt(html, *args, **kwargs)
            case 'markdown':
                from markdownify import markdownify as md
                return md(html, **kwargs)

            case _:
                raise ValueError(f"Unsupported provider: {self.strategy}")
