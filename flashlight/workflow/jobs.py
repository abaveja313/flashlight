from dagster import job
from flashlight.workflow.assets import locate_privacy_policy

@job
def my_simple_job():
    locate_privacy_policy()