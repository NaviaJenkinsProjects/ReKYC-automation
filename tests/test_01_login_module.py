from playwright.sync_api import Page

import rekyc_module_common as common


class TestLoginModule:
    def test_login_positive_flow(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
