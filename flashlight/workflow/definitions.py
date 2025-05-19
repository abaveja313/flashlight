from dagster import Definitions
from dagster_aws.s3 import S3Resource

from flashlight.workflow.assets import locate_privacy_policy
from flashlight.workflow.jobs import my_simple_job
from flashlight.workflow.resources import settings, config_resource, BrowserManager, LLMResource
from flashlight.workflow.resources.s3_file_manager import S3FileIOManager

defs = Definitions(
    jobs=[my_simple_job],
    assets=[locate_privacy_policy],
    resources={
        "io_manager": S3FileIOManager(
            s3_bucket=settings.aws_s3_bucket,
            s3_prefix=settings.aws_s3_prefix,
            s3_resource=S3Resource()
        ),
        "config": config_resource,
        "browser_context": BrowserManager(headless=settings.playwright_headless),
        "llm": LLMResource(
            model_name=settings.llm_model_name,
            temperature=settings.llm_temperature,
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
        ),
    },
)