from contextlib import contextmanager
from typing import Generator, Optional

from dagster import ConfigurableResource, InitResourceContext
from pydantic import PrivateAttr
from fake_useragent import UserAgent
from loguru import logger
from playwright.sync_api import Playwright, sync_playwright, Browser, BrowserContext


class BrowserManager(ConfigurableResource):
    """
    Singleton per worker process: holds a single Browser instance.
    Provides a context manager for creating/tracing browser contexts.
    """
    # Exposed config field
    headless: bool = True

    _playwright: Optional[Playwright] = PrivateAttr(default=None)
    _browser: Optional[Browser] = PrivateAttr(default=None)

    def setup_for_execution(self, context: InitResourceContext) -> None:
        """
        Set up Playwright and launch the browser once per execution.
        """
        logger.info("Initializing Playwright...")
        self._playwright = sync_playwright().start()
        logger.info("Playwright started. Launching browser...")
        self._browser = self._playwright.chromium.launch(
            headless=self.headless,
            args=["--disable-spdy", "--disable-http2"],
        )

    @contextmanager
    def managed_context(
            self,
            *,
            tracing: bool = False,
            context_kwargs: Optional[dict] = None,
    ) -> Generator[BrowserContext, None, None]:
        """
        Yield a new BrowserContext with optional tracing enabled.
        Tracing can capture screenshots and snapshots per context.
        """
        ua = UserAgent().random
        logger.debug("Using User-Agent: %s", ua)
        ctx_kwargs = {
            "user_agent": ua,
            **(context_kwargs or {}),
        }
        ctx: BrowserContext = self._browser.new_context(**ctx_kwargs)
        try:
            yield ctx
        finally:
            logger.info("Closing BrowserContext...")
            ctx.close()

    def shutdown(self) -> None:
        """
        Tear down Playwright and browser on resource shutdown.
        """
        if self._browser:
            self._browser.close()
        if self._playwright:
            self._playwright.stop()
