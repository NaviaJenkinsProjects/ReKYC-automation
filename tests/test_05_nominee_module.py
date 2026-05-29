from playwright.sync_api import Page

import rekyc_module_common as common


class TestNomineeModule:
    def test_nominee_page_loads(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.run_nominee_module(page)
