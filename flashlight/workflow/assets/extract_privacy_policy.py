import pathlib
import tempfile
import uuid
from pathlib import Path
from typing import cast, List

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
)
from langchain_core.language_models import BaseChatModel
from managed_browser import BrowserManager, ManagedSession
from playwright.async_api import Page

from flashlight.utils.page_utils import screenshot_region, scroll_to_bottom
from flashlight.workflow.resources import settings, LLMResource, domain_partitions


async def remove_overlays(
    llm: BaseChatModel,
    session: ManagedSession,
    page: Page
) -> int:
    adjust_viewport_agent = session.make_agent(
        llm=llm,
        task="Dismiss any dialogs, modals, banners or popups that are covering page content. No need to scroll",
        controller=Controller(
            exclude_actions=[
                'search_google', 'open_url', 'save_pdf', 'switch_tab',
                'open_tab', 'close_tab', 'extract_content', 'scroll_to_text',
                'drag_drop', 'scroll_down', 'scroll_up', 'send_key'
            ]
        ),
        start_page=page
    )
    result = await adjust_viewport_agent.run(max_steps=10)
    # 4) Give page a moment, then return history length as before
    await page.wait_for_timeout(3000)
    return len(result.history)

async def navigate_to_privacy_policy(llm: BaseChatModel, session: ManagedSession, page: Page):
    navigate_to_policy = session.make_agent(
        llm=llm,
        start_page=page,
        task="Navigate to the page containing the privacy policy / notice. "
             "If there are multiple regions available, navigate to the US version."
             " When the page contains legal text resembling a privacy policy, the task is complete.",
        controller=Controller(exclude_actions=['search_google', 'save_pdf', 'drag_drop']),
    )
    policy_nav_result = await navigate_to_policy.run(max_steps=30)
    if not policy_nav_result.is_successful():
        raise Failure("Could not navigate to privacy policy")

    await page.wait_for_timeout(1000)


@dg.multi_asset(
    required_resource_keys={"browser_manager", "llm"},
    partitions_def=domain_partitions,
    outs={
        "remove_overlay_action_count": AssetOut(
            dagster_type=int,
            group_name="usability",
            io_manager_key="io_manager",
            description="Number of actions to remove overlays",
            metadata={"ext": ".pkl"}
        ),
        "privacy_policy_url": AssetOut(
            dagster_type=str,
            group_name="privacy_policy",
            io_manager_key="io_manager",
            description="Extracted privacy policy URL",
            metadata={"ext": ".pkl"}
        ),
        "footer_screenshot": AssetOut(
            dagster_type=Path,
            group_name="footer",
            io_manager_key="io_manager",
            description="Screenshot of the footer section",
            metadata={"ext": ".png"}
        ),
        "privacy_policy_text": AssetOut(
            dagster_type=str,
            group_name="privacy_policy",
            io_manager_key="io_manager",
            description="Privacy policy text",
            metadata={"ext": ".pkl"}
        ),
        "privacy_policy_trace": AssetOut(
            dagster_type=Path,
            group_name="traces",
            io_manager_key="io_manager",
            description="Playwright trace archive for privacy policy navigation",
            metadata={"ext": ".zip"}
        ),
    },
    config_schema={
        "url": Field(String, is_required=True, description="Starting website URL"),
        "load_timeout_ms": Field(Int, default_value=60_000, description="Page load timeout in milliseconds"),
        "operation_delay_ms": Field(Int, default_value=2_000, description="Page operation delay in milliseconds"),
    },
)
async def find_privacy_policy(context: AssetExecutionContext):
    # Extract resources and config
    bm = cast(BrowserManager, context.resources.browser_manager)
    llm = cast(LLMResource, context.resources.llm).client

    url = context.op_config["url"]
    load_timeout_ms = context.op_config["load_timeout_ms"]
    operation_delay_ms = context.op_config["operation_delay_ms"]

    context.log.info(f"Finding privacy policy from: {url}")

    tracing_out = tempfile.NamedTemporaryFile(prefix="trace_", mode="w+b", delete=False)

    async with bm.managed_context(use_tracing=True, tracing_output_path=tracing_out.name) as session:
        session = cast(ManagedSession, session)
        page = await session.browser_context.new_page()

        # Navigate to the initial URL
        context.log.info(f"Navigating to website: {url}")

        # Usually works better to wait until 'domcontentloaded' - 'networkidle' hangs a lot more IMO
        await page.goto(url, wait_until="domcontentloaded", timeout=load_timeout_ms)

        await page.wait_for_timeout(operation_delay_ms)
        await scroll_to_bottom(
            page=page,
            max_loops=settings.get("max_scroll_steps", 100),
            pause_time=settings.get("scroll_delay_secs", 0.5),
        )
        remove_ops = await remove_overlays(llm, session, page) # TODO @amrit - being casted to a bool IDK why
        context.log.info(f"Removed overlays in {remove_ops} operations")
        yield Output(remove_ops, output_name="remove_overlay_action_count")

        # Take a screenshot of the footer for navigation
        footer_screenshot = await screenshot_region(
            page=page,
            number_dividers=3,
            direction="vertical",
            indexes=(1, 2),  # Bottom 2/3
        )
        context.log.info(f"Captured footer screenshot: {footer_screenshot}")
        yield Output(footer_screenshot, output_name="footer_screenshot")

        # Some websites use a "privacy center" or something like which requires some non-deterministic steps.
        navigate_to_policy = session.make_agent(
            start_page=page,
            llm=llm,
            task="You are already at the footer of the webpage. "
                 "Navigate to the page containing the privacy policy / notice. "
                 "If there are multiple regions available, navigate to the US version."
                 " When the page contains legal text resembling a privacy policy, the task is complete.",
            controller=Controller(exclude_actions=['search_google', 'save_pdf', 'drag_drop']),
        )
        policy_nav_result = await navigate_to_policy.run(max_steps=5)

        if not policy_nav_result.is_successful():
            raise Failure("Could not navigate to privacy policy")

        # Record the privacy policy URL
        privacy_url = page.url
        context.log.info(f"Found privacy policy at: {privacy_url}")

        yield Output(privacy_url, output_name="privacy_policy_url", metadata={"url": MetadataValue.url(privacy_url)})

    yield Output(pathlib.Path(tracing_out.name), output_name="privacy_policy_trace")

