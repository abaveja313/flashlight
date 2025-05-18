from typing import Generator, Any

from dagster import DagsterInstance
from dagster import resource, DynamicPartitionsDefinition
from dynaconf import Dynaconf
from playwright.sync_api import BrowserContext

from flashlight.workflow.resources.playwright_manager import PlaywrightManager

settings = Dynaconf(
    settings_files=["settings.toml", ".secrets.toml"],
    environments=True,
    default_env="default",
    load_dotenv=True,
)

domain_partitions = DynamicPartitionsDefinition(name="domain")


@resource
def config_resource(_):
    """
    Dynaconf-based config available via context.resources.config
    """
    return settings


@resource
def dagster_instance(_):
    return DagsterInstance.get()


@resource(required_resource_keys={"config"})
def user_agent_provider(context) -> str:
    """
    Provides a random, up-to-date User-Agent string using the fake-useragent library.
    Falls back to a default or config value if lookup fails.
    """
    # Lazy import so dependency is optional unless this resource is used
    try:
        from fake_useragent import UserAgent
        ua = UserAgent()
        return ua.random
    except Exception as e:
        context.log.warning(f"Failed to fetch random user-agent: {e}")
        return context.resources.config.USER_AGENT or 'Mozilla/5.0 (compatible; ScraperBot/1.0)'


@resource(required_resource_keys={"config"})
def playwright_manager(context) -> PlaywrightManager:
    """
    Resource that starts one browser per process using headless flag from config
    """
    headless = context.resources.config.PLAYWRIGHT_HEADLESS
    return PlaywrightManager(headless=headless)


@resource(required_resource_keys={"playwright_manager", "user_agent_provider"})
def browser_context(context) -> Generator[BrowserContext, None, Any]:
    """
    Yields a fresh BrowserContext on each invocation, with a dynamic fake User-Agent
    """
    mgr: PlaywrightManager = context.resources.playwright_manager
    user_agent = context.resources.user_agent_provider
    ctx = mgr.browser.new_context(user_agent=user_agent)
    try:
        yield ctx
    finally:
        ctx.close()
