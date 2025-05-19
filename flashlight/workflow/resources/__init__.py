from dagster import DagsterInstance
from dagster import resource, DynamicPartitionsDefinition
from dynaconf import Dynaconf

from flashlight.workflow.resources.browser_manager import BrowserManager
from flashlight.workflow.resources.llm_resource import LLMResource

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
