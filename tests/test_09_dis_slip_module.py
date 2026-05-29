from playwright.sync_api import Page

import rekyc_module_common as common


class TestDisSlipModule:
    def test_dis_slip_page_loads(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.core.open_section(page, "Dis Slip Req")
        common.core.assert_validation_feedback(page, ["dp", "email", "mobile", "dis"], "DIS slip request page")
