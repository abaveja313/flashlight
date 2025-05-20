from dagster import job
from flashlight.workflow.assets import analyze_footer_screenshot, find_privacy_policy


@job
def ccpa_analysis():
    find_privacy_policy()
    analyze_footer_screenshot()
