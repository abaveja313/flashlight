# from browser_use.agent.views import ActionResult
# from browser_use.browser.browser import Browser
# from browser_use.controller.service import Controller
#
#
# def create_iframe_enabled_controller(*args, **kwargs):
#     controller = Controller(*args, **kwargs)
#
#     @controller.action("Click button inside an embedded iframe")
#     async def click_iframe_button(button_text: str, browser: Browser):
#         page = await browser.get_current_page()
#         for frame in page.frames:
#             # Look for an element (e.g. button or link) containing the desired text
#             element = await frame.query_selector(f"text=\"{button_text}\"")
#             if element:
#                 await element.click()
#                 return ActionResult(extracted_content=f"Clicked '{button_text}' in iframe")
#         return ActionResult(extracted_content=f"No '{button_text}' button found in iframes")
#
#     @controller.action("Click selector inside an embedded iframe")
#     async def click_iframe_selector(css_selector: str, browser: Browser):
#         """
#         Click first element matching `css_selector` in any frame.
#         Also tries clicking the closest <button>/<div> if the element itself
#         (e.g. an <svg>) is not directly clickable.
#         """
#         page = await browser.get_current_page()
#         for frame in page.frames:
#             el = await frame.query_selector(css_selector)
#             if el and await el.is_visible():
#                 try:
#                     await el.click()
#                 except Exception:
#                     # e.g. SVG not receiving pointer events → click nearest button
#                     parent = await el.evaluate_handle(
#                         '(e)=>e.closest("button,div")')
#                     if parent:
#                         await parent.as_element().click()
#                     else:
#                         raise
#                 return ActionResult(
#                     extracted_content=f"Clicked selector '{css_selector}' in iframe"
#                 )
#         return ActionResult(
#             extracted_content=f"Selector '{css_selector}' not found in any iframe"
#         )
