import tempfile

from browser_use.browser.browser import BrowserConfig
from dagster import DagsterInstance
from dagster import resource, DynamicPartitionsDefinition
from dynaconf import Dynaconf
from managed_browser import BrowserManager

from flashlight.workflow.resources.llm_resource import LLMResource

settings = Dynaconf(
    settings_files=["settings.toml", ".secrets.toml"],
    environments=True,
    default_env="default",
    load_dotenv=True,
)

domain_partitions = DynamicPartitionsDefinition(name="domain")


@resource
def browser_manager(_) -> BrowserManager:
    # Allow cross origin iframe support
    # https://github.com/browser-use/browser-use/issues/443
    return BrowserManager(
        browser_config=BrowserConfig(
            headless=settings.playwright_headless,
            _force_keep_browser_alive=True,
            extra_browser_args=[
                # "--allow-running-insecure-content",
                # "--disable-web-security",
                # "--disable-site-isolation-trials",
                # "--disable-features=IsolateOrigins,site-per-process",
                # "--no-first-run",
                # "--no-default-browser-check",
            ],
            disable_security=True,
        )
    )


def config_resource(_):
    """
    Dynaconf-based config available via context.resources.config
    """
    return settings


@resource
def dagster_instance(_):
    return DagsterInstance.get()
