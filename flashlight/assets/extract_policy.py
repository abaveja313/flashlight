import pathlib
import tempfile
from pathlib import Path
from typing import cast, Tuple, Optional

import dagster as dg
from browser_use.controller.service import Controller
from dagster import (
    Field,
    String,
    Int,
    AssetExecutionContext,
    MetadataValue,
    Output,
    AssetOut,
    Failure,
    AssetIn,
)
from langchain_core.language_models import BaseChatModel
from managed_browser import BrowserManager, ManagedSession
from playwright.async_api import Page

from flashlight.resources import settings, LLMResource, domain_partitions, TextExtractor
from flashlight.utils.page_utils import screenshot_region, scroll_to_bottom
from flashlight.utils.prompts import ContainsCCPARightsOutput, EXTRACT_CCPA_RIGHTS, ExtractedPrivacyPolicyOutput, \
    EXTRACT_PRIVACY_POLICY_TEXT


async def remove_overlays(
        llm: BaseChatModel, session: ManagedSession, page: Page
) -> Tuple[Page, int]:
    adjust_viewport_agent = session.make_agent(
        llm=llm,
        task="Dismiss any dialogs, modals, banners or popups that are overalyed on page content.",
        controller=Controller(
            exclude_actions=[
                "search_google",
                "open_url",
                "save_pdf",
                "switch_tab",
                "open_tab",
                "close_tab",
                "extract_content",
                "scroll_to_text",
                "drag_drop",
                "scroll_down",
                "scroll_up",
                "send_key",
            ]
        ),
        start_page=page,
    )
    result, page = await adjust_viewport_agent.run(max_steps=10)
    # 4) Give page a moment, then return history length as before
    await page.wait_for_timeout(3000)
    return page, len(result.history)


async def navigate_to_privacy_policy(
        llm: BaseChatModel, session: ManagedSession, page: Page
):
    # Todo fails on some privacy cengters like airbnb
    navigate_to_policy = session.make_agent(
        llm=llm,
        start_page=page,
        task="Navigate to the page containing the privacy policy / notice. "
             "If there are multiple regions available, navigate to the US version."
             " When the page contains a comprehensive privacy policy document, rather than a link to such a document, "
             " switch to that tab (if necessary), and your job is complete",
        controller=Controller(
            exclude_actions=["search_google", "save_pdf", "drag_drop"]
        ),
    )
    policy_nav_result, page = await navigate_to_policy.run(max_steps=6)
    if not policy_nav_result.is_successful():
        raise Failure("Could not navigate to privacy policy")

    await page.wait_for_timeout(1000)
    return page


async def attempt_ccpa_extraction(
        llm: BaseChatModel, extractor: TextExtractor, text: str, logger
) -> Tuple[Optional[str], str]:
    logger.debug("Attempting CCPA Extraction from text: %s", text)
    llm_with_parser = llm.with_structured_output(ContainsCCPARightsOutput)
    chain = EXTRACT_CCPA_RIGHTS | llm_with_parser
    prepped = extractor.prep_llm_input(text)
    result = cast(ContainsCCPARightsOutput, await chain.ainvoke({"contents": prepped}))
    if result.contains_ccpa_rights:
        return (extractor.parse_region(text, start_line=result.start_line, end_line=result.end_line),
                result.explanation)
    return None, result.explanation


@dg.multi_asset(
    required_resource_keys={"browser_manager", "llm"},
    partitions_def=domain_partitions,
    outs={
        "remove_overlay_action_count": AssetOut(
            dagster_type=int,
            group_name="usability",
            io_manager_key="io_manager",
            description="Number of actions to remove overlays",
            metadata={"ext": ".pkl"},
        ),
        "privacy_policy_url": AssetOut(
            dagster_type=str,
            group_name="privacy_policy",
            io_manager_key="io_manager",
            description="Extracted privacy policy URL",
            metadata={"ext": ".pkl"},
        ),
        "footer_screenshot": AssetOut(
            dagster_type=Path,
            group_name="footer",
            io_manager_key="io_manager",
            description="Screenshot of the footer section",
            metadata={"ext": ".png"},
        ),
        "privacy_policy_html": AssetOut(
            dagster_type=str,
            group_name="privacy_policy",
            io_manager_key="io_manager",
            description="Extracted privacy policy HTML",
            metadata={"ext": ".pkl"},
        ),
        "privacy_policy_trace": AssetOut(
            dagster_type=Path,
            group_name="traces",
            io_manager_key="io_manager",
            description="Playwright trace archive for privacy policy navigation",
            metadata={"ext": ".zip"},
        ),
    },
    config_schema={
        "url": Field(String, is_required=False, description="Starting website URL"),
        "load_timeout_ms": Field(
            Int, default_value=60_000, description="Page load timeout in milliseconds"
        ),
        "operation_delay_ms": Field(
            Int, default_value=2_000, description="Page operation delay in milliseconds"
        ),
        "scroll_delay_ms": Field(
            Int,
            default_value=1000,
            description="Page scroll delay " "in milliseconds for infinite scroll",
        ),
    },
)
async def find_privacy_policy(context: AssetExecutionContext):
    # Extract resources and config
    bm = cast(BrowserManager, context.resources.browser_manager)
    llm = cast(LLMResource, context.resources.llm).client

    url = context.op_config.get(
        "url", f"https://{context.partition_key}"
    )  # easier from ui
    context.log.info(f"Using URL {url!r}")

    load_timeout_ms = context.op_config["load_timeout_ms"]
    operation_delay_ms = context.op_config["operation_delay_ms"]

    context.log.info(f"Finding privacy policy from: {url}")

    tracing_out = tempfile.NamedTemporaryFile(prefix="trace_", mode="w+b", delete=False)

    async with bm.managed_context(
            use_tracing=True, tracing_output_path=tracing_out.name
    ) as session:
        session = cast(ManagedSession, session)
        page = await session.browser_context.new_page()

        # Navigate to the initial URL
        context.log.info(f"Navigating to website: {url}")

        # Usually works better to wait until 'domcontentloaded' - 'networkidle' hangs a lot more IMO
        await page.goto(url, wait_until="domcontentloaded", timeout=load_timeout_ms)
        await page.wait_for_timeout(operation_delay_ms)

        # TODO @amrit - being casted to a bool IDK why
        page, remove_ops = await remove_overlays(
            llm, session, page
        )
        context.log.info(f"Removed overlays in {remove_ops} operations")

        yield Output(remove_ops, output_name="remove_overlay_action_count")
        await scroll_to_bottom(
            page=page,
            pause_time_ms=settings.get("pause_time_ms", 200),
            max_rounds=settings.get("max_scroll_rounds", 50),
        )
        await page.wait_for_timeout(operation_delay_ms)

        # Take a screenshot of the footer for navigation
        footer_screenshot = await screenshot_region(
            page=page,
            number_dividers=4,
            direction="vertical",
            indexes=(1, 2, 3),  # Bottom 3/4
        )
        context.log.info(f"Captured footer screenshot: {footer_screenshot}")
        yield Output(footer_screenshot, output_name="footer_screenshot")
        page = await navigate_to_privacy_policy(llm=llm, session=session, page=page)

        privacy_url = page.url
        context.log.info(f"Found privacy policy at: {privacy_url}")

        yield Output(
            privacy_url,
            output_name="privacy_policy_url",
            metadata={"url": MetadataValue.url(privacy_url)},
        )

        # Page contents
        contents = await page.content()
        yield Output(contents, output_name="privacy_policy_html")

    yield Output(pathlib.Path(tracing_out.name), output_name="privacy_policy_trace")


@dg.multi_asset(
    required_resource_keys={"mini_llm", "text_extractor"},
    partitions_def=domain_partitions,
    ins={
        "privacy_policy_html": AssetIn(
            dagster_type=str,
            key="privacy_policy_html",
            metadata={"ext": ".pkl"},
        ),
    },
    outs={
        "privacy_policy_text": AssetOut(
            dagster_type=str,
            group_name="privacy_policy",
            io_manager_key="io_manager",
            description="Privacy policy text",
            metadata={"ext": ".pkl"},
        ),
    },
)
async def extract_privacy_policy(context: AssetExecutionContext, privacy_policy_html: str):
    mini_llm = cast(LLMResource, context.resources.mini_llm).client
    extractor = cast(TextExtractor, context.resources.text_extractor)

    parsed = extractor.from_html(privacy_policy_html)
    prepped = extractor.prep_llm_input(parsed)
    mini_llm_with_parser = mini_llm.with_structured_output(ExtractedPrivacyPolicyOutput)
    chain = EXTRACT_PRIVACY_POLICY_TEXT | mini_llm_with_parser
    result = cast(ExtractedPrivacyPolicyOutput, await chain.ainvoke({"contents": prepped}))
    context.log.info(f"Extracted privacy policy text lines {result.start_line!r} ... {result.end_line!r}")
    contents = extractor.parse_region(parsed, start_line=result.start_line, end_line=result.end_line)

    yield Output(
        contents,
        output_name="privacy_policy_text",
        metadata={
            "preview": MetadataValue.md(contents[:settings.preview_length]),
            "explanation": MetadataValue.md(result.explanation)
        },
    )


@dg.multi_asset(
    required_resource_keys={"browser_manager", "llm", "mini_llm", "text_extractor"},
    partitions_def=domain_partitions,
    ins={
        "privacy_policy_text": AssetIn(
            dagster_type=str,
            key="privacy_policy_text",
            metadata={"ext": ".pkl"},
        ),
        "privacy_policy_url": AssetIn(
            dagster_type=str,
            key="privacy_policy_url",
            metadata={"ext": ".pkl"},
        ),
    },
    outs={
        "ccpa_rights_url": AssetOut(
            dagster_type=str,
            group_name="ccpa_policy",
            io_manager_key="io_manager",
            description="URL to the CCPA rights policy.",
            metadata={"ext": ".pkl"},
        ),
        "ccpa_rights_text": AssetOut(
            dagster_type=str,
            group_name="ccpa_policy",
            io_manager_key="io_manager",
            description="Text of the CCPA rights policy.",
            metadata={"ext": ".pkl"},
        ),
        "ccpa_trace": AssetOut(
            dagster_type=Path,
            group_name="traces",
            io_manager_key="io_manager",
            description="Trace data of CCPA policy location process.",
            metadata={"ext": ".zip"},
            is_required=False,
        ),
    },
)
async def extract_ccpa_policy(
        context: AssetExecutionContext, privacy_policy_text: str, privacy_policy_url: str
):
    llm = cast(LLMResource, context.resources.llm).client
    mini_llm = cast(LLMResource, context.resources.mini_llm).client
    extractor = cast(TextExtractor, context.resources.text_extractor)
    extraction_result, _ = await attempt_ccpa_extraction(llm=mini_llm, text=privacy_policy_text, logger=context.log,
                                                         extractor=extractor)

    if extraction_result:
        context.log.info(f"CCPA rights found at {privacy_policy_url}")
        yield Output(
            privacy_policy_url,
            output_name="ccpa_rights_url",
            metadata={"url": MetadataValue.url(privacy_policy_url)},
        )
        yield Output(
            extraction_result,
            output_name="ccpa_rights_text",
            metadata={
                "preview": MetadataValue.md(extraction_result[:settings.preview_length]),
                "explanation": MetadataValue.text(extraction_result),
            },
        )
        return

        # 3) Otherwise spin up a browser agent to locate the rights page
    context.log.info("Invoking agent to locate downstream CCPA rights page")
    trace_file = tempfile.NamedTemporaryFile(
        prefix="ccpa_trace_", suffix=".zip", delete=False
    )
    bm = cast(BrowserManager, context.resources.browser_manager)

    async with bm.managed_context(
            use_tracing=True, tracing_output_path=trace_file.name
    ) as session:
        session = cast(ManagedSession, session)
        page = await session.browser_context.new_page()
        await page.goto(privacy_policy_url, wait_until="domcontentloaded")

        agent = session.make_agent(
            start_page=page,
            llm=llm,
            task="The following privacy policy does NOT contain any privacy rights specific to California residents. "
                 "Navigate to the page that lists such rights listed in legal language, then you are DONE. If you CANNOT"
                 "find that information, you FAILED.",
        )
        agent_result, page = await agent.run(max_steps=10)

        if not agent_result.is_successful():
            raise Failure("Agent failed to locate CCPA rights page")

        context.log.info(f"Agent navigated to CCPA rights page: {page.url}")
        page_html = await page.content()
        ccpa_text = extractor.from_html(page_html)

        # 4) Re-extract from the discovered page
        result, explanation = await attempt_ccpa_extraction(llm=mini_llm, text=ccpa_text, logger=context.log,
                                                            extractor=extractor)
        if not result:
            raise Failure("Failed to extract CCPA rights from the located page")

        yield Output(
            page.url,
            output_name="ccpa_rights_url",
            metadata={"url": MetadataValue.url(page.url)},
        )
        yield Output(
            result,
            output_name="ccpa_rights_text",
            metadata={
                "preview": MetadataValue.md(result[:settings.preview_length]),
                "explanation": MetadataValue.text(explanation),
            },
        )

    yield Output(
        Path(trace_file.name),
        output_name="ccpa_trace",
    )
