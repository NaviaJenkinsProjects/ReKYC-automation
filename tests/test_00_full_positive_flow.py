import os

from playwright.sync_api import Page

import rekyc_module_common as common


DUPLICATE_SERVICE_EMAIL = "praveendinesh2005@gmail.com"
DUPLICATE_SERVICE_MOBILE = "8248652721"


def _active_page(page: Page, state: dict) -> Page:
    for candidate in page.context.pages:
        try:
            candidate_url = candidate.url.lower()
            if (
                not candidate.is_closed()
                and "rekyc.navia.co.in" in candidate_url
                and "login.php" not in candidate_url
            ):
                candidate.bring_to_front()
                state["page"] = candidate
                return candidate
        except Exception:
            continue
    for candidate in page.context.pages:
        try:
            if not candidate.is_closed() and "rekyc.navia.co.in" in candidate.url.lower():
                candidate.bring_to_front()
                state["page"] = candidate
                return candidate
        except Exception:
            continue
    try:
        current = state.get("page")
        if current and not current.is_closed():
            return current
    except Exception:
        pass
    for candidate in page.context.pages:
        try:
            if not candidate.is_closed():
                state["page"] = candidate
                return candidate
        except Exception:
            continue
    state["page"] = page.context.new_page()
    return state["page"]


def _ensure_rekyc_session(page: Page, state: dict) -> Page:
    live_page = _active_page(page, state)
    try:
        url = live_page.url.lower()
    except Exception:
        url = ""
    if "rekyc.navia.co.in" not in url:
        live_page.goto(common.core.REKYC_URL, wait_until="domcontentloaded", timeout=30000)
        live_page.wait_for_timeout(2000)
        try:
            url = live_page.url.lower()
        except Exception:
            url = ""
    if "rekyc.navia.co.in" in url and "login.php" not in url:
        state["page"] = live_page
        return live_page
    for attempt in range(1, 3):
        try:
            if common.core.is_logged_in_dashboard(live_page):
                state["page"] = live_page
                return live_page
        except Exception:
            pass
        try:
            common.login_to_rekyc(live_page)
            if common.core.is_logged_in_dashboard(live_page):
                break
        except Exception:
            if attempt == 2:
                raise
            common.core.reset_login_page(live_page)
            live_page.wait_for_timeout(2000)
    state["page"] = live_page
    return live_page


def _run_login_negative_scenarios(page: Page):
    common.core.reset_login_page(page)
    common.core.fill_ucc(page, "")
    common.core.submit_login(page)
    page.wait_for_timeout(2500)
    common.core.check_still_on_login(page)
    common.core.assert_validation_feedback(page, ["required", "please", "ucc", "dob", "enter"], "blank login validation")

    common.core.reset_login_page(page)
    common.core.fill_ucc(page, "INVALID123")
    common.core.submit_login(page)
    page.wait_for_timeout(2500)
    common.core.check_still_on_login(page)
    common.core.assert_validation_feedback(page, ["invalid", "ucc", "client", "please", "error"], "invalid UCC validation")

    common.core.reset_login_page(page)
    if os.environ.get("REKYC_HEADLESS", "").lower() == "true":
        common.core.fill_ucc(page, "")
        common.core.select_dob(page, common.core.DOB_YEAR, common.core.DOB_MONTH, common.core.DOB_DAY)
        common.core.submit_login(page)
        page.wait_for_timeout(2500)
        common.core.check_still_on_login(page)
        common.core.assert_validation_feedback(
            page,
            ["required", "please", "ucc", "client", "enter"],
            "blank UCC with DOB validation",
        )
        print("  [OK] Headless-safe login negatives completed without server-side failed DOB attempt")
        return

    common.core.fill_ucc(page, common.core.REKYC_UCC)
    common.core.select_dob(page, "2000", "0", "1")
    common.core.submit_login(page)
    page.wait_for_timeout(5000)
    common.core.check_still_on_login(page)
    common.core.assert_validation_feedback(page, ["invalid", "dob", "date", "wrong", "match", "error"], "wrong DOB validation")


def _assert_address_invalid_aadhaar(page: Page):
    common.core.open_section(page, "Change of address")
    digilocker_page = common.core.click_address_proceed_to_change(page)
    common.core.click_digilocker_first(digilocker_page, common.core.DIGILOCKER_AADHAAR_TAB_LOCATORS, "DigiLocker Aadhaar tab")
    common.core.fill_digilocker_field(
        digilocker_page,
        common.core.DIGILOCKER_AADHAAR_INPUT_LOCATORS,
        "111111111111",
        "invalid Aadhaar",
    )
    common.core.click_digilocker_first(digilocker_page, common.core.DIGILOCKER_NEXT_LOCATORS, "DigiLocker Next")
    digilocker_page.wait_for_timeout(3000)
    common.core.assert_validation_feedback(
        digilocker_page,
        ["invalid", "aadhaar", "aadhar", "uid", "please", "error"],
        "address invalid Aadhaar validation",
    )


def _submit_negative_otp_on_current_page(page: Page, otp_value: str, description: str):
    common.core.fill_first_visible(page, common.core.OTP_LOCATORS, otp_value)
    submitted = False
    for loc in common.core.OTP_SUBMIT_LOCATORS:
        try:
            button = page.locator(loc).first
            if button.is_visible(timeout=1000):
                if button.is_disabled(timeout=500):
                    break
                button.click(timeout=2000)
                submitted = True
                break
        except Exception:
            continue
    page.wait_for_timeout(2500)
    if "verify_otp" not in page.url.lower():
        raise Exception(f"{description} proceeded unexpectedly")
    try:
        common.core.assert_validation_feedback(
            page,
            ["otp", "invalid", "wrong", "incorrect", "digit", "required", "please", "enter", "error"],
            description,
        )
    except Exception:
        if not submitted:
            print(f"  [OK] {description} blocked because submit button is disabled")
            return
        raise
    print(f"  [OK] {description} correctly rejected")


def _run_current_otp_negatives_then_positive(page: Page, valid_otp: str, description: str):
    _submit_negative_otp_on_current_page(page, "", f"{description} blank OTP validation")
    _submit_negative_otp_on_current_page(page, "000000", f"{description} wrong OTP validation")
    _submit_negative_otp_on_current_page(page, "123", f"{description} short OTP validation")
    common.core.submit_current_otp_page(page, valid_otp, description)


def _run_negative_step(page: Page, step_number: int, step_name: str, action):
    def guarded_action():
        if "navia" not in page.url.lower():
            print(f"  [i] Skipping {step_name}: current URL is outside Navia ({page.url})")
            return
        action()

    common.core.run_step(step_number, step_name, guarded_action)


def _run_login_scenarios(page: Page):
    def blank_login():
        common.core.reset_login_page(page)
        common.core.fill_ucc(page, "")
        common.core.submit_login(page)
        page.wait_for_timeout(2500)
        common.core.check_still_on_login(page)
        common.core.assert_validation_feedback(page, ["required", "please", "ucc", "dob", "enter"], "blank login validation")

    common.core.run_step(1, "Negative login: Blank UCC and blank DOB", blank_login)

    def invalid_ucc():
        common.core.reset_login_page(page)
        common.core.fill_ucc(page, "INVALID123")
        common.core.submit_login(page)
        page.wait_for_timeout(2500)
        common.core.check_still_on_login(page)
        common.core.assert_validation_feedback(page, ["invalid", "ucc", "client", "please", "error"], "invalid UCC validation")

    common.core.run_step(2, "Negative login: Invalid UCC", invalid_ucc)

    def wrong_dob_login():
        common.core.reset_login_page(page)
        common.core.fill_ucc(page, common.core.REKYC_UCC)
        common.core.select_dob(page, "2000", "0", "1")
        common.core.submit_login(page)
        page.wait_for_timeout(5000)
        common.core.check_still_on_login(page)
        common.core.assert_validation_feedback(page, ["invalid", "dob", "date", "wrong", "match", "error"], "wrong DOB validation")

    common.core.run_step(3, "Negative login: Valid UCC and invalid DOB", wrong_dob_login)

    def submit_valid_login():
        common.core.reset_login_page(page)
        common.core.fill_ucc(page, common.core.REKYC_UCC)
        common.core.select_dob(page, common.core.DOB_YEAR, common.core.DOB_MONTH, common.core.DOB_DAY)
        common.core.handle_captcha_if_present(page)
        common.core.submit_login(page)
        page.wait_for_timeout(5000)
        common.core.handle_captcha_if_present(page)
        if not common.core.is_otp_page(page):
            common.core.submit_login(page)
            page.wait_for_timeout(10000)
        if not common.core.is_otp_page(page):
            raise Exception(f"OTP page not opened after login submit. Current URL: {page.url}")

    common.core.run_step(4, "Positive login: Valid UCC and valid DOB", submit_valid_login)
    common.core.run_step(12, "OTP Negative: Submit with blank OTP", lambda: _submit_negative_otp_on_current_page(page, "", "Login blank OTP validation"))
    common.core.run_step(13, "OTP Negative: Submit wrong OTP (000000)", lambda: _submit_negative_otp_on_current_page(page, "000000", "Login wrong OTP validation"))
    common.core.run_step(14, "OTP Negative: Submit short OTP (123)", lambda: _submit_negative_otp_on_current_page(page, "123", "Login short OTP validation"))

    def submit_valid_otp():
        otp = common.core.fetch_latest_yopmail_otp(page, "Login OTP", common.core.REKYC_YOPMAIL)
        common.core.fill_otp(page, otp)
        common.core.submit_otp(page)
        page.wait_for_timeout(5000)
        if common.core.is_otp_page(page):
            raise Exception("Still on OTP page after valid login OTP submit")
        if not common.core.is_logged_in_dashboard(page):
            raise Exception(f"Dashboard did not load after login. Current URL: {page.url}")

    common.core.run_step(15, "Positive OTP: Valid OTP from Yopmail", submit_valid_otp)


def _run_post_service_steps(page: Page):
    common.core.run_step(70, "Service Post-OTP: Upload signature", lambda: common.core.upload_signature_for_esign(page))
    common.core.run_step(72, "Service Post-OTP: ReKYC live IPV liveness capture (blink detection)", lambda: (common.core.prepare_ipv_browser(page), common.core.capture_ipv_photo(page)))
    common.core.run_step(71, "Service Post-OTP: View unsigned KYC PDF", lambda: common.core.view_unsigned_pdf(page))
    common.core.run_step(73, "Service Post-OTP: Proceed to Aadhaar eSign", lambda: common.core.proceed_to_esign(page))
    common.core.run_step(74, "Service Post-OTP: Complete Aadhaar eSign OTP", lambda: common.core.complete_aadhaar_esign(page))


def _open_new_value_otp_page(page: Page, section_name: str):
    if section_name.lower() == "email":
        if not common.core.fill_first_visible(page, common.core.SERVICE_EMAIL_INPUT_LOCATORS, common.core.NEW_SERVICE_EMAIL, timeout=10000):
            raise Exception("New email input field not found after existing email OTP")
        try:
            page.keyboard.press("Tab")
            page.locator("input[type='email'], input[name*='email' i], input[id*='email' i]").first.dispatch_event("change")
        except Exception:
            pass
        print(f"  [OK] New email entered: {common.core.NEW_SERVICE_EMAIL}")
    else:
        if not common.core.fill_first_visible(page, common.core.SERVICE_MOBILE_INPUT_LOCATORS, common.core.NEW_SERVICE_MOBILE, timeout=10000):
            raise Exception("New mobile input field not found after existing mobile OTP")
        try:
            page.keyboard.press("Tab")
            page.locator("input[name*='mobile' i], input[id*='mobile' i]").first.dispatch_event("change")
        except Exception:
            pass
        print(f"  [OK] New mobile number entered: {common.core.NEW_SERVICE_MOBILE}")

    page.wait_for_timeout(1000)
    if not common.core.click_continue_or_send_for_new_email(page):
        raise Exception(f"Continue/Send OTP button not found after entering new {section_name.lower()}")
    page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        common.core.click_first_visible(page, common.core.SERVICE_OKAY_LOCATORS, timeout=3000)
        page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        raise Exception(f"New {section_name.lower()} OTP verification page did not open")


def _assert_duplicate_new_service_value(page: Page, section_name: str):
    before_url = page.url
    if section_name.lower() == "email":
        duplicate_value = DUPLICATE_SERVICE_EMAIL
        if not common.core.fill_first_visible(page, common.core.SERVICE_EMAIL_INPUT_LOCATORS, duplicate_value, timeout=10000):
            raise Exception("New email input field not found for duplicate-email validation")
    else:
        duplicate_value = DUPLICATE_SERVICE_MOBILE
        if not common.core.fill_first_visible(page, common.core.SERVICE_MOBILE_INPUT_LOCATORS, duplicate_value, timeout=10000):
            raise Exception("New mobile input field not found for duplicate-mobile validation")

    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    page.wait_for_timeout(1000)
    if not common.core.click_continue_or_send_for_new_email(page):
        raise Exception(f"Continue/Send OTP button not found for duplicate {section_name.lower()} validation")
    page.wait_for_timeout(3000)

    if "verify_otp" in page.url.lower() and page.url != before_url:
        raise Exception(f"Duplicate {section_name.lower()} value unexpectedly proceeded to OTP page")

    common.core.assert_validation_feedback(
        page,
        ["already", "exist", "mapped", "registered", "linked", "another", "duplicate", "email", "mobile"],
        f"duplicate {section_name.lower()} validation",
    )
    common.core.click_first_visible(page, common.core.SERVICE_OKAY_LOCATORS, timeout=2000)
    print(f"  [OK] Duplicate {section_name.lower()} rejected: {duplicate_value}")


def _submit_existing_service_otp_then_duplicate_value(page: Page, section_name: str, existing_otp: str):
    common.core.submit_current_otp_page(page, existing_otp, f"{section_name} existing")
    _assert_duplicate_new_service_value(page, section_name)


def _run_email_module_with_inline_negatives(page: Page):
    common.core.run_step(18, "Email Section", lambda: common.core.open_section(page, "Email"))
    common.core.start_service_otp_verification(page, "Email")
    existing_otp = common.core.fetch_latest_yopmail_otp(page, "Email existing-mail OTP", common.core.EXISTING_SERVICE_OTP_EMAIL)
    _run_negative_step(page, 61, "Email Negative: Submit blank OTP", lambda: _submit_negative_otp_on_current_page(page, "", "Email existing-mail blank OTP validation"))
    _run_negative_step(page, 62, "Email Negative: Submit wrong OTP", lambda: _submit_negative_otp_on_current_page(page, "000000", "Email existing-mail wrong OTP validation"))
    _run_negative_step(page, 63, "Email Negative: Submit short OTP", lambda: _submit_negative_otp_on_current_page(page, "123", "Email existing-mail short OTP validation"))

    def complete_email_positive():
        _open_new_value_otp_page(page, "Email")
        new_email_otp = common.core.fetch_latest_yopmail_otp(page, "Email new-mail OTP", common.core.NEW_SERVICE_EMAIL)
        common.core.submit_current_otp_page(page, new_email_otp, "Email new-mail")

    common.core.run_step(
        129,
        "Email Negative: Existing email linked with another account",
        lambda: _submit_existing_service_otp_then_duplicate_value(page, "Email", existing_otp),
    )
    common.core.run_step(69, "Email Positive: Complete email OTP flow using E-mail OTP", complete_email_positive)
    _run_post_service_steps(page)


def _run_mobile_module_with_inline_negatives(page: Page):
    common.core.run_step(19, "Mobile Section", lambda: common.core.open_section(page, "Mobile No"))
    common.core.start_service_otp_verification(page, "Mobile No")
    existing_otp = common.core.fetch_latest_yopmail_otp(page, "Mobile existing OTP", common.core.EXISTING_MOBILE_OTP_EMAIL)
    _run_negative_step(page, 65, "Mobile Negative: Submit blank OTP", lambda: _submit_negative_otp_on_current_page(page, "", "Mobile existing blank OTP validation"))
    _run_negative_step(page, 66, "Mobile Negative: Submit wrong OTP", lambda: _submit_negative_otp_on_current_page(page, "000000", "Mobile existing wrong OTP validation"))
    _run_negative_step(page, 67, "Mobile Negative: Submit short OTP", lambda: _submit_negative_otp_on_current_page(page, "123", "Mobile existing short OTP validation"))

    def complete_mobile_positive():
        _open_new_value_otp_page(page, "Mobile No")
        new_mobile_otp = common.core.fetch_latest_yopmail_otp(page, "Mobile new OTP", common.core.NEW_MOBILE_OTP_EMAIL)
        common.core.submit_current_otp_page(page, new_mobile_otp, "Mobile new")

    common.core.run_step(
        130,
        "Mobile Negative: Existing mobile linked with another account",
        lambda: _submit_existing_service_otp_then_duplicate_value(page, "Mobile No", existing_otp),
    )
    common.core.run_step(68, "Mobile Positive: Complete mobile OTP flow using E-mail OTP", complete_mobile_positive)
    _run_post_service_steps(page)


def _assert_nominee_blank_required(page: Page):
    common.core.open_section(page, "Nominee")
    common.core.open_fresh_nominee_form(page)
    common.core.clear_nominee_required_fields(page)
    common.core.submit_nominee(page)
    common.core.assert_validation_feedback(
        page,
        ["required", "please", "nominee", "pan", "mobile", "relation", "share", "email"],
        "nominee required field validation",
    )


def _assert_nominee_invalid_field(page: Page, locators, value: str, keywords, description: str):
    common.core.open_section(page, "Nominee")
    common.core.fill_nominee_positive_data(page, minor=False)
    common.core.fill_last_visible_nominee_field(page, locators, value, description)
    common.core.submit_nominee(page)
    common.core.assert_validation_feedback(page, keywords, f"nominee {description} validation")
    print(f"  [OK] Nominee {description} rejected")


def _assert_nominee_invalid_field_on_current_form(page: Page, locators, value: str, keywords, description: str):
    common.core.fill_nominee_positive_data(page, minor=False)
    common.core.fill_last_visible_nominee_field(page, locators, value, description)
    common.core.submit_nominee(page)
    common.core.assert_validation_feedback(page, keywords, f"nominee {description} validation")
    print(f"  [OK] Nominee {description} rejected")


def _assert_nominee_add_without_declaration(page: Page):
    common.core.open_section(page, "Nominee")
    page.evaluate(
        """
        () => {
            for (const box of document.querySelectorAll("input[type='checkbox']")) {
                box.checked = false;
                box.removeAttribute('checked');
                box.dispatchEvent(new Event('input', { bubbles: true }));
                box.dispatchEvent(new Event('change', { bubbles: true }));
            }
        }
        """
    )
    before_url = page.url
    common.core.click_nominee_add_button(page, "summary Add Nominee(s) without declaration")
    page.wait_for_timeout(2000)
    if "add_nominee" in page.url.lower() and page.url != before_url:
        raise Exception("Add Nominee proceeded without selecting declaration checkbox")
    common.core.assert_validation_feedback(page, ["nomination", "confirm", "checkbox", "wish", "nominee"], "nominee declaration validation")


def _assert_nominee_minor_without_guardian(page: Page):
    common.core.fill_last_visible_nominee_field(page, common.core.NOMINEE_PAN_LOCATORS, "987654567890", "PAN/Aadhaar Number")
    common.core.fill_last_visible_nominee_field(page, common.core.NOMINEE_NAME_LOCATORS, "Minor Nominee", "Nominee Name")
    common.core.fill_last_visible_nominee_field(page, common.core.NOMINEE_MOBILE_LOCATORS, "9876543210", "Mobile")
    common.core.select_last_nominee_relation(page, "brother")
    common.core.fill_last_visible_nominee_field(page, common.core.NOMINEE_SHARE_LOCATORS, "50", "Share")
    common.core.fill_last_visible_nominee_field(page, common.core.NOMINEE_DOB_LOCATORS, common.core.MINOR_NOMINEE_DOB, "Date of Birth")
    common.core.trigger_field_change(page, common.core.NOMINEE_DOB_LOCATORS)
    common.core.fill_last_visible_nominee_field(page, common.core.NOMINEE_EMAIL_LOCATORS, "minor.nominee@example.com", "Email")
    common.core.set_last_address_as_client(page, True)
    common.core.submit_nominee(page)
    common.core.assert_validation_feedback(page, ["guardian", "minor", "required", "please"], "minor nominee guardian validation")


def _run_nominee_negative_scenarios_fast(page: Page):
    common.core.run_step(97, "Nominee Negative: Add nominee without declaration", lambda: _assert_nominee_add_without_declaration(page))

    common.core.open_section(page, "Nominee")
    common.core.open_fresh_nominee_form(page)
    common.core.run_step(32, "Nominee Negative: Submit blank nominee form", lambda: (
        common.core.clear_nominee_required_fields(page),
        common.core.submit_nominee(page),
        common.core.assert_validation_feedback(
            page,
            ["required", "please", "nominee", "pan", "mobile", "relation", "share", "email"],
            "nominee required field validation",
        ),
    ))
    common.core.run_step(33, "Nominee Negative: Invalid PAN/Aadhaar", lambda: _assert_nominee_invalid_field_on_current_form(
        page,
        common.core.NOMINEE_PAN_LOCATORS,
        "123",
        ["pan", "aadhaar", "valid", "invalid", "number"],
        "invalid PAN/Aadhaar",
    ))
    common.core.run_step(35, "Nominee Negative: Invalid mobile", lambda: _assert_nominee_invalid_field_on_current_form(
        page,
        common.core.NOMINEE_MOBILE_LOCATORS,
        "123",
        ["mobile", "phone", "valid", "invalid", "10"],
        "invalid mobile",
    ))
    common.core.run_step(37, "Nominee Negative: Invalid share", lambda: _assert_nominee_invalid_field_on_current_form(
        page,
        common.core.NOMINEE_SHARE_LOCATORS,
        "150",
        ["percentage", "share", "100", "invalid", "allocation"],
        "invalid share",
    ))
    common.core.run_step(38, "Nominee Negative: Future DOB", lambda: _assert_nominee_invalid_field_on_current_form(
        page,
        common.core.NOMINEE_DOB_LOCATORS,
        "01-01-2099",
        ["dob", "date", "birth", "future", "invalid", "age"],
        "future DOB",
    ))
    common.core.run_step(39, "Nominee Negative: Invalid email", lambda: _assert_nominee_invalid_field_on_current_form(
        page,
        common.core.NOMINEE_EMAIL_LOCATORS,
        "bad-email",
        ["email", "valid", "invalid"],
        "invalid email",
    ))
    common.core.run_step(40, "Nominee Negative: Minor nominee without guardian", lambda: _assert_nominee_minor_without_guardian(page))


def _assert_nominee_negative_scenarios(page: Page):
    _assert_nominee_blank_required(page)
    _assert_nominee_invalid_field(
        page,
        common.core.NOMINEE_PAN_LOCATORS,
        "123",
        ["pan", "aadhaar", "valid", "invalid", "number"],
        "invalid PAN/Aadhaar",
    )
    _assert_nominee_invalid_field(
        page,
        common.core.NOMINEE_MOBILE_LOCATORS,
        "123",
        ["mobile", "phone", "valid", "invalid", "10"],
        "invalid mobile",
    )
    _assert_nominee_invalid_field(
        page,
        common.core.NOMINEE_SHARE_LOCATORS,
        "150",
        ["percentage", "share", "100", "invalid", "allocation"],
        "invalid share",
    )
    _assert_nominee_invalid_field(
        page,
        common.core.NOMINEE_DOB_LOCATORS,
        "01-01-2099",
        ["dob", "date", "birth", "future", "invalid", "age"],
        "future DOB",
    )
    _assert_nominee_invalid_field(
        page,
        common.core.NOMINEE_EMAIL_LOCATORS,
        "bad-email",
        ["email", "valid", "invalid"],
        "invalid email",
    )


def _assert_bank_invalid_account_ifsc(page: Page):
    common.core.click_bank_add_account(page)
    common.core.click_bank_manual_entry(page)
    common.core.fill_required_first_visible(page, common.core.BANK_ACCOUNT_LOCATORS, "123", "Invalid bank account number")
    common.core.fill_optional_first_visible(page, common.core.BANK_CONFIRM_ACCOUNT_LOCATORS, "123")
    common.core.fill_required_first_visible(page, common.core.BANK_IFSC_LOCATORS, "BADIFSC", "Invalid IFSC")
    try:
        common.core.click_bank_verify(page)
    except Exception:
        # Invalid account/IFSC can keep the Verify button disabled via HTML5 validation.
        pass
    common.core.assert_validation_feedback(page, ["invalid", "ifsc", "account", "verify", "bank"], "invalid bank account/IFSC validation")


def _assert_bank_without_proof(page: Page):
    common.core.click_bank_add_account(page)
    common.core.click_bank_manual_entry(page)
    common.core.fill_bank_positive_data(page)
    common.core.click_bank_verify(page)
    common.core.accept_bank_name_mismatch_if_present(page)
    common.core.submit_bank(page)
    common.core.assert_validation_feedback(page, ["proof", "upload", "please select"], "bank proof validation")


def _assert_segment_without_any_change(page: Page):
    common.core.open_section(page, "Segment")
    common.core.accept_segment_risk_disclosure_if_present(page)
    if not common.core.click_first_visible(page, common.core.SEGMENT_SUBMIT_LOCATORS, timeout=10000):
        raise Exception("Segment Submit button not found")
    page.wait_for_timeout(2500)
    common.core.assert_validation_feedback(page, ["segment", "activate", "deactivate", "select", "change"], "segment no-change validation")


def _assert_segment_without_required_checkbox(page: Page):
    common.core.open_section(page, "Segment")
    common.core.accept_segment_risk_disclosure_if_present(page)
    common.core.enable_bfo_segment(page)
    page.evaluate(
        """
        () => {
            const terms = Array.from(document.querySelectorAll('body *')).find((el) => {
                const s = window.getComputedStyle(el);
                if (s.display === 'none' || s.visibility === 'hidden') return false;
                const text = (el.innerText || el.textContent || '').toLowerCase();
                return text.includes('i am aware') && text.includes('mtf') && text.includes('accept the terms');
            });
            if (!terms) return false;
            let row = terms;
            for (let i = 0; i < 7 && row; i += 1) {
                const text = (row.innerText || row.textContent || '').toLowerCase();
                const box = row.querySelector && row.querySelector("input[type='checkbox']");
                if (box && text.includes('i am aware') && text.includes('accept the terms') && !text.includes('account closure')) {
                    box.checked = false;
                    box.removeAttribute('checked');
                    box.dispatchEvent(new Event('input', { bubbles: true }));
                    box.dispatchEvent(new Event('change', { bubbles: true }));
                    return true;
                }
                row = row.parentElement;
            }
            return false;
        }
        """
    )
    if not common.core.click_first_visible(page, common.core.SEGMENT_SUBMIT_LOCATORS, timeout=10000):
        raise Exception("Segment Submit button not found")
    page.wait_for_timeout(2500)
    common.core.assert_validation_feedback(
        page,
        ["mtf", "terms", "condition", "checkbox", "accept", "aware"],
        "segment terms checkbox validation",
    )


def _assert_income_without_slab(page: Page):
    common.core.open_section(page, "Income Declaration")
    common.core.open_income_edit_page(page)
    if not common.core.click_first_visible(page, common.core.INCOME_UPDATE_LOCATORS, timeout=5000):
        raise Exception("Income declaration Update button not found")
    page.wait_for_timeout(2500)
    common.core.assert_validation_feedback(page, ["income", "slab", "select", "please"], "income slab validation")


def _assert_dis_slip_without_checkbox(page: Page):
    common.core.open_section(page, "Dis Slip Req")
    if common.core.click_first_visible(
        page,
        [
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed')]",
            "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed')]",
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
        ],
        timeout=5000,
    ):
        page.wait_for_timeout(2000)
        common.core.assert_validation_feedback(page, ["checkbox", "agree", "declaration", "please"], "DIS slip checkbox validation")
        return
    text = common.core.visible_text(page).lower()
    if "dis" not in text and "slip" not in text:
        raise Exception("DIS Slip request page did not load")
    print("  [OK] DIS Slip proceed is not available until declaration is selected")


def _assert_service_status_loads(page: Page):
    common.core.open_section(page, "Service Status")
    text = common.core.visible_text(page).lower()
    if "status" not in text and "service" not in text:
        raise Exception("Service Status page did not load")
    print("  [OK] Service Status page loaded")


def _assert_documents_section_loads(page: Page):
    common.core.open_section(page, "Documents")
    text = common.core.visible_text(page).lower()
    if "document" not in text and "proof" not in text:
        raise Exception("Documents section did not load")
    print("  [OK] Documents section loaded")


def _view_document_proof(page: Page, proof_number: int):
    common.core.open_section(page, "Documents")
    common.core.view_document_proof(page, proof_number)
    print(f"  [OK] Document proof {proof_number} viewed")


class TestFullPositiveFlow:
    def test_all_modules_negative_then_positive_single_login(self, page: Page):
        common.reset_results()
        state = {"page": page}

        _run_login_scenarios(page)
        state["page"] = page

        def fail_step(step_number: int, step_name: str, err: Exception):
            common.core.run_step(
                step_number,
                step_name,
                lambda: (_ for _ in ()).throw(err),
            )

        def run_flow(fallback_step: int, fallback_name: str, runner):
            try:
                runner(_ensure_rekyc_session(page, state))
                state["page"] = _active_page(page, state)
            except Exception as err:
                fail_step(fallback_step, fallback_name, err)

        def run_scenario(step_number: int, step_name: str, runner, negative: bool = False):
            current_page = _active_page(page, state)
            if negative and "navia" not in current_page.url.lower():
                print(f"  [i] Skipping {step_name}: current URL is outside Navia ({current_page.url})")
                return
            common.core.run_step(
                step_number,
                step_name,
                lambda: runner(_ensure_rekyc_session(page, state)),
            )
            state["page"] = _active_page(page, state)

        run_flow(69, "Email Positive: Complete email OTP flow using E-mail OTP", _run_email_module_with_inline_negatives)
        run_flow(68, "Mobile Positive: Complete mobile OTP flow using E-mail OTP", _run_mobile_module_with_inline_negatives)

        run_scenario(20, "Address Section", lambda p: common.core.open_section(p, "Change of address"))
        run_flow(77, "Address Positive: DigiLocker Aadhaar verification", common.core.complete_address_digilocker_verification)

        run_scenario(21, "Nominee Section", lambda p: common.core.open_section(p, "Nominee"))
        if "navia" in _active_page(page, state).url.lower():
            _run_nominee_negative_scenarios_fast(_ensure_rekyc_session(page, state))
        run_flow(41, "Nominee Positive: Valid nominee details", common.run_nominee_module)

        run_scenario(22, "Bank Section", lambda p: common.core.open_section(p, "Bank"))
        run_scenario(46, "Bank Negative: Invalid account number and IFSC", _assert_bank_invalid_account_ifsc, negative=True)
        run_scenario(45, "Bank Negative: Submit without proof", _assert_bank_without_proof, negative=True)
        run_flow(50, "Bank Positive: Valid bank details and statement proof", common.run_bank_module)

        run_scenario(27, "Documents Positive: Section loads", _assert_documents_section_loads)
        run_scenario(28, "Documents Positive: View proof 1", lambda p: _view_document_proof(p, 1))
        run_scenario(29, "Documents Positive: View proof 2", lambda p: _view_document_proof(p, 2))

        run_scenario(23, "Segment Section", lambda p: common.core.open_section(p, "Segment"))
        run_scenario(115, "Segment Negative: Submit without segment change", _assert_segment_without_any_change, negative=True)
        run_scenario(114, "Segment Negative: Submit without required checkbox", _assert_segment_without_required_checkbox, negative=True)
        run_flow(112, "Segment Positive: BSE derivative activation", common.run_segment_module)

        run_scenario(24, "Income Declaration Section", lambda p: common.core.open_section(p, "Income Declaration"))
        run_scenario(126, "Income Declaration Negative: Update without income slab", _assert_income_without_slab, negative=True)
        run_flow(125, "Income Declaration Positive: Update selected income slab", common.run_income_module)

        run_scenario(25, "DIS Slip Section", lambda p: common.core.open_section(p, "Dis Slip Req"))
        run_scenario(127, "DIS Slip Negative: Declaration/proceed validation", _assert_dis_slip_without_checkbox, negative=True)
        run_scenario(26, "Service Status positive check", _assert_service_status_loads)

        common.core.assert_all_steps_passed()
