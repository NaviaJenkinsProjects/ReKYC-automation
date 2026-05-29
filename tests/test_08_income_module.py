from playwright.sync_api import Page

import rekyc_module_common as common


class TestIncomeModule:
    def test_income_declaration_page_loads(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.run_income_module(page)
