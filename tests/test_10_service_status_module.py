from playwright.sync_api import Page

import rekyc_module_common as common


class TestServiceStatusModule:
    def test_service_status_page_loads(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.core.open_section(page, "Service Status")
        common.core.assert_validation_feedback(page, ["approved", "rejected", "pending", "status"], "service status page")
