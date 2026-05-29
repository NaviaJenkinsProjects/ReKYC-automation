from playwright.sync_api import Page

import rekyc_module_common as common


class TestEmailModule:
    def test_email_modification_full_flow(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.run_email_module(page)
