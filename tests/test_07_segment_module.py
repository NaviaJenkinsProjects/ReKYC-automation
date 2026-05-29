from playwright.sync_api import Page

import rekyc_module_common as common


class TestSegmentModule:
    def test_segment_page_loads(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.run_segment_module(page)
