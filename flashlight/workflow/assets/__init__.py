import dagster as dg

@dg.asset(required_resource_keys={"browser_context"})
def privacy_policy_link(context):
    browser_ctx = context.resources.browser_context
    page = browser_ctx.new_page()
    page.goto(context.op_config["url"])
    href = page.locator("a:has-text('Privacy Policy')").get_attribute("href")
    page.close()
    return href

