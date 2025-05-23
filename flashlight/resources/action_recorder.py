import copy
import json
from types import MethodType

from playwright.async_api import BrowserContext, Page


class PageActionRecorder:
    """
    Async context manager that:
      - Assigns an incremental `page_id` to each Page (initial & new).
      - Logs a "new_page" event plus every call to key Page methods.
      - On exit, restores all methods and removes its listener.
      - Provides `replay()` to re-run the recorded sequence on a new context.
    """

    def __init__(self, browser_context: BrowserContext):
        self.browser_context = browser_context
        self.recorded_actions = []  # List[{"action","page_id","args","kwargs"}]
        self._original_methods = []  # List[(Page, method_name, original)]
        self._on_page = None  # the listener handle
        self._page_ids = {}  # Page → int
        self._next_id = 1

    def _assign_id(self, page: Page) -> int:
        pid = self._next_id
        self._next_id += 1
        self._page_ids[page] = pid
        setattr(page, "_recorder_page_id", pid)
        return pid

    async def __aenter__(self):
        # patch fn that will both assign an ID + monkey-patch the page
        def _patch(page: Page):
            # 1) Assign a new_id if unseen, and log it
            if page not in self._page_ids:
                pid = self._assign_id(page)
                self.recorded_actions.append(
                    {"action": "new_page", "page_id": pid, "args": (), "kwargs": {}}
                )

            # 2) Wrap key methods
            method_names = [
                "goto",
                "reload",
                "go_back",
                "go_forward",
                "click",
                "dblclick",
                "fill",
                "type",
                "press",
                "check",
                "uncheck",
                "select_option",
                "set_input_files",
                "evaluate",
                "evaluate_handle",
                "wait_for_timeout",
                "close",
                "wait_for_selector",
                "wait_for_load_state",
                "wait_for_navigation",
            ]
            for name in method_names:
                if not hasattr(page, name):
                    continue
                orig = getattr(page, name)
                # don't patch twice
                if any(page is p and name == m for (p, m, _) in self._original_methods):
                    continue
                self._original_methods.append((page, name, orig))

                # create patched coroutine
                async def _patched(self, *args, __orig=orig, __name=name, **kwargs):
                    pid = getattr(self, "_recorder_page_id")
                    self._recorder.recorded_actions.append(
                        {
                            "action": __name,
                            "page_id": pid,
                            "args": args,
                            "kwargs": kwargs,
                        }
                    )
                    # forward
                    return await __orig(*args, **kwargs)

                setattr(page, "_recorder", self)
                setattr(page, name, MethodType(_patched, page))

        # Patch all existing pages
        for pg in self.browser_context.pages:
            _patch(pg)

        # Subscribe to new pages
        self._on_page = lambda pg: _patch(pg)
        self.browser_context.on("page", self._on_page)

        return self

    async def snapshot(self, use_json: bool = False):
        """
        Returns a deep copy of the current recorded actions list.
        This allows you to take checkpoints during recording.
        """
        transform = json.dumps if use_json else lambda x: x
        return transform(copy.deepcopy(self.recorded_actions))

    @staticmethod
    async def replay(browser_context: BrowserContext, actions_json: str) -> Page:
        """
        Replay a previously recorded sequence of actions (as JSON) on
        the given BrowserContext. Closes all existing pages first,
        and returns the Page that was active in the last recorded action.
        """
        # 1) Deserialize
        actions = json.loads(actions_json)

        # 2) Close all current pages
        for pg in list(browser_context.pages):
            await pg.close()

        # 3) Map recorded page_ids to new Page instances
        page_map: dict[int, Page] = {}
        last_pid: int | None = None

        # 4) Replay every action
        for act in actions:
            name = act["action"]
            pid = act["page_id"]
            args = act.get("args", ())
            kwargs = act.get("kwargs", {})

            if name == "new_page":
                page = await browser_context.new_page()
                page_map[pid] = page
            else:
                page = page_map.get(pid)
                if page is None:
                    raise RuntimeError(f"No page found for id {pid} during replay")
                await getattr(page, name)(*args, **kwargs)

            last_pid = pid

        # 5) Return the page corresponding to the last action
        return page_map.get(last_pid)

    async def __aexit__(self, exc_type, exc, tb):
        # Unsubscribe listener
        if self._on_page:
            try:
                self.browser_context.off("page", self._on_page)
            except Exception:
                pass

        # Restore original methods
        for page, name, orig in self._original_methods:
            try:
                setattr(page, name, orig)
                delattr(page, "_recorder")
                delattr(page, "_recorder_page_id")
            except Exception:
                pass

        # Clear state
        self._original_methods.clear()
        self._on_page = None
        return False  # don’t suppress exceptions
