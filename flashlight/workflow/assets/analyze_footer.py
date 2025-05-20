from pathlib import Path
from typing import cast

import dagster as dg
from dagster import AssetIn, AssetOut, AssetExecutionContext, Output, MetadataValue

from flashlight.utils.file_utils import image_to_data_uri
from flashlight.utils.prompts import ContainsPrivacyIconOutput, CONTAINS_PRIVACY_ICON
from flashlight.workflow.resources import domain_partitions, LLMResource


@dg.multi_asset(
    required_resource_keys={"browser_manager", "llm"},
    partitions_def=domain_partitions,
    group_name="footer",
    ins={
        "footer_screenshot": AssetIn(
            dagster_type=Path,
            key="footer_screenshot",
            metadata={"ext": ".png"},
        ),
    },
    outs={
        "footer_has_privacy_icon": AssetOut(
            dagster_type=bool,
            metadata={"ext": ".png"},
            key="footer_privacy_icon",
            description="Whether the footer contains a link with the CCPA privacy choices icon"
        )
    }
)
async def analyze_footer_screenshot(context: AssetExecutionContext, footer_screenshot: Path):
    assert footer_screenshot.exists(), "Footer screenshot cannot be analyzed as it was not downloaded"
    try:
        llm = cast(LLMResource, context.resources.llm).client
        llm_with_parser = llm.with_structured_output(ContainsPrivacyIconOutput)
        chain = CONTAINS_PRIVACY_ICON | llm_with_parser

        encoded_image = image_to_data_uri(path=footer_screenshot, delete=True)

        result = cast(ContainsPrivacyIconOutput, await chain.ainvoke({
            "image_url": encoded_image
        }))

        yield Output(
            result.uses_icon,
            output_name="footer_has_privacy_icon",
            metadata={
                "has_icon": MetadataValue.bool(result.uses_icon),
                "explanation": MetadataValue.text(result.explanation),
            }
        )
    finally:
        footer_screenshot.unlink(missing_ok=True)