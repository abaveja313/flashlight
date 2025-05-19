import os
import re
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Sequence

from playwright.sync_api import FloatRect
from playwright.sync_api import Page, TimeoutError


def accept_cookies(page: Page, timeout: float = 1_000) -> bool:
    """
    Click a cookie‐consent button via fuzzy match, then
    disable pointer‐events on any remaining overlays so they
    can’t block future clicks.
    """
    # ---- 1) Fuzzy‐click any cookie buttons ----
    cookie_texts = [
        "Accept", "Accept Cookies", "I Accept", "Agree", "I Agree",
        "Got it", "OK", "Yes", "Allow", "Accept All", "Dismiss"
    ]
    # case‐insensitive partial match
    patterns = [re.compile(re.escape(text), re.IGNORECASE) for text in cookie_texts]
    clicked = False

    for pat in patterns:
        try:
            btn = page.get_by_role("button", name=pat, exact=False).first
            btn.click(timeout=timeout)
            clicked = True
            break
        except TimeoutError:
            continue
        except Exception:
            continue

    if not clicked:
        return False

    # ---- 2) Disable OneTrust overlays and big fixed containers ----
    page.evaluate(textwrap.dedent("""
    () => {
      const vw = window.innerWidth, vh = window.innerHeight;

      // A) Hide known OneTrust elements by ID or class
      document
        .querySelectorAll('[id^="onetrust"], .ot-sdk-container, .ot-banner, .ot-widget-container')
        .forEach(el => {
          el.style.display = 'none';
          el.style.pointerEvents = 'none';
        });

      // B) Generic “big fixed/sticky/absolute” overlay blocker
      document.querySelectorAll('*').forEach(el => {
        const cs = window.getComputedStyle(el);
        const z = parseInt(cs.zIndex) || 0;
        // only consider high‐z‐index positioned elements
        if ((cs.position === 'fixed' || cs.position === 'sticky' || cs.position === 'absolute')
            && z > 0) {
          const r = el.getBoundingClientRect();
          // if it covers ≥80% of viewport, disable its pointer events
          if (r.width >= vw * 0.8 && r.height >= vh * 0.8) {
            el.style.pointerEvents = 'none';
          }
        }
      });
    }
    """))

    return True


def dismiss_modals(page: Page) -> None:
    """
    Click any modal “close” buttons or icons (×), then remove
    any remaining modal containers, backdrops, scroll-locks, OneTrust overlays, etc.
    Covers Bootstrap, ARIA dialogs, <dialog> elements, and OneTrust consent widgets.
    """
    page.evaluate(textwrap.dedent("""
        () => {
            // 1) Click all obvious “close” buttons
            const closeSelectors = [
                '.btn-close',             // Bootstrap 5
                '[data-dismiss="modal"]', // Bootstrap 4
                '[data-bs-dismiss="modal"]',
                '[aria-label="Close"]'    // ARIA dialog close buttons
            ];
            closeSelectors.forEach(sel =>
                document.querySelectorAll(sel).forEach(el => {
                    try { el.click(); } catch {}
                })
            );
            // Buttons that literally show an “×” or “✕”
            document.querySelectorAll('button, [role="button"]').forEach(btn => {
                const t = btn.innerText?.trim();
                if (t === '×' || t === '✕') {
                    try { btn.click(); } catch {}
                }
            });

            // 2) Remove modal containers/backdrops/scroll locks
            const modalSelectors = [
                '.modal',
                '.modal-backdrop',
                '[aria-modal="true"]',
                '[role="dialog"]',
                '[role="alertdialog"]'
            ];
            modalSelectors.forEach(sel =>
                document.querySelectorAll(sel).forEach(el => el.remove())
            );
            document.body.classList.remove('modal-open', 'overflow-hidden');

            // 3) Hide or remove any OneTrust overlays
            document.querySelectorAll('[id^="onetrust"]').forEach(el => {
                try {
                    el.remove();
                } catch {
                    el.style.display = 'none';
                }
            });

            // 4) Close any native <dialog> elements
            document.querySelectorAll('dialog[open]').forEach(d => {
                try { d.close(); } catch {}
            });
        }
    """))


def scroll_to_bottom(page, pause_time: float = 1.0, max_loops: int = 50):
    last_height = page.evaluate("() => document.body.scrollHeight")
    for _ in range(max_loops):
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        time.sleep(pause_time)
        new_height = page.evaluate("() => document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height


def screenshot_region(
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
    viewport = page.viewport_size or page.evaluate(
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
    page.screenshot(path=tmp_path, clip=clip)
    return Path(tmp_path)


def safe_goto(page, url, **goto_kwargs):
    try:
        page.goto(url, **goto_kwargs)
    except Exception as e:
        if "Protocol error" in str(e):
            # Retry over plain fetch → click instead of navigation
            page.evaluate(f"window.location.href = {url!r}")
            page.wait_for_load_state("domcontentloaded")
        else:
            raise
