import os
import tempfile
from pathlib import Path
from typing import Sequence

from playwright.async_api import Page, FloatRect, BrowserContext


async def get_or_create_page(context: BrowserContext) -> Page:
    if len(context.pages) > 0 and context.pages[0].url == 'about:blank':
        return context.pages[0]  # we can use this
    return await context.new_page()


async def scroll_to_bottom(page: Page, pause_time: float = 1.0, max_loops: int = 50):
    last_height = page.evaluate("() => document.body.scrollHeight")
    for _ in range(max_loops):
        await page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        await page.wait_for_timeout(pause_time)
        new_height = await page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


async def screenshot_region(
        *,
        page: Page,
        number_dividers: int,
        direction: str,
        indexes: Sequence[int],
) -> Path:
    # Fix: https://github.com/microsoft/playwright/issues/28995
    os.environ['PW_TEST_SCREENSHOT_NO_FONTS_READY'] = '1'

    # --- Validation ---
    if number_dividers < 1:
        raise ValueError(f"number_dividers must be ≥1 (got {number_dividers})")

    if direction not in ("vertical", "horizontal"):
        raise ValueError(f"direction must be 'vertical' or 'horizontal' (got {direction!r})")

    if not indexes:
        raise ValueError("indexes must be a non-empty sequence of ints")
    sorted_ix = sorted(indexes)

    if any(i < 0 or i >= number_dividers for i in sorted_ix):
        raise ValueError(f"All indexes must be in [0, {number_dividers - 1}] (got {indexes})")

    if sorted_ix != list(range(sorted_ix[0], sorted_ix[-1] + 1)):
        raise ValueError(f"Indexes must form a contiguous range (got {indexes})")

    tmp_file = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    tmp_path = tmp_file.name
    tmp_file.close()

    # Get viewport size
    viewport = page.viewport_size or await page.evaluate(
        "() => ({ width: window.innerWidth, height: window.innerHeight })"
    )
    vp_w, vp_h = viewport["width"], viewport["height"]

    # Compute clip rectangle
    if direction == "vertical":
        slice_h = vp_h / number_dividers
        clip = FloatRect(
            x=0.0,
            y=slice_h * sorted_ix[0],
            width=vp_w,
            height=slice_h * len(sorted_ix),
        )
    else:
        slice_w = vp_w / number_dividers
        clip = FloatRect(
            x=slice_w * sorted_ix[0],
            y=0.0,
            width=slice_w * len(sorted_ix),
            height=vp_h,
        )

    # --- Screenshot and return ---
    await page.screenshot(path=tmp_path, clip=clip)
    return Path(tmp_path)
