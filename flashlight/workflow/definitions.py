from dagster import Definitions, define_asset_job
from dagster_aws.s3 import S3Resource

from flashlight.workflow.assets import find_privacy_policy, analyze_footer_screenshot
from flashlight.workflow.resources import settings, config_resource, LLMResource, browser_manager
from flashlight.workflow.resources.s3_file_manager import S3FileIOManager

defs = Definitions(
    assets=[find_privacy_policy, analyze_footer_screenshot],
    jobs=[define_asset_job(
        "deep_analysis"
    )],
    resources={
        "io_manager": S3FileIOManager(
            s3_bucket=settings.aws_s3_bucket,
            s3_prefix=settings.aws_s3_prefix,
            s3_resource=S3Resource()
        ),
        "config": config_resource,
        "browser_manager": browser_manager,
        "llm": LLMResource(
            model_name=settings.llm_model_name,
            temperature=settings.llm_temperature,
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
        ),
    },
)
