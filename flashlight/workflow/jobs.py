from dagster import job
from flashlight.workflow.assets import find_privacy_policy_link

@job
def my_simple_job():
    find_privacy_policy_link()