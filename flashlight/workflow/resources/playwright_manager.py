from playwright.sync_api import Playwright, sync_playwright, Browser


class PlaywrightManager:
    """
    Singleton per worker process: holds a single Browser instance
    """
    def __init__(self, headless: bool):
        self._playwright: Playwright = sync_playwright().start()
        self.browser: Browser = self._playwright.chromium.launch(headless=headless)

    def shutdown(self):
        self.browser.close()
        self._playwright.stop()
