from playwright.sync_api import Page

import rekyc_module_common as common


class TestBankModule:
    def test_bank_add_account_flow(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.run_bank_module(page)
