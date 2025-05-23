from dagster import Definitions, define_asset_job
from dagster_aws.s3 import S3Resource

from flashlight.assets import (
    prepare_window,
    extract_privacy_policy,
    extract_ccpa_policy,
    analyze_footer_screenshot,
)
from flashlight.resources import (
    settings,
    config_resource,
    LLMResource,
    browser_manager,
    TextExtractor,
)
from flashlight.resources.s3_file_manager import S3FileIOManager

defs = Definitions(
    assets=[
        prepare_window,
        extract_privacy_policy,
        extract_ccpa_policy,
        analyze_footer_screenshot,
    ],
    jobs=[define_asset_job("deep_analysis")],
    resources={
        "io_manager": S3FileIOManager(
            s3_bucket=settings.aws_s3_bucket,
            s3_prefix=settings.aws_s3_prefix,
            s3_resource=S3Resource(),
        ),
        "config": config_resource,
        "browser_manager": browser_manager,
        "text_extractor": TextExtractor(
            strategy=settings.html_extractor_strategy,
        ),
        "llm": LLMResource(
            model_name=settings.llm_model_name,
            temperature=settings.llm_temperature,
            provider=settings.llm_provider,
            api_key=settings.llm_api_key,
        ),
        "mini_llm": LLMResource(
            model_name=settings.mini_llm_model_name,
            temperature=settings.mini_llm_temperature,
            provider=settings.mini_llm_provider,
            api_key=settings.mini_llm_api_key,
        ),
    },
)
