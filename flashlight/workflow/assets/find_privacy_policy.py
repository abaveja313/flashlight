import shutil
from pathlib import Path
import os
import tempfile
from typing import cast, Optional

import dagster as dg
from dagster import (
    Field,
    String,
    Int,
    AssetExecutionContext,
    AssetMaterialization,
    Failure,
    MetadataValue,
    Output,
    AssetOut,
)
from playwright.sync_api import TimeoutError
from langchain.chains.llm import LLMChain
from langchain_core.output_parsers import PydanticOutputParser

from flashlight.prompts import FindNextClickOutput, FIND_NEXT_CLICK_CHAT
from flashlight.utils.file_utils import image_to_data_uri
from flashlight.utils.page_utils import (
    scroll_to_bottom,
    screenshot_region,
    dismiss_modals,
    accept_cookies,
)
from flashlight.workflow.resources import BrowserManager, settings, LLMResource, domain_partitions


def click_elements_by_text(page, text: str, logger) -> bool:
    locator = page.locator(f'text="{text}"')
    count = locator.count()
    if count == 0:
        return False
    for i in range(count):
        try:
            locator.nth(i).click(timeout=5000)
        except TimeoutError:
            logger.warning(f"Regular click failed for '{text}', forcing it")
            locator.nth(i).click(force=True)
    return True


def iterate_clicks(
        page,
        chain: LLMChain,
        goal: str,
        initial_image_url: Path,
        max_steps: int,
        logger,
) -> FindNextClickOutput:
    image_url = initial_image_url
    result: Optional[FindNextClickOutput] = None
    logger.info(f"Starting click iteration (up to {max_steps} steps) toward '{goal}'.")
    for step in range(max_steps):
        logger.debug(f"Step {step + 1}, prompting LLM with image {image_url}")
        result = chain.predict_and_parse(
            goal=goal,
            image_url=image_to_data_uri(image_url),
        )
        logger.info(f"Result: target={result.target!r}, complete={result.complete}, reason={result.explanation!r}")
        if result.complete or not result.target:
            break

        if not click_elements_by_text(page, result.target, logger):
            logger.warning(f"No element matched '{result.target}', aborting.")
            break

        page.wait_for_timeout(settings.get("navigation_delay_ms", 2_000))

        image_url = screenshot_region(
            page=page,
            number_dividers=1,
            direction="vertical",
            indexes=(0,),
        )
        logger.debug(f"Captured next full-page screenshot: {image_url}")

    return result


@dg.multi_asset(
    required_resource_keys={"browser_context", "llm"},
    partitions_def=domain_partitions,
    outs={
        "footer_screenshot": AssetOut(
            dagster_type=Path,
            io_manager_key="io_manager",
            description="Screenshot of bottom half of the website’s footer",
        ),
        "privacy_policy_url": AssetOut(
            dagster_type=str,
            io_manager_key="io_manager",
            description="Extracted privacy policy link",
        ),
        "playwright_trace": AssetOut(
            dagster_type=Path,
            io_manager_key="io_manager",
            description="Playwright trace archive (zip)",
        ),
    },
    config_schema={
        "url": Field(String, is_required=True),
        "load_timeout_ms": Field(Int, default_value=60_000),
    },
)
def locate_privacy_policy(context: AssetExecutionContext):
    bm = cast(BrowserManager, context.resources.browser_context)
    llm = cast(LLMResource, context.resources.llm)

    context.log.info(f"Navigating to {context.op_config['url']}")
    with bm.managed_context() as ctx:
        ctx.tracing.start(screenshots=True, snapshots=True, title="Locate Privacy Policy")
        page = ctx.new_page()
        page.goto(
            context.op_config["url"],
            wait_until="domcontentloaded",
            timeout=context.op_config["load_timeout_ms"],
        )

        dismiss_modals(page)
        if accept_cookies(page):
            page.wait_for_timeout(500)

        scroll_to_bottom(
            page=page,
            max_loops=settings.get("max_scroll_steps", 100),
            pause_time=settings.get("scroll_delay_secs", 0.5),
        )
        page.wait_for_timeout(settings.get("footer_load_delay_ms", 1_000))

        # 1) Capture the initial footer screenshot
        footer_screenshot = screenshot_region(
            page=page,
            number_dividers=2,
            direction="vertical",
            indexes=(1,),
        )
        context.log.info(f"Captured footer screenshot: {footer_screenshot}")

        # 2) Run LLM click loop
        parser = PydanticOutputParser(pydantic_object=FindNextClickOutput)
        chain = LLMChain(llm=llm.client, prompt=FIND_NEXT_CLICK_CHAT, output_parser=parser)
        result = iterate_clicks(
            page=page,
            chain=chain,
            goal=(
                "Navigate to and open the site’s privacy policy statement/notice—"
                "if multiple regional versions are listed, choose the United States or California variant—"
                "and only click links whose visible text contains “privacy.” Do not go to specific sections of the policy."
            ),
            initial_image_url=footer_screenshot,
            max_steps=settings.get("max_find_steps", 5),
            logger=context.log,
        )
        if not result.complete:
            raise Failure("Failed to locate the privacy policy link")

        # 3) Copy & emit only the initial screenshot
        upload_footer = footer_screenshot.parent / f"upload-{footer_screenshot.name}"
        shutil.copy(footer_screenshot, upload_footer)
        context.log.info(f"Copied footer screenshot for upload: {upload_footer}")
        yield AssetMaterialization.file(
            path=footer_screenshot,
            asset_key="footer_screenshot",
            description="Screenshot of bottom half of the website’s footer",
        )
        yield Output(upload_footer, output_name="footer_screenshot")

        # 4) Emit the extracted URL
        context.log.info(f"Privacy policy link: {page.url}")
        yield AssetMaterialization(
            asset_key="privacy_policy_url",
            description="Extracted privacy policy link",
        )
        yield Output(page.url, output_name="privacy_policy_url", metadata={
            "url": MetadataValue.url(page.url)
        })

        # 5) Stop tracing and emit the trace archive using mkstemp
        fd, tmp_path_str = tempfile.mkstemp(suffix=".zip")
        os.close(fd)
        trace_path = Path(tmp_path_str)

        ctx.tracing.stop(path=str(trace_path))
        context.log.info(f"Playwright trace saved to {trace_path}")
        yield AssetMaterialization.file(
            path=trace_path,
            asset_key="playwright_trace",
            description="Playwright trace archive (zip)",
        )
        yield Output(trace_path, output_name="playwright_trace")
