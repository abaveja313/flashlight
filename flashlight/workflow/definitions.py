import dagster as dg
from dagster_aws.s3 import S3PickleIOManager, S3Resource

from flashlight.workflow.assets import find_privacy_policy_link
from flashlight.workflow.jobs import my_simple_job
from flashlight.workflow.resources import settings, config_resource, playwright_manager, browser_context, \
    user_agent_provider

defs = dg.Definitions(
    jobs=[my_simple_job],
    assets=[
        find_privacy_policy_link
    ],
    resources={
        "io_manager": S3PickleIOManager(
            s3_resource=S3Resource(),
            s3_bucket=settings.AWS_S3_BUCKET,
            s3_prefix=settings.AWS_S3_PREFIX,
        ),
        "user_agent_provider": user_agent_provider,
        "config": config_resource,
        "playwright_manager": playwright_manager,
        "browser_context": browser_context
    }
)
