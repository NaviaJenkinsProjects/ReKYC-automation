from playwright.sync_api import Page

import rekyc_module_common as common


class TestAddressModule:
    def test_address_change_digilocker_verification(self, page: Page):
        common.reset_results()
        common.login_to_rekyc(page)
        common.core.complete_address_digilocker_verification(page)
