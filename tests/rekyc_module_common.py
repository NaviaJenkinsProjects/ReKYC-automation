import os
import sys

import pytest
from playwright.sync_api import Page

CURRENT_DIR = os.path.dirname(__file__)
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import ReKYC_Test as core


def reset_results():
    core._step_results_store["results"].clear()


def login_to_rekyc(page: Page):
    page.goto(core.REKYC_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(3000)
    if not core.fill_ucc(page, core.REKYC_UCC):
        raise Exception("UCC input field not found")
    if not core.click_first_visible(page, core.DOB_LOCATORS):
        raise Exception("DOB input field not found")
    page.wait_for_timeout(1000)
    page.locator(".yearselect").first.select_option(value=core.DOB_YEAR)
    page.locator(".monthselect").first.select_option(value=core.DOB_MONTH)
    day_number = str(int(core.DOB_DAY))
    dates = page.locator("td.available:not(.off):not(.disabled)")
    for i in range(dates.count()):
        cell = dates.nth(i)
        if cell.text_content().strip() == day_number:
            cell.click()
            break
    else:
        raise Exception("DOB day not found")
    core.handle_captcha_if_present(page)
    core.submit_login(page)
    page.wait_for_timeout(5000)
    core.handle_captcha_if_present(page)
    if not core.is_otp_page(page):
        core.submit_login(page)
        page.wait_for_timeout(10000)
    if not core.is_otp_page(page):
        raise Exception(f"OTP page not opened after login submit. Current URL: {page.url}")
    login_otp = core.fetch_latest_yopmail_otp(page, "Login OTP", core.REKYC_YOPMAIL)
    if not core.fill_otp(page, login_otp):
        raise Exception("Login OTP input field not found")
    core.submit_otp(page)
    page.wait_for_timeout(5000)
    if core.is_otp_page(page):
        raise Exception("Still on OTP page after valid login OTP submit")
    if not core.is_logged_in_dashboard(page):
        raise Exception(f"Dashboard did not load after login. Current URL: {page.url}")


def complete_common_signature_ipv_esign(page: Page):
    core.complete_post_service_esign_flow(page)


def run_email_module(page: Page):
    core.open_section(page, "Email")
    core.complete_service_otp_flow(page, "Email")
    complete_common_signature_ipv_esign(page)


def run_mobile_module(page: Page):
    core.open_section(page, "Mobile No")
    core.complete_service_otp_flow(page, "Mobile No")
    complete_common_signature_ipv_esign(page)


def run_nominee_module(page: Page):
    core.open_section(page, "Nominee")
    core.assert_nominee_loaded(page)
    core.continue_nominee(page)
    complete_common_signature_ipv_esign(page)


def run_income_module(page: Page):
    core.update_income_declaration(page)


def run_segment_module(page: Page):
    core.update_segment_and_protean_surakshaa(page)


def run_bank_module(page: Page):
    core.run_bank_module(page)


def block_manual_or_data_dependent(module_name: str, reason: str):
    pytest.skip(f"{module_name}: {reason}")
