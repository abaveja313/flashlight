import dagster as dg
import dagster_gemini as gemini
from dagster import AssetSpec


@dg.multi_asset(
    required_resource_keys={"browser_context"}
    specs=AssetSpec()
)
@dg.asset(required_resource_keys={"browser_context"}, kinds={"scraping", "gemini"})
def extract_privacy_policy(context):
    browser_ctx = context.resources.browser_context
    page = browser_ctx.new_page()
