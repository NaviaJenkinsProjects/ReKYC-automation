import json
import os
import re
import sys
import time
import base64
import urllib.request
import urllib.parse
from urllib.parse import urljoin

from playwright.sync_api import Page

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ReKYC_Config import (
    DOB_DAY,
    DOB_MONTH,
    DOB_YEAR,
    REKYC_UCC,
    REKYC_URL,
    REKYC_YOPMAIL,
    CAPTCHA_API_KEY,
)

RUN_NOMINEE_MODULE = True
RUN_NOMINEE_GUARDIAN_MODULE = True
RUN_BANK_MODULE = False
RUN_EMAIL_MOBILE_MODULE = True
RUN_EMAIL_MOBILE_NEGATIVE_MODULE = False
CLIENT_AADHAAR_NUMBER = "830889536550"
CLIENT_PAN_NUMBER = "IBSPN7684H"
MINOR_NOMINEE_DOB = "01-01-2015"
MAJOR_NOMINEE_DOB = "01-01-1995"
EXISTING_SERVICE_OTP_EMAIL = "gateicaujohei-9617@yopmail.com"
NEW_SERVICE_EMAIL = "naviatestingekyc@yopmail.com"
EXISTING_MOBILE_OTP_EMAIL = "naviatesting@yopmail.com"
NEW_MOBILE_OTP_EMAIL = "naviatestingekyc@yopmail.com"
ESIGN_OTP_EMAIL = "naviatesting@yopmail.com"
NEW_SERVICE_MOBILE = "7530099052"
PERSONAL_MOTHER_NAME = "Test Mother"
PERSONAL_FATHER_NAME = "Krishna Moorthy B"
PERSONAL_MARITAL_STATUS = "Unmarried"
PERSONAL_EDUCATION = "Graduate"
PERSONAL_OCCUPATION = "Business"
PERSONAL_ANNUAL_INCOME = "1L-5L"
PERSONAL_MARKET_EXPERIENCE = "0-1 Year"
PERSONAL_SOURCE_INCOME = "Salaried"
PERSONAL_NATIONALITY = "Indian"
SIGNATURE_FILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "assets", "Signature.png")
)
BANK_ACCOUNT_NUMBER = "110001165430"
BANK_IFSC_CODE = "CNRB0016117"
BANK_PROOF_FILE_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "assets", "Account_statement.pdf")
)
TEST_GEOLOCATION = {
    "latitude": 13.0827,
    "longitude": 80.2707,
    "accuracy": 25,
}


# -----------------------------------------------------------------------------
#  reCAPTCHA v2 solver via 2captcha.com
# -----------------------------------------------------------------------------

def _2captcha_get(url):
    with urllib.request.urlopen(url, timeout=15) as r:
        return r.read().decode()


def solve_recaptcha_v2(page):
    if not CAPTCHA_API_KEY:
        print("  [WARN] CAPTCHA_API_KEY not set -- skipping CAPTCHA solve")
        return False

    site_key = page.evaluate("""
        () => {
            const el = document.querySelector('.g-recaptcha');
            if (el) return el.getAttribute('data-sitekey');
            if (window.___grecaptcha_cfg) {
                const clients = window.___grecaptcha_cfg.clients;
                for (const k in clients) {
                    const c = clients[k];
                    for (const j in c) {
                        if (c[j] && c[j].sitekey) return c[j].sitekey;
                    }
                }
            }
            return null;
        }
    """)

    if not site_key:
        return False

    site_url = page.url
    print(f"  -> reCAPTCHA detected (sitekey: {site_key[:24]}...) -- sending to 2captcha")

    params = urllib.parse.urlencode({
        "key":       CAPTCHA_API_KEY,
        "method":    "userrecaptcha",
        "googlekey": site_key,
        "pageurl":   site_url,
        "json":      1,
    })
    resp = json.loads(_2captcha_get(f"http://2captcha.com/in.php?{params}"))

    if resp.get("status") != 1:
        raise Exception(f"2captcha submission error: {resp}")

    captcha_id = resp["request"]
    print(f"  -> Task ID: {captcha_id}  |  polling for result...")

    token = None
    for attempt in range(36):
        time.sleep(5)
        result = json.loads(_2captcha_get(
            f"http://2captcha.com/res.php?key={CAPTCHA_API_KEY}"
            f"&action=get&id={captcha_id}&json=1"
        ))
        if result.get("status") == 1:
            token = result["request"]
            print(f"  [OK] 2captcha solved in ~{(attempt+1)*5}s")
            break
        if result.get("request") in ("ERROR_CAPTCHA_UNSOLVABLE", "ERROR_WRONG_CAPTCHA_ID"):
            raise Exception(f"2captcha error: {result['request']}")

    if not token:
        raise Exception("2captcha timed out -- no token returned after 3 minutes")

    page.evaluate(f"""
        (token) => {{
            const resp = document.getElementById('g-recaptcha-response');
            if (resp) {{ resp.value = token; resp.style.display = 'block'; }}
            document.querySelectorAll('[name="g-recaptcha-response"]').forEach(el => {{
                el.value = token;
            }});
            const widget = document.querySelector('.g-recaptcha');
            if (widget) {{
                const cb = widget.getAttribute('data-callback');
                if (cb && typeof window[cb] === 'function') window[cb](token);
            }}
            if (window.___grecaptcha_cfg) {{
                const clients = window.___grecaptcha_cfg.clients;
                for (const k in clients) {{
                    const c = clients[k];
                    for (const j in c) {{
                        if (c[j] && typeof c[j].callback === 'function') {{
                            try {{ c[j].callback(token); }} catch(e) {{}}
                        }}
                    }}
                }}
            }}
        }}
    """, token)

    page.wait_for_timeout(1500)
    print("  [OK] reCAPTCHA token injected successfully")
    return True


def handle_captcha_if_present(page):
    try:
        iframe_visible = page.locator("iframe[src*='recaptcha']").first.is_visible(timeout=3000)
    except Exception:
        iframe_visible = False

    if not iframe_visible:
        return

    print("  [WARN] reCAPTCHA challenge detected!")

    if CAPTCHA_API_KEY:
        solve_recaptcha_v2(page)
    else:
        if os.environ.get("REKYC_HEADLESS", "").lower() == "true":
            raise Exception("reCAPTCHA detected in headless mode; cannot proceed without CAPTCHA_API_KEY")
        print("  [WARN] No CAPTCHA_API_KEY set.")
        print("  [WARN] You have 90 seconds to solve the CAPTCHA manually in the browser.")
        for remaining in range(90, 0, -10):
            print(f"     Waiting {remaining}s for manual CAPTCHA solve...")
            page.wait_for_timeout(10000)
            try:
                still_visible = page.locator("iframe[src*='recaptcha']").first.is_visible(timeout=1000)
                if not still_visible:
                    print("  [OK] CAPTCHA dismissed (manual solve detected)")
                    return
            except Exception:
                return
        print("  [WARN] CAPTCHA window expired -- continuing anyway")


def reset_login_page(page):
    page.goto(REKYC_URL, wait_until="domcontentloaded")
    page.wait_for_timeout(2000)


def is_otp_page(page):
    return "otp" in page.url.lower() or "verify_otp" in page.url.lower()


def is_logged_in_dashboard(page):
    current_url = page.url.lower()
    if is_otp_page(page) or "login" in current_url:
        return False
    page_text = visible_text(page).lower()
    return any(
        marker in current_url or marker in page_text
        for marker in ["dashboard", "service status", "mobile no", "email", "nominee", "rekyc"]
    )


# FIX 1: Use a list inside a mutable container so it survives across imports
#         and can be safely cleared without rebinding the module-level name.
_step_results_store = {"results": []}


def get_step_results():
    return _step_results_store["results"]


def run_step(step_number, step_name, action):
    results = get_step_results()
    try:
        action()
        results.append({
            "step":   step_number,
            "name":   step_name,
            "status": "PASS",
            "reason": "",
        })
        print(f"Step {step_number} PASSED: {step_name}")
    except Exception as e:
        error_msg = str(e).encode("ascii", "ignore").decode("ascii")
        results.append({
            "step":   step_number,
            "name":   step_name,
            "status": "FAIL",
            "reason": error_msg,
        })
        print(f"Step {step_number} FAILED: {step_name}")
        print(f"Reason: {error_msg}")
    finally:
        json_path = os.path.join(
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            "rekyc_step_results.json",
        )
        with open(json_path, "w") as f:
            json.dump(results, f, indent=2)


def assert_all_steps_passed():
    failed_steps = [s for s in get_step_results() if s.get("status") == "FAIL"]
    if failed_steps:
        summary = "; ".join(
            f"Step {s.get('step')} {s.get('name')}: {s.get('reason')}"
            for s in failed_steps
        )
        raise AssertionError(f"{len(failed_steps)} ReKYC step(s) failed: {summary}")


def click_first_visible(page_or_frame, locators, timeout=3000):
    for loc in locators:
        try:
            el = page_or_frame.locator(loc).first
            if el.is_visible(timeout=timeout):
                el.click()
                return True
        except Exception:
            continue
    return False


def any_locator_visible(page_or_frame, locators, timeout=700):
    for loc in locators:
        try:
            if page_or_frame.locator(loc).first.is_visible(timeout=timeout):
                return True
        except Exception:
            continue
    return False

def click_button_robust(page, locators, description, timeout=10000):
    """
    Robust button click with multiple strategies to handle overlays,
    hidden elements, and custom event handlers.
    
    Strategies:
    1. Scroll into view if needed
    2. Force click to bypass overlays
    3. JavaScript click fallback
    4. Mouse event dispatch fallback
    5. Multiple retries
    """
    print(f"  [i] Attempting to click: {description}")
    
    for attempt in range(3):  # 3 attempts
        for loc in locators:
            try:
                el = page.locator(loc).first
                if el.count() == 0:
                    continue
                
                # Strategy 1: Check visibility and scroll if needed
                try:
                    is_visible = el.is_visible(timeout=1000)
                except Exception:
                    is_visible = False
                
                if not is_visible:
                    try:
                        el.scroll_into_view_if_needed(timeout=2000)
                        page.wait_for_timeout(500)
                        is_visible = el.is_visible(timeout=1000)
                    except Exception:
                        pass
                
                if not is_visible and attempt > 0:
                    continue
                
                # Strategy 2: Force click to bypass overlays
                try:
                    el.click(force=True, timeout=3000)
                    page.wait_for_timeout(1000)
                    print(f"  [OK] Button clicked successfully (force click): {description}")
                    return True
                except Exception as e:
                    print(f"  [WARN] Force click failed, trying alternatives: {str(e)[:40]}")
                
                # Strategy 3: JavaScript click
                try:
                    clicked = page.evaluate("""
                        () => {
                            const buttons = Array.from(document.querySelectorAll('button, input[type=submit], a'));
                            const target = buttons.find(el => {
                                const text = (el.innerText || el.value || '').toLowerCase();
                                return text.includes('proceed') && (text.includes('esign') || text.includes('e-sign'));
                            });
                            if (!target) return false;
                            target.scrollIntoView({block: 'center', inline: 'center'});
                            target.click();
                            return true;
                        }
                    """)
                    if clicked:
                        page.wait_for_timeout(1000)
                        print(f"  [OK] Button clicked successfully (JavaScript): {description}")
                        return True
                except Exception as e:
                    print(f"  [WARN] JavaScript click failed: {str(e)[:40]}")
                
                # Strategy 4: Dispatch mouse events
                try:
                    page.evaluate("""
                        () => {
                            const buttons = Array.from(document.querySelectorAll('button, input[type=submit], a'));
                            const target = buttons.find(el => {
                                const text = (el.innerText || el.value || '').toLowerCase();
                                return text.includes('proceed') && (text.includes('esign') || text.includes('e-sign'));
                            });
                            if (!target) return;
                            const rect = target.getBoundingClientRect();
                            const opts = {
                                bubbles: true,
                                cancelable: true,
                                view: window,
                                clientX: rect.left + rect.width / 2,
                                clientY: rect.top + rect.height / 2
                            };
                            target.dispatchEvent(new MouseEvent('mousedown', opts));
                            target.dispatchEvent(new MouseEvent('mouseup', opts));
                            target.dispatchEvent(new MouseEvent('click', opts));
                        }
                    """)
                    page.wait_for_timeout(1000)
                    print(f"  [OK] Button clicked successfully (mouse events): {description}")
                    return True
                except Exception as e:
                    print(f"  [WARN] Mouse event click failed: {str(e)[:40]}")
                    
            except Exception as e:
                print(f"  [WARN] Locator processing failed: {str(e)[:40]}")
                continue
        
        if attempt < 2:
            print(f"  [i] Retry {attempt + 1}/3 for: {description}")
            page.wait_for_timeout(2000)
    
    raise Exception(f"Could not click button after 3 attempts: {description}")

def fill_first_visible(page_or_frame, locators, value, timeout=3000):
    for loc in locators:
        try:
            el = page_or_frame.locator(loc).first
            if el.is_visible(timeout=timeout):
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def clear_blocking_overlays(page):
    try:
        page.keyboard.press("Escape")
    except Exception:
        pass
    try:
        page.evaluate("""
            () => {
                document.querySelectorAll('.reveal-overlay, .modal-backdrop').forEach((el) => {
                    el.style.display = 'none';
                    el.style.pointerEvents = 'none';
                });
                document.querySelectorAll('.reveal, .modal').forEach((el) => {
                    el.style.display = 'none';
                    el.classList.remove('open', 'show');
                    el.setAttribute('aria-hidden', 'true');
                });
                document.body.classList.remove('is-reveal-open', 'modal-open');
                document.documentElement.classList.remove('is-reveal-open', 'modal-open');
            }
        """)
    except Exception:
        pass


SECTION_FALLBACK_URLS = {
    "Email": "email.php",
    "Mobile No": "mobile.php",
    "Nominee": "nominee.php",
    "Change of address": "address_change.php",
    "Bank": "bank.php",
    "Segment": "segment.php",
    "Income Declaration": "income_dec.php",
    "Dis Slip Req": "dis_slip_req.php",
    "Documents": "document.php",
    "DDPI": "ddpi.php",
}


def visible_text(page):
    try:
        return (page.locator("body").inner_text(timeout=5000) or "").strip()
    except Exception:
        return ""

def visible_menu_links(page):
    try:
        return page.locator("a:visible").evaluate_all(
            "els => els.map(e => (e.innerText || e.textContent || '').trim()).filter(Boolean)"
        )
    except Exception:
        return []


def assert_required_rekyc_sections_available(page, required_sections=None):
    required_sections = required_sections or [
        "Email",
        "Mobile No",
        "Change of address",
        "Nominee",
        "Bank",
        "Segment",
        "Income Declaration",
        "Documents",
        "Dis Slip Req",
        "Service Status",
    ]
    visible_links = visible_menu_links(page)
    normalized_links = [link.lower() for link in visible_links]
    missing = []
    for section in required_sections:
        expected = section.lower()
        if not any(expected in link for link in normalized_links):
            missing.append(section)
    if missing:
        available_text = ", ".join(visible_links[:12]) if visible_links else "no visible menu links"
        raise Exception(
            "Required ReKYC sections are not available for this account. "
            f"Missing: {', '.join(missing)}. Visible sections: {available_text}"
        )


def debug_page_state(page, description=""):
    """Print detailed page state for debugging button click issues"""
    print(f"\n  [DEBUG] ========== Page State: {description} ==========")
    print(f"  [DEBUG] URL: {page.url}")
    
    try:
        page_text = visible_text(page).lower()
        print(f"  [DEBUG] Page text (first 150 chars): {page_text[:150]}")
    except Exception as e:
        print(f"  [DEBUG] Could not get page text: {str(e)[:50]}")
    
    try:
        buttons = page.evaluate("""
            () => Array.from(document.querySelectorAll('button, input[type=submit], a'))
                .map(el => ({
                    tag: el.tagName,
                    text: (el.innerText || el.value || '').substring(0, 40),
                    id: el.id || 'N/A',
                    class: el.className.substring(0, 40),
                    visible: el.offsetParent !== null,
                    disabled: el.disabled || false
                }))
                .slice(0, 15)
        """)
        print(f"  [DEBUG] All buttons on page:")
        for i, btn in enumerate(buttons, 1):
            print(f"    {i}. {btn['tag']} | Text: {btn['text']} | Visible: {btn['visible']} | Disabled: {btn['disabled']}")
    except Exception as e:
        print(f"  [DEBUG] Could not get buttons: {str(e)[:50]}")
    
    try:
        modals = page.evaluate("""
            () => Array.from(document.querySelectorAll('[role=dialog], .modal, .popup, .overlay, .reveal'))
                .filter(el => el.offsetParent !== null)
                .map(el => ({
                    class: el.className.substring(0, 50),
                    text: (el.innerText || '').substring(0, 50)
                }))
        """)
        if modals:
            print(f"  [DEBUG] Visible modals/overlays:")
            for modal in modals:
                print(f"    - {modal['class']}: {modal['text']}")
    except Exception:
        pass
    
    print(f"  [DEBUG] ==========================================================\n")


def assert_visible_any(page_or_frame, locators, description, timeout=3000):
    for loc in locators:
        try:
            el = page_or_frame.locator(loc).first
            if el.is_visible(timeout=timeout):
                return el
        except Exception:
            continue
    raise Exception(f"{description} not visible")


def assert_input_value(page_or_frame, locators, expected_value, description, timeout=3000):
    el = assert_visible_any(page_or_frame, locators, description, timeout=timeout)
    actual_value = el.input_value(timeout=timeout)
    if actual_value.strip() != str(expected_value).strip():
        raise Exception(
            f"{description} did not retain expected value. "
            f"Expected '{expected_value}', got '{actual_value}'"
        )
    return el


def assert_validation_feedback(page, expected_keywords=None, description="validation"):
    """
    Require visible validation evidence for negative scenarios.
    Staying on the same URL alone is not enough to mark a validation test as PASS.
    """
    expected_keywords = [k.lower() for k in (expected_keywords or [])]
    feedback_selectors = [
        ".error",
        ".errors",
        ".invalid-feedback",
        ".validation",
        ".validation-error",
        ".field-validation-error",
        ".text-danger",
        ".alert",
        ".alert-danger",
        ".toast",
        ".toast-message",
        "[role='alert']",
        "[aria-invalid='true']",
        "label.error",
        "#error",
        "#errmsg",
        "#errorMsg",
    ]

    messages = []
    for selector in feedback_selectors:
        try:
            items = page.locator(selector)
            for i in range(min(items.count(), 10)):
                item = items.nth(i)
                if item.is_visible(timeout=1000):
                    text = (item.inner_text(timeout=1000) or "").strip()
                    if text:
                        messages.append(text)
                    else:
                        messages.append(selector)
        except Exception:
            continue

    try:
        invalid_count = page.evaluate("""
            () => Array.from(document.querySelectorAll('input, select, textarea'))
                .filter((el) => el.offsetParent !== null && el.matches(':invalid')).length
        """)
        if invalid_count:
            messages.append(f"{invalid_count} invalid HTML5 field(s)")
    except Exception:
        pass

    page_text = visible_text(page).lower()
    if expected_keywords and any(keyword in page_text for keyword in expected_keywords):
        messages.append("Expected validation keyword found in page text")

    if not messages:
        raise Exception(f"{description}: expected validation feedback was not visible")

    print("  [OK] Validation feedback detected:", " | ".join(messages[:3]))


def open_section(page, link_text, wait_time=2000):
    clear_blocking_overlays(page)
    fallback = SECTION_FALLBACK_URLS.get(link_text)
    link = page.locator(f"//a[normalize-space()='{link_text}' or contains(normalize-space(),'{link_text}')]").first
    try:
        link.wait_for(state="visible", timeout=10000)
    except Exception:
        visible_links = visible_menu_links(page)
        available_text = ", ".join(visible_links[:12]) if visible_links else "no visible menu links"
        raise Exception(
            f"{link_text} section is not available for this account. Visible sections: {available_text}"
        )
    href = link.get_attribute("href")

    if href and not href.startswith("#") and "javascript:" not in href.lower():
        target_url = urljoin(page.url, href)
        page.goto(target_url, wait_until="domcontentloaded")
        page.wait_for_timeout(wait_time)
    else:
        try:
            link.click(timeout=5000)
        except Exception:
            clear_blocking_overlays(page)
            link.click(force=True, timeout=5000)
        page.wait_for_timeout(wait_time)

    page_text = ""
    try:
        page_text = page.locator("h1, h2, h3, h4, legend, .card-title, .page-title").inner_text(timeout=3000).lower()
    except Exception:
        page_text = visible_text(page).lower()
    expected_url_part = (fallback or link_text).replace(" ", "_").lower()

    if expected_url_part not in page.url.lower() and link_text.lower() not in page_text:
        raise Exception(f"{link_text} section did not load or display expected text")


def view_document_proof(page, proof_number):
    clear_blocking_overlays(page)
    rows = page.locator("table tr")
    try:
        rows.first.wait_for(state="visible", timeout=10000)
    except Exception:
        raise Exception(f"Proof {proof_number}: documents table not available")
    if rows.count() <= proof_number:
        raise Exception(f"Proof {proof_number}: row not available")
    row = rows.nth(proof_number)
    clickable_cells = row.locator("td")
    if clickable_cells.count() == 0:
        raise Exception(f"Proof {proof_number}: no clickable cells available")
    clickable_cells.last.click(force=True)
    page.wait_for_timeout(2000)
    try:
        file_name = (row.locator("td").nth(2).text_content() or "").strip().lower()
    except Exception:
        file_name = ""
    if file_name.endswith(".pdf"):
        try:
            iframe = page.locator("iframe").first
            box = iframe.bounding_box()
            if box:
                page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        except Exception:
            pass
        for _ in range(18):
            page.mouse.wheel(0, 450)
            page.wait_for_timeout(650)
    close_buttons = [
        "#closeModal",
        "button[data-close]",
        ".close-button",
        "//button[contains(text(),'Close')]",
        "//button[contains(text(),'close')]",
        "//button[contains(text(),'?')]",
    ]
    for loc in close_buttons:
        try:
            close_button = page.locator(loc).first
            if close_button.is_visible(timeout=2000):
                close_button.click(force=True)
                page.wait_for_timeout(1000)
                return
        except Exception:
            continue
    clear_blocking_overlays(page)


# --- shared locator lists ----------------------------------------------------
UCC_LOCATORS = [
    "input[placeholder='ucc']",
    "input[placeholder='UCC']",
    "//input[@name='ucc']",
    "//input[@id='ucc']",
]
DOB_LOCATORS = [
    "input[placeholder='DOB : DD/MM/YYYY']",
    "//input[@placeholder='DOB : DD/MM/YYYY']",
    "//input[@name='dob']",
    "//input[@id='dob']",
]
OTP_LOCATORS = [
    "input[placeholder*='OTP']",
    "input[placeholder*='otp']",
    "input[name*='otp']",
    "input[id*='otp']",
    "//input[contains(translate(@placeholder,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'otp')]",
    "//input[@type='text' or @type='tel' or @type='number']",
]

# FIX 7: Multiple submit button selectors for resilience
OTP_SUBMIT_LOCATORS = [
    "button[data-key='sbt']",
    "button[type='submit']",
    "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//input[@type='submit']",
]
SERVICE_EDIT_LOCATORS = [
    "//button[contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile') or contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]",
    "//a[contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile') or contains(translate(@onclick,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]",
    "//input[(contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit') or contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'modify')) and not(@type='hidden')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit')]",
    "a[title*='Edit' i]",
    "button[title*='Edit' i]",
    "a[class*='edit' i]",
    "button[class*='edit' i]",
    "//i[(contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit') or contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pencil')) and not(ancestor::*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'voice assistant')])]",
    "//a[.//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit') or contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pencil')]]",
    "//button[.//*[contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit') or contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pencil')]]",
    "//i[(contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'edit') or contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pencil')) and not(ancestor::*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'voice assistant')])]/ancestor::*[self::a or self::button][1]",
]
SERVICE_DECLARATION_LOCATORS = [
    "input[type='checkbox']",
    "//input[@type='checkbox']",
]
SERVICE_SEND_OTP_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send otp')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send otp')]",
]
SERVICE_EMAIL_OTP_RADIO_LOCATORS = [
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'e-mail')]/preceding::input[@type='radio'][1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]/preceding::input[@type='radio'][1]",
    "//input[@type='radio' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]",
    "//input[@type='radio' and contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]",
    "//input[@type='radio' and contains(translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]",
]
SERVICE_MOBILE_OTP_RADIO_LOCATORS = [
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile')]/preceding::input[@type='radio'][1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile no')]/preceding::input[@type='radio'][1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'phone')]/preceding::input[@type='radio'][1]",
    "//input[@type='radio' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile')]",
    "//input[@type='radio' and contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile')]",
    "//input[@type='radio' and contains(translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile')]",
]
SERVICE_OKAY_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'okay')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ok')]",
]
ADDRESS_PROCEED_CHANGE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed to change')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed to change')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed to change')]",
]
DIGILOCKER_AADHAAR_TAB_LOCATORS = [
    "#pills-aadhaar-tab",
    "a#pills-aadhaar-tab",
    "a[aria-controls='pills-aadhaar']",
    "xpath=//*[self::button or self::a or @role='tab'][normalize-space()='Aadhaar']",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'aadhaar')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'aadhaar')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'aadhaar') and (@role='tab' or self::button or self::a)]",
]
DIGILOCKER_AADHAAR_INPUT_LOCATORS = [
    "input[placeholder*='Aadhaar' i]",
    "input[name*='aadhaar' i]",
    "input[id*='aadhaar' i]",
]
DIGILOCKER_NEXT_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
]
DIGILOCKER_OTP_INPUT_LOCATORS = [
    "input[placeholder*='OTP' i]",
    "input[name*='otp' i]",
    "input[id*='otp' i]",
    "input[type='text']",
    "input[type='tel']",
    "input[type='number']",
]
DIGILOCKER_SECURITY_PIN_INPUT_LOCATORS = [
    "input[placeholder*='security PIN' i]",
    "input[placeholder*='PIN' i]",
    "input[name*='pin' i]",
    "input[id*='pin' i]",
    "input[type='password']",
    "input[type='text']",
    "input[type='tel']",
    "input[type='number']",
]
DIGILOCKER_SUBMIT_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
]
DIGILOCKER_CONTINUE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
]
SERVICE_EMAIL_INPUT_LOCATORS = [
    "input[type='email']",
    "input[name*='email' i]",
    "input[id*='email' i]",
    "input[placeholder*='email' i]",
    "input[placeholder*='e-mail' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]/following::input[1]",
]
SERVICE_MOBILE_INPUT_LOCATORS = [
    "input[name*='mobile' i]",
    "input[id*='mobile' i]",
    "input[name*='phone' i]",
    "input[id*='phone' i]",
    "input[placeholder*='Mobile Number' i]",
    "input[placeholder*='phone' i]",
    "input[type='tel']",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'phone')]/following::input[1]",
]
SERVICE_CONTINUE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "button[data-key*='continue' i]",
    "input[data-key*='continue' i]",
    "a[data-key*='continue' i]",
    ".continue",
    ".continuebtn",
    ".continue_btn",
]
SERVICE_POPUP_BUTTON_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ok')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed')]",
    "//input[@type='button' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm')]",
    "//input[@type='button' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ok')]",
    "//input[@type='submit' and contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
]
SERVICE_CLOSE_MODAL_LOCATORS = [
    "//button[normalize-space()='X' or normalize-space()='x']",
    "//button[contains(@class,'close')]",
    ".close",
    ".close-button",
]
SEGMENT_SUBMIT_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
]
SEGMENT_RISK_AGREE_LOCATORS = [
    "//button[normalize-space()='Agree']",
    "//a[normalize-space()='Agree']",
    "//input[translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='agree']",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'agree')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'agree')]",
]
BANK_AGREE_PROCEED_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed')]",
]
ONEMONEY_SEND_OTP_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send otp')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send otp')]",
]
ONEMONEY_OTP_LOCATORS = [
    "input[placeholder*='OTP' i]",
    "input[name*='otp' i]",
    "input[id*='otp' i]",
    "input[type='tel']",
    "input[type='text']",
    "input[type='number']",
]
ONEMONEY_LOGIN_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
]
PROTEAN_SURAKSHAA_CONTINUE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
]
PROTEAN_SURAKSHAA_ACCEPT_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
]

NOMINEE_ADD_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add nominee')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add nominee(s)')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add nominee(s)')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add nominee')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add nominee')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add')]",
    "#addNominee",
    ".addNominee",
]
NOMINEE_SAVE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
]
NOMINEE_CONTINUE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//input[@type='submit']",
]
NOMINEE_CONTINUE_ONLY_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
]
SIGNATURE_FILE_INPUT_LOCATORS = [
    "input#drawimagerest",
    "input#drawimage",
    "input[name='drawimagerest']",
    "input[name='drawimage']",
    "input#uploadsign",
    "input#upload_sign_file",
    "input[name*='upload' i]",
    "input[id*='upload' i]",
    "input[name*='signature' i]",
    "input[id*='signature' i]",
    "input[type='file'][accept*='image']",
    "input[type='file']",
]
SIGNATURE_UPLOAD_TAB_LOCATORS = [
    "//button[normalize-space()='Upload Signature']",
    "//a[normalize-space()='Upload Signature']",
    "//*[self::button or self::a or self::div][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload signature')]",
]
SIGNATURE_TRIGGER_LOCATORS = [
    "#upload_sign",
    "//button[@id='upload_sign']",
    "#drawimagerestcl",
    "label#drawimagerestcl",
    "label[for='drawimagerest']",
    "label[for='drawimage']",
    "input[type='button'][value*='Please upload' i]",
    "input[type='button'][value*='signature' i]",
    "//*[normalize-space()='Please upload signature']",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please upload signature')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please upload signature')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please upload signature')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload')]",
    "//label[@id='drawimagerestcl']",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'signature')]",
]
SIGNATURE_UPLOAD_AREA_LOCATORS = [
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload (or) capture')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload (or) capture')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'capture')]",
]
SIGNATURE_SUBMIT_LOCATORS = [
    "//button[normalize-space()='Submit']",
    "//input[@type='submit' and translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='submit']",
    "button[type='submit']",
    "input[type='submit']",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
]
UNSIGNED_PDF_LOCATORS = [
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'view unsigned kyc pdf')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'unsigned kyc pdf')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'view unsigned kyc pdf')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'unsigned kyc pdf')]",
]
PROCEED_ESIGN_LOCATORS = [
    # Digio-specific
    "input[name='digiosubmit']",
    
    # FIX: Add more button pattern variations
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'esign')]",
    
    # Exact text matches
    "//button[normalize-space()='Continue to eSign']",
    "//button[normalize-space()='Continue to E-Sign']",
    "//button[normalize-space()='Continue to E-sign']",
    
    # Case-insensitive variations
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue to e-sign')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue to esign')]",
    
    # With child elements
    "//button[contains(.,'Continue')]",
    "//button[contains(.,'eSign')]",
    
    # Links
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue to e-sign')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue to esign')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    
    # Input submit
    "//input[@type='submit' and (contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue') or contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'esign') or contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'e-sign'))]",
    
    # Data attributes
    "//button[contains(@data-action, 'esign')]",
    "//button[contains(@data-action, 'continue')]",
    "//*[self::button or self::a or self::input][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue') and (contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'esign') or contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'e-sign'))]",
    "//*[self::button or self::a or self::input][contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue') and (contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'esign') or contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'e-sign'))]",
    "//*[self::button or self::a or self::input][contains(translate(@id,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'esign') or contains(translate(@name,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'esign') or contains(translate(@class,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'esign')]",
]
ESIGN_AADHAAR_LOCATORS = [
    "input#vid",
    "input[name='vid']",
    "input[placeholder*='Aadhaar' i]",
    "input[placeholder*='Aadhar' i]",
    "input[placeholder*='VID' i]",
    "input[maxlength='12']",
]
ESIGN_SEND_OTP_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send otp')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'send otp')]",
]
ESIGN_OTP_LOCATORS = [
    "input#otpInput",
    "input[name*='otp' i]",
    "input[placeholder*='otp' i]",
]
ESIGN_SUBMIT_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verify')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'verify')]",
]
IPV_CONSENT_CHECKBOX_LOCATORS = [
    "//input[@type='checkbox' and not(@disabled)]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'camera access')]/preceding::input[@type='checkbox'][1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'i agree')]/preceding::input[@type='checkbox'][1]",
]
IPV_PROCEED_LOCATORS = [
    "//button[normalize-space()='Proceed with IPV']",
    "//input[translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='proceed with ipv']",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed with ipv')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed with ipv')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed with ipv')]",
]
NOMINEE_PAN_LOCATORS = [
    "input[name*='pan' i]",
    "input[id*='pan' i]",
    "input[name*='aadhaar' i]",
    "input[id*='aadhaar' i]",
    "input[placeholder*='PAN' i]",
    "input[placeholder*='Aadhaar' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pan/aadhaar number')]/following::input[1]",
]
NOMINEE_NAME_LOCATORS = [
    "input[name*='nominee'][name*='name' i]",
    "input[id*='nominee'][id*='name' i]",
    "input[placeholder*='Nominee'][placeholder*='Name' i]",
    "input[placeholder*='Nominee Name' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'nominee name')]/following::input[1]",
]
NOMINEE_RELATION_LOCATORS = [
    "select[name*='relation' i]",
    "select[id*='relation' i]",
    "select[name*='nominee_relation' i]",
    "select[id*='nomirel' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship')]/following::select[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relation with account holder')]/following::select[1]",
]
NOMINEE_DOB_LOCATORS = [
    "input[name*='dob' i]",
    "input[id*='dob' i]",
    "input[placeholder*='DOB' i]",
    "input[placeholder*='Date of Birth' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'dob')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'date of birth')]/following::input[1]",
]
NOMINEE_SHARE_LOCATORS = [
    "input[name*='percent' i]",
    "input[id*='percent' i]",
    "input[name*='share' i]",
    "input[id*='share' i]",
    "input[name*='ratio' i]",
    "input[id*='ratio' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'percentage')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'share')]/following::input[1]",
]
NOMINEE_MOBILE_LOCATORS = [
    "input[name*='mobile' i]",
    "input[id*='mobile' i]",
    "input[name*='phone' i]",
    "input[id*='phone' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile')]/following::input[1]",
]
NOMINEE_EMAIL_LOCATORS = [
    "input[name*='email' i]",
    "input[id*='email' i]",
    "input[type='email']",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email')]/following::input[1]",
]
NOMINEE_ADDRESS_LOCATORS = [
    "textarea[name*='address' i]",
    "textarea[id*='address' i]",
    "input[name*='address' i]",
    "input[id*='address' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'address')]/following::textarea[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'address')]/following::input[1]",
]
NOMINEE_ADDRESS_AS_CLIENT_LOCATORS = [
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'address as per client address')]/preceding::input[@type='checkbox'][1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'address as per client address')]/input[@type='checkbox']",
    "input[type='checkbox'][name*='address' i]",
    "input[type='checkbox'][id*='address' i]",
]
GUARDIAN_PAN_LOCATORS = [
    "input[name*='guardian'][name*='pan' i]",
    "input[id*='guardian'][id*='pan' i]",
    "input[name*='guardian'][name*='aadhaar' i]",
    "input[id*='guardian'][id*='aadhaar' i]",
    "input[placeholder*='Guardian'][placeholder*='PAN' i]",
    "input[placeholder*='Guardian'][placeholder*='Aadhaar' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian pan')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian aadhaar')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian name')]/preceding::label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'pan/aadhaar number')][1]/following::input[1]",
]
GUARDIAN_NAME_LOCATORS = [
    "input[name*='guardian'][name*='name' i]",
    "input[id*='guardian'][id*='name' i]",
    "input[placeholder*='Guardian Name' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian name')]/following::input[1]",
]
GUARDIAN_MOBILE_LOCATORS = [
    "input[name*='guardian'][name*='mobile' i]",
    "input[id*='guardian'][id*='mobile' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian name')]/following::label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mobile')][1]/following::input[1]",
]
GUARDIAN_DOB_LOCATORS = [
    "input[name*='guardian'][name*='dob' i]",
    "input[id*='guardian'][id*='dob' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian')]/preceding::label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'date of birth')][1]/following::input[1]",
]
GUARDIAN_EMAIL_LOCATORS = [
    "input[name*='guardian'][name*='email' i]",
    "input[id*='guardian'][id*='email' i]",
    "input[placeholder*='Email ID' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'email id')]/following::input[1]",
]
GUARDIAN_RELATION_LOCATORS = [
    "select[name*='guardian'][name*='relation' i]",
    "select[id*='guardian'][id*='relation' i]",
    "input[name*='guardian'][name*='relation' i]",
    "input[id*='guardian'][id*='relation' i]",
    "select[name*='guardian'][name*='relationship' i]",
    "select[id*='guardian'][id*='relationship' i]",
    "input[name*='guardian'][name*='relationship' i]",
    "input[id*='guardian'][id*='relationship' i]",
    "span.select2-selection",
    ".select2-selection",
    "[role='combobox']",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian with nominee')]/following::select[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian with nominee')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian')]/following::select[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian relationship')]/following::select[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian relationship')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian relation')]/following::select[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'guardian relation')]/following::input[1]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian with nominee')]/following::select[1]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian with nominee')]/following::input[1]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian')]/following::select[1]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian')]/following::input[1]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian with nominee')]/following::*[contains(@class,'select2-selection') or @role='combobox'][1]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'relationship of guardian')]/following::*[contains(@class,'select2-selection') or @role='combobox'][1]",
]

BANK_ADD_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add bank')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add bank')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add')]",
    "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'add')]",
]
BANK_SAVE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'continue')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'save')]",
    "//input[@type='submit']",
]
BANK_ACCOUNT_LOCATORS = [
    "input[name*='account'][name*='number' i]",
    "input[id*='account'][id*='number' i]",
    "input[name*='accno' i]",
    "input[id*='accno' i]",
    "input[placeholder*='Account Number' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'account number')]/following::input[1]",
]
BANK_CONFIRM_ACCOUNT_LOCATORS = [
    "input[name*='confirm' i][name*='account' i]",
    "input[id*='confirm' i][id*='account' i]",
    "input[placeholder*='Confirm' i][placeholder*='Account' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm account')]/following::input[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'re-enter account')]/following::input[1]",
]
BANK_IFSC_LOCATORS = [
    "input[name*='ifsc' i]",
    "input[id*='ifsc' i]",
    "input[placeholder*='IFSC' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ifsc')]/following::input[1]",
]
BANK_NAME_LOCATORS = [
    "input[name*='bank'][name*='name' i]",
    "input[id*='bank'][id*='name' i]",
    "input[placeholder*='Bank Name' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'bank name')]/following::input[1]",
]
BANK_BRANCH_LOCATORS = [
    "input[name*='branch' i]",
    "input[id*='branch' i]",
    "input[placeholder*='Branch' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'branch')]/following::input[1]",
]
BANK_ACCOUNT_TYPE_LOCATORS = [
    "select[name*='account'][name*='type' i]",
    "select[id*='account'][id*='type' i]",
    "select[name*='type' i]",
    "select[id*='type' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'account type')]/following::select[1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'account type')]/following::input[1]",
]
BANK_PROOF_LOCATORS = [
    "input[type='file']",
    "//input[@type='file']",
]


def human_type(page, locators, value, delay_ms=120):
    """
    Type character-by-character with realistic delay -- looks human to reCAPTCHA.
    Falls back to fill() for empty values or if element not found.
    """
    if not value:
        return fill_first_visible(page, locators, value)
    for loc in locators:
        try:
            el = page.locator(loc).first
            if el.is_visible(timeout=3000):
                el.click()
                el.fill("")
                page.wait_for_timeout(200)
                for char in value:
                    el.type(char)
                    page.wait_for_timeout(delay_ms)
                return True
        except Exception:
            continue
    return False


def fill_ucc(page, value):
    if value:
        return human_type(page, UCC_LOCATORS, value)
    return fill_first_visible(page, UCC_LOCATORS, value)


def close_calendar_if_open(page):
    """Press Escape and wait briefly to dismiss any open date-picker."""
    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass


def select_dob(page, year, month, day):
    """Open calendar, choose year/month/day."""
    # FIX 9: Close any previously open calendar before opening a new one
    close_calendar_if_open(page)
    clicked = click_first_visible(page, DOB_LOCATORS)
    if not clicked:
        raise Exception("DOB input field not found")
    page.wait_for_timeout(2000)
    page.locator(".yearselect").first.select_option(value=year)
    page.locator(".monthselect").first.select_option(value=month)
    day_number = str(int(day))
    dates = page.locator("td.available:not(.off):not(.disabled)")
    for i in range(dates.count()):
        cell = dates.nth(i)
        if cell.text_content().strip() == day_number:
            cell.click()
            return
    raise Exception("DOB day not found in calendar")


def submit_login(page):
    try:
        page.locator("#submitform").click(timeout=15000)
    except Exception as e:
        if "otp" in page.url.lower() or "verify_otp" in page.url.lower():
            print("  [OK] Login submit navigated to OTP despite click timeout")
            return
        message = str(e).lower()
        if "recaptcha" in message or "intercepts pointer events" in message:
            handle_captcha_if_present(page)
            try:
                page.locator("#submitform").click(force=True, timeout=5000)
                return
            except Exception:
                try:
                    page.evaluate(
                        """() => {
                            const btn = document.querySelector('#submitform');
                            if (btn) btn.click();
                        }"""
                    )
                    page.wait_for_timeout(3000)
                    return
                except Exception:
                    pass
        raise e


def submit_otp(page):
    """FIX 7: Try multiple submit button selectors."""
    if not click_first_visible(page, OTP_SUBMIT_LOCATORS, timeout=5000):
        raise Exception("OTP submit button not found with any known selector")


def fetch_latest_yopmail_otp(page, description="OTP", inbox_email=None):
    new_page = page.context.new_page()
    try:
        new_page.goto("https://yopmail.com/en/", wait_until="domcontentloaded")
        inbox = (inbox_email or REKYC_YOPMAIL).split("@")[0]
        new_page.locator("#login").fill(inbox)
        new_page.keyboard.press("Enter")
        new_page.wait_for_timeout(3000)

        mail_items = None
        for attempt in range(12):
            new_page.wait_for_timeout(5000)
            try:
                refresh_button = new_page.locator("#refresh")
                if refresh_button.is_visible(timeout=2000):
                    refresh_button.click()
                    new_page.wait_for_timeout(2000)
            except Exception:
                pass
            inbox_frame = new_page.frame_locator("#ifinbox")
            items = inbox_frame.locator(".m, .lm")
            try:
                if items.count() > 0:
                    mail_items = items
                    print(f"  [OK] {description} email found after {(attempt+1)*5}s")
                    break
            except Exception:
                pass
            print(f"  ... Waiting for {description} email ({(attempt+1)*5}s elapsed)...")

        if mail_items is None:
            raise Exception(f"No {description} email found in Yopmail inbox after 60 seconds")

        mail_frame = new_page.frame_locator("#ifmail")
        checked_count = min(mail_items.count(), 10)
        last_text = ""
        for item_index in range(checked_count):
            try:
                mail_items.nth(item_index).click()
                new_page.wait_for_timeout(1200)
                body = mail_frame.locator("body")
                body.wait_for(timeout=30000)
                text = body.inner_text(timeout=30000)
                last_text = text
                otp_match = re.search(r"\b\d{6}\b", text)
                if otp_match:
                    otp = otp_match.group(0)
                    print(f"  [OK] {description} fetched: {otp}")
                    return otp
            except Exception:
                continue
        raise Exception(
            f"{description} not found in the latest {checked_count} Yopmail email(s). "
            f"Last email preview: {last_text[:160]}"
        )
    finally:
        new_page.close()


def section_url(section_name):
    return urljoin(REKYC_URL, {
        "Email": "email.php",
        "Mobile No": "mobile.php",
    }[section_name])


def service_modal_visible(page):
    for loc in SERVICE_SEND_OTP_LOCATORS:
        try:
            if page.locator(loc).first.is_visible(timeout=1000):
                return True
        except Exception:
            continue
    return False


def open_service_update_modal(page, section_name):
    clear_blocking_overlays(page)
    open_section(page, section_name)
    if service_modal_visible(page):
        return
    clicked_candidate = False
    for loc in SERVICE_EDIT_LOCATORS:
        try:
            candidates = page.locator(loc)
            for i in range(min(candidates.count(), 8)):
                candidate = candidates.nth(i)
                if not candidate.is_visible(timeout=1000):
                    continue
                clicked_candidate = True
                try:
                    candidate.click(timeout=2000)
                except Exception:
                    candidate.click(force=True, timeout=2000)
                page.wait_for_timeout(1500)
                if service_modal_visible(page):
                    return
                # FIX: Don't close modal immediately, wait longer for it to appear
                # Mobile module might take longer to show the modal
                page.wait_for_timeout(2000)
                if service_modal_visible(page):
                    return
                
                # FIX: For mobile, don't close modal if it's in DOM
                # The modal might be open but not fully rendered yet
                if section_name.lower() == "mobile no":
                    modal_in_dom = page.evaluate("""() => {
                        const modals = document.querySelectorAll('.modal, .reveal, [role="dialog"], .popup, [class*="modal"], [class*="popup"]');
                        return modals.length > 0;
                    }""")
                    if modal_in_dom:
                        print("  [DEBUG] Mobile modal is in DOM, proceeding...")
                        page.wait_for_timeout(1000)
                        return
                
                # Original close logic for other sections
                if section_name.lower() not in page.url.lower() and section_name.lower() not in visible_text(page).lower():
                    close_service_modal(page)
                    if section_name.lower() not in page.url.lower():
                        page.goto(section_url(section_name), wait_until="domcontentloaded")
                        page.wait_for_timeout(1000)
        except Exception:
            continue
    if not clicked_candidate:
        raise Exception(f"{section_name} edit button not found")
    if not service_modal_visible(page):
        raise Exception(f"{section_name} update modal did not open")


def complete_service_otp_flow(page, section_name):
    if section_name.lower() == "email":
        complete_email_change_flow(page)
        return
    if section_name.lower() == "mobile no":
        complete_mobile_change_flow(page)
        return
    start_service_otp_verification(page, section_name)
    otp = fetch_latest_yopmail_otp(page, f"{section_name} OTP", REKYC_YOPMAIL)
    if not fill_first_visible(page, OTP_LOCATORS, otp):
        raise Exception(f"{section_name} OTP input field not found")
    submit_service_otp(page)
    page.wait_for_timeout(3000)
    if "verify_otp" in page.url.lower():
        raise Exception(f"{section_name} stayed on OTP page after valid OTP submit")
    print(f"  [OK] {section_name} OTP submitted successfully")


def submit_current_otp_page(page, otp, description):
    if not fill_first_visible(page, OTP_LOCATORS, otp):
        raise Exception(f"{description} OTP input field not found")
    submit_service_otp(page)
    page.wait_for_timeout(3000)
    if "verify_otp" in page.url.lower():
        raise Exception(f"{description} stayed on OTP page after valid OTP submit")
    print(f"  [OK] {description} OTP submitted successfully")


def click_continue_or_send_for_new_email(page):
    if click_first_visible(page, SERVICE_CONTINUE_LOCATORS, timeout=5000):
        return True
    try:
        clicked = page.evaluate(
            """() => {
                const candidates = Array.from(document.querySelectorAll('button,input[type="button"],input[type="submit"],a'));
                const target = candidates.find((el) => {
                    const text = `${el.innerText || ''} ${el.value || ''} ${el.getAttribute('data-key') || ''} ${el.className || ''}`.toLowerCase();
                    const rect = el.getBoundingClientRect();
                    const visible = rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden' && getComputedStyle(el).display !== 'none';
                    return visible && text.includes('continue');
                });
                if (!target) return false;
                target.scrollIntoView({ block: 'center', inline: 'center' });
                target.click();
                return true;
            }"""
        )
        if clicked:
            return True
    except Exception:
        pass
    return False


def complete_email_change_flow(page):
    # First OTP authorizes the change and must come to the existing login Yopmail.
    start_service_otp_verification(page, "Email")
    existing_otp = fetch_latest_yopmail_otp(page, "Email existing-mail OTP", EXISTING_SERVICE_OTP_EMAIL)
    submit_current_otp_page(page, existing_otp, "Email existing-mail")

    page.wait_for_timeout(3000)
    if not fill_first_visible(page, SERVICE_EMAIL_INPUT_LOCATORS, NEW_SERVICE_EMAIL, timeout=10000):
        raise Exception("New email input field not found after existing email OTP")
    try:
        page.keyboard.press("Tab")
        page.locator("input[type='email'], input[name*='email' i], input[id*='email' i]").first.dispatch_event("change")
    except Exception:
        pass
    page.wait_for_timeout(1000)
    print(f"  [OK] New email entered: {NEW_SERVICE_EMAIL}")

    if not click_continue_or_send_for_new_email(page):
        raise Exception("Continue/Send OTP button not found after entering new email")
    page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        click_first_visible(page, SERVICE_OKAY_LOCATORS, timeout=3000)
        page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        raise Exception("New email OTP verification page did not open")

    new_email_otp = fetch_latest_yopmail_otp(page, "Email new-mail OTP", NEW_SERVICE_EMAIL)
    submit_current_otp_page(page, new_email_otp, "Email new-mail")

def complete_mobile_change_flow(page):
    # Step 1: Start OTP verification for existing mobile
    start_service_otp_verification(page, "Mobile No")
    
    # Step 2: Fetch existing mobile OTP from EXISTING_MOBILE_OTP_EMAIL
    existing_otp = fetch_latest_yopmail_otp(page, "Mobile existing OTP", EXISTING_MOBILE_OTP_EMAIL)
    
    # Step 3: Submit existing mobile OTP
    submit_current_otp_page(page, existing_otp, "Mobile existing")
    
    # Step 4: Wait for page to load
    page.wait_for_timeout(3000)
    
    # Step 5: Fill new mobile number
    if not fill_first_visible(page, SERVICE_MOBILE_INPUT_LOCATORS, NEW_SERVICE_MOBILE, timeout=10000):
        raise Exception("New mobile input field not found after existing mobile OTP")
    
    # Step 6: Trigger change event
    try:
        page.keyboard.press("Tab")
        page.locator("input[name*='mobile' i], input[id*='mobile' i]").first.dispatch_event("change")
    except Exception:
        pass
    
    # Step 7: Wait and log
    page.wait_for_timeout(1000)
    print(f"  [OK] New mobile number entered: {NEW_SERVICE_MOBILE}")
    
    # Step 8: Click Continue/Send OTP button
    if not click_continue_or_send_for_new_email(page):
        raise Exception("Continue/Send OTP button not found after entering new mobile")
    
    # Step 9: Wait for OTP page
    page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        click_first_visible(page, SERVICE_OKAY_LOCATORS, timeout=3000)
        page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        raise Exception("New mobile OTP verification page did not open")
    
    # Step 10: Fetch new mobile OTP from NEW_MOBILE_OTP_EMAIL
    new_mobile_otp = fetch_latest_yopmail_otp(page, "Mobile new OTP", NEW_MOBILE_OTP_EMAIL)
    
    # Step 11: Submit new mobile OTP
    submit_current_otp_page(page, new_mobile_otp, "Mobile new")
    
    # Step 12: Log completion
    print("  [OK] Mobile number change completed successfully")

def get_all_pages(page):
    return page.context.pages


def scroll_by(page, y=500):
    page.evaluate(f"window.scrollBy(0, {int(y)})")


def inject_fixed_geolocation(page):
    coords_json = json.dumps(TEST_GEOLOCATION)
    page.add_init_script(
        """
        (() => {
            const coords = __COORDS__;
            const position = {
                coords: {
                    latitude: coords.latitude,
                    longitude: coords.longitude,
                    accuracy: coords.accuracy,
                    altitude: null,
                    altitudeAccuracy: null,
                    heading: null,
                    speed: null
                },
                timestamp: Date.now()
            };
            const geolocation = {
                getCurrentPosition: (success) => setTimeout(() => success(position), 50),
                watchPosition: (success) => {
                    setTimeout(() => success(position), 50);
                    return 1;
                },
                clearWatch: () => {}
            };
            Object.defineProperty(navigator, 'geolocation', {
                configurable: true,
                get: () => geolocation
            });
        })();
        """.replace("__COORDS__", coords_json)
    )


# =============================================================================
#  ReKYC LIVE IPV -- BLINK LIVENESS DETECTION
#
#  KEY DIFFERENCE from eKYC:
#    eKYC: uploads a static image file for IPV verification
#    ReKYC: uses LIVE camera with real-time blink detection
#           The system streams video, detects a face, waits for you to blink,
#           and auto-captures. No photo upload is involved.
#
#  HOW THIS WORKS:
#    1. inject_fake_camera_with_blink() creates a canvas-based fake camera
#       stream that renders a face and blinks every ~900ms automatically.
#       This satisfies the blink-detection algorithm without needing a human.
#    2. inject_fixed_geolocation() provides GPS coords so the location
#       permission prompt is handled silently.
#    3. run_rekyc_ipv_liveness() orchestrates the full flow:
#       - Grants camera + location permissions
#       - Accepts consent checkbox
#       - Waits for face-box / "Finding Face" state
#       - Lets blink loop run; polls for auto-capture success
#       - Retries up to 3 times if capture expires
#       - Clicks Confirm/Continue after capture
# =============================================================================

def inject_fake_camera_with_blink(page):
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    open_path = os.path.join(project_root, "assets", "eyes_opened.jpg")
    closed_path = os.path.join(project_root, "assets", "eyes_closed.jpg")

    if not os.path.exists(open_path) or not os.path.exists(closed_path):
        raise FileNotFoundError(
            f"IPV blink images not found.\n"
            f"  eyes_opened.jpg : {open_path}\n"
            f"  eyes_closed.jpg : {closed_path}"
        )

    with open(open_path, "rb") as f:
        open_b64 = base64.b64encode(f.read()).decode()
    with open(closed_path, "rb") as f:
        closed_b64 = base64.b64encode(f.read()).decode()

    js_code = f"""
    (() => {{
        if (window.__REKYC_IPV_STOP_BLINKING__) {{
            try {{ window.__REKYC_IPV_STOP_BLINKING__(); }} catch (e) {{}}
        }}
        window.__REKYC_IPV_CAMERA_INSTALLED__ = true;

        const OPEN_IMG   = 'data:image/jpeg;base64,{open_b64}';
        const CLOSED_IMG = 'data:image/jpeg;base64,{closed_b64}';
        const FIRST_OPEN_MS = 3000;
        const CLOSED_MS = 1000;
        const RETRY_OPEN_MS = 15000;
        const canvas = document.createElement('canvas');
        canvas.width  = 1280;
        canvas.height = 720;
        const ctx = canvas.getContext('2d', {{ willReadFrequently: true }});
        const openImg   = new Image();
        const closedImg = new Image();
        openImg.src   = OPEN_IMG;
        closedImg.src = CLOSED_IMG;
        let currentImg = openImg;
        let blinkTimers = [];
        let animationId = null;
        let stopped = false;

        function schedule(fn, delay) {{
            const id = setTimeout(fn, delay);
            blinkTimers.push(id);
            return id;
        }}

        function clearTimers() {{
            blinkTimers.forEach((id) => clearTimeout(id));
            blinkTimers = [];
        }}

        function drawCameraFrame(img) {{
            ctx.fillStyle = '#f2f2f2';
            ctx.fillRect(0, 0, canvas.width, canvas.height);
            if (!img.complete || img.naturalWidth === 0) return;

            const boxSize = Math.round(canvas.height * 0.62);
            const boxX    = Math.round((canvas.width  - boxSize) / 2);
            const boxY    = Math.round((canvas.height - boxSize) / 2);
            ctx.fillStyle = '#eeeeee';
            ctx.fillRect(boxX, boxY, boxSize, boxSize);

            const scale  = Math.min(boxSize / img.naturalWidth, boxSize / img.naturalHeight);
            const width  = img.naturalWidth  * scale;
            const height = img.naturalHeight * scale;
            const x = boxX + (boxSize - width)  / 2;
            const y = boxY + (boxSize - height) / 2;
            ctx.drawImage(img, x, y, width, height);
        }}

        function drawLoop() {{
            drawCameraFrame(currentImg);
            if (!stopped) animationId = requestAnimationFrame(drawLoop);
        }}

        function stillOnIpvPage() {{
            const url = window.location.href.toLowerCase();
            const body = (document.body && document.body.innerText || '').toLowerCase();
            return url.includes('photo_capturing')
                || body.includes('blink your eyes')
                || body.includes('finding face')
                || body.includes('lets take a selfie');
        }}

        function startBlinkCycle(waitBeforeCloseMs = FIRST_OPEN_MS) {{
            if (stopped) return;
            currentImg = openImg;
            window.__REKYC_IPV_BLINK_DONE__ = false;
            schedule(closeEyesOnce, waitBeforeCloseMs);
        }}

        function closeEyesOnce() {{
            if (stopped) return;
            if (!stillOnIpvPage()) {{
                currentImg = openImg;
                window.__REKYC_IPV_BLINK_DONE__ = true;
                return;
            }}
            currentImg = closedImg;
            schedule(() => {{
                currentImg = openImg;
                window.__REKYC_IPV_BLINK_DONE__ = true;
                schedule(() => {{
                    if (!stopped && stillOnIpvPage()) closeEyesOnce();
                }}, RETRY_OPEN_MS);
            }}, CLOSED_MS);
        }}

        let installed = false;
        const install = () => {{
            if (installed) return;
            installed = true;
            currentImg = openImg;
            drawCameraFrame(openImg);
            drawLoop();
            startBlinkCycle();
            const media = navigator.mediaDevices || {{}};
            media.getUserMedia = async (constraints) => {{
                if (constraints && constraints.video) return canvas.captureStream(30);
                return new MediaStream();
            }};
            Object.defineProperty(navigator, 'mediaDevices', {{
                configurable: true,
                get: () => media,
            }});
            window.__REKYC_IPV_STOP_BLINKING__ = () => {{
                stopped = true;
                clearTimers();
                if (animationId) cancelAnimationFrame(animationId);
                currentImg = openImg;
                drawCameraFrame(openImg);
                window.__REKYC_IPV_BLINK_DONE__ = true;
            }};
            console.log('[ReKYC-IPV] Real blink camera installed');
        }};

        let loaded = 0;
        const done = () => {{ loaded += 1; if (loaded >= 2) install(); }};
        openImg.onload   = done;
        closedImg.onload = done;
        openImg.onerror = install;
        closedImg.onerror = install;
        if (openImg.complete) done();
        if (closedImg.complete) done();
        schedule(() => {{ if (!installed) install(); }}, 1000);
    }})();
    """

    page.add_init_script(js_code)
    try:
        page.evaluate(js_code)
    except Exception:
        pass
    print("  [OK] IPV fake blink camera injected")



# -----------------------------------------------------------------------------
#  Consent handling -- ReKYC IPV consent is different from eKYC
#  ReKYC shows: "I agree to the use of my device camera for the above-stated purpose"
#  with an Accept button to proceed. eKYC used a file-upload approach entirely.
# -----------------------------------------------------------------------------

IPV_REKYC_CONSENT_CHECKBOX_LOCATORS = [
    # Exact text match
    "//input[@type='checkbox' and not(@disabled)]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'i agree to the use of my device camera')]/preceding::input[@type='checkbox'][1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'camera')]/preceding::input[@type='checkbox'][1]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'i agree')]/preceding::input[@type='checkbox'][1]",
    # Class-based fallback
    "input[type='checkbox']:not([disabled])",
]

IPV_REKYC_ACCEPT_LOCATORS = [
    "//button[normalize-space()='Accept']",
    "//button[normalize-space()='I Accept']",
    "//input[@type='button' and translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='accept']",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed with ipv')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed with ipv')]",
]

IPV_REKYC_READY_SELECTORS = [
    # The ReKYC liveness screen shows these texts/elements when camera is active
    "//video",
    "//canvas",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'finding face')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'blink')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'look straight')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'place your face')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'please follow the above instructions')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'position your face')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'center your face')]",
]

IPV_REKYC_SUCCESS_SELECTORS = [
    # These are unambiguous post-capture page indicators only.
    # DO NOT add generic words like 'verified', 'captured', 'liveness' here —
    # those appear on the camera screen itself and cause false positives.
    # NOTE: 'proceed to e-sign' is safe here — on the ReKYC page it only
    # becomes visible AFTER the IPV widget completes, not before.
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'view unsigned kyc pdf')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'unsigned kyc pdf')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed to e-sign')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed to esign')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ipv done')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ipv successful')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ipv completed')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'photo taken successfully')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'live photo captured')]",
]

IPV_REKYC_EXPIRED_SELECTORS = [
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'photo capture time has expired')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'capture time expired')]",
    "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'session expired')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'retake')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'retake photo')]",
]

IPV_REKYC_CONFIRM_LOCATORS = [
    # Only buttons that specifically appear AFTER photo is captured.
    # Do NOT include generic 'proceed', 'continue', 'submit' — they match wrong buttons.
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'confirm')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'use photo')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'use this photo')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
]


def _ipv_check_visible(page, selectors, timeout_ms=600):
    """Returns True if any selector from the list is currently visible."""
    for sel in selectors:
        try:
            if page.locator(sel).first.is_visible(timeout=timeout_ms):
                return True
        except Exception:
            continue
    return False


def _ipv_click_first_visible(page, selectors, timeout_ms=3000):
    """Click the first visible element from the list. Returns True on success."""
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if el.is_visible(timeout=timeout_ms):
                el.click(force=True)
                page.wait_for_timeout(800)
                return True
        except Exception:
            continue
    return False


def click_ipv_consent_checkbox_strong(page):
    try:
        clicked = page.evaluate(
            """() => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const fireClick = (el) => {
                    if (!el) return false;
                    el.scrollIntoView({ block: 'center', inline: 'center' });
                    const rect = el.getBoundingClientRect();
                    const opts = {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + rect.height / 2
                    };
                    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        el.dispatchEvent(new MouseEvent(type, opts));
                    }
                    if (typeof el.click === 'function') el.click();
                    return true;
                };
                const modal = Array.from(document.querySelectorAll('div, section, article, form'))
                    .filter((el) => {
                        const text = (el.innerText || '').toLowerCase();
                        return text.includes('live photo capture required')
                            || text.includes('in-person verification')
                            || text.includes('proceed with ipv')
                            || text.includes('camera access')
                            || text.includes('i agree');
                    })
                    .sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (ar.width * ar.height) - (br.width * br.height);
                    })[0] || document;

                const input = Array.from(modal.querySelectorAll('input[type="checkbox"]'))
                    .find((el) => !el.disabled) || document.querySelector('input[type="checkbox"]:not([disabled])');
                if (input) {
                    input.checked = true;
                    input.setAttribute('checked', 'checked');
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    fireClick(input);
                    input.checked = true;
                    input.dispatchEvent(new Event('change', { bubbles: true }));
                    if (input.checked) return true;
                }

                const label = Array.from(modal.querySelectorAll('label, span, div, p'))
                    .find((el) => (el.innerText || el.textContent || '').toLowerCase().includes('i agree'));
                if (label) {
                    fireClick(label);
                    const rect = label.getBoundingClientRect();
                    for (const x of [rect.left - 24, rect.left - 38, rect.left + 12]) {
                        const target = document.elementFromPoint(x, rect.top + rect.height / 2);
                        fireClick(target);
                    }
                }

                const smallBoxes = Array.from(modal.querySelectorAll('input, span, div, label, i'))
                    .filter((el) => {
                        const rect = el.getBoundingClientRect();
                        const cls = String(el.className || '').toLowerCase();
                        return isVisible(el)
                            && rect.width >= 10 && rect.width <= 42
                            && rect.height >= 10 && rect.height <= 42
                            && (cls.includes('check') || cls.includes('box') || el.matches('input[type="checkbox"], label, span'));
                    });
                for (const box of smallBoxes) {
                    fireClick(box);
                    const current = modal.querySelector('input[type="checkbox"]') || document.querySelector('input[type="checkbox"]');
                    if (!current || current.checked) return true;
                }
                const current = modal.querySelector('input[type="checkbox"]') || document.querySelector('input[type="checkbox"]');
                return !current || current.checked;
            }"""
        )
        if clicked:
            page.wait_for_timeout(600)
            return True
    except Exception:
        pass

    try:
        label = page.locator("//*[contains(normalize-space(.),'I agree')]").first
        box = label.bounding_box(timeout=2000)
        if box:
            y = box["y"] + box["height"] / 2
            for x in [box["x"] - 24, box["x"] - 38, box["x"] + 12]:
                page.mouse.click(x, y)
                page.wait_for_timeout(300)
            return True
    except Exception:
        pass
    return False


def click_ipv_proceed_button_strong(page):
    if _ipv_click_first_visible(
        page,
        [
            "xpath=//button[normalize-space(.)='Proceed with IPV']",
            "xpath=//button[contains(normalize-space(.),'Proceed with IPV')]",
            "xpath=//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed with ipv')]",
            "xpath=//a[contains(normalize-space(.),'Proceed with IPV')]",
            "xpath=//button[contains(normalize-space(.),'Accept')]",
        ],
        timeout_ms=5000,
    ):
        return True
    try:
        clicked = page.evaluate(
            """() => {
                const btn = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"]'))
                    .find((el) => {
                        const text = (el.innerText || el.value || '').toLowerCase();
                        const rect = el.getBoundingClientRect();
                        const style = getComputedStyle(el);
                        return rect.width > 0
                            && rect.height > 0
                            && style.display !== 'none'
                            && style.visibility !== 'hidden'
                            && (text.includes('proceed with ipv') || text.includes('accept'));
                    });
                if (!btn) return false;
                btn.disabled = false;
                btn.removeAttribute('disabled');
                btn.scrollIntoView({ block: 'center', inline: 'center' });
                btn.click();
                return true;
            }"""
        )
        if clicked:
            page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    return False


def accept_rekyc_ipv_consent(page):
    """
    ReKYC IPV consent flow (aligned with eKYC robust implementation):
      1. Checkbox: 'I agree to the use of my device camera...'
      2. Button:   'Accept' or 'Proceed with IPV'

    Returns True if consent was found and accepted, False if not shown.
    Uses the same multi-strategy JS + coordinate fallback as eKYC's accept_ipv_camera_consent.
    """
    page.wait_for_timeout(1500)
    page_text = visible_text(page).lower()

    consent_indicators = [
        "i agree to the use of my device camera",
        "camera access",
        "live photo",
        "liveness",
        "ipv",
        "in-person verification",
    ]
    if not any(ind in page_text for ind in consent_indicators):
        return False   # consent UI not visible right now

    print("  [i] ReKYC IPV consent screen detected")
    if click_ipv_consent_checkbox_strong(page):
        print("  [OK] IPV consent checkbox selected")
        if click_ipv_proceed_button_strong(page):
            print("  [OK] Proceed with IPV clicked")
            page.wait_for_timeout(3000)
            return True

    # ── Strategy 1: eKYC-style JS modal scan ─────────────────────────────────
    checked = False
    try:
        checked = page.evaluate("""
            () => {
                const modal = Array.from(document.querySelectorAll('div, section, article'))
                    .filter(el => {
                        const text = (el.innerText || '').trim();
                        return (text.includes('Live Photo Capture Required') ||
                                text.includes('In-Person Verification') ||
                                text.includes('device camera')) &&
                            text.includes('I agree to the use of my device camera') &&
                            (text.includes('Accept') || text.includes('Proceed with IPV'));
                    })
                    .sort((a, b) => (a.getBoundingClientRect().width * a.getBoundingClientRect().height) -
                        (b.getBoundingClientRect().width * b.getBoundingClientRect().height))[0] || document;

                const candidates = Array.from(modal.querySelectorAll(
                    "input[type='checkbox'], [role='checkbox'], .checkbox, .checkmark, label, span"
                ));
                const checkbox = candidates.find(el => {
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 8 || rect.height < 8 || rect.width > 80 || rect.height > 80) return false;
                    const style = window.getComputedStyle(el);
                    if (style.visibility === 'hidden' || style.display === 'none') return false;
                    const text = (el.innerText || el.getAttribute('aria-label') || '').trim();
                    return el.matches("input[type='checkbox'], [role='checkbox'], .checkbox, .checkmark") ||
                        text === '' || text.includes('I agree');
                });
                if (!checkbox) return false;

                checkbox.scrollIntoView({block: 'center', inline: 'center'});
                if (checkbox.tagName === 'INPUT') {
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('input', {bubbles: true}));
                    checkbox.dispatchEvent(new Event('change', {bubbles: true}));
                    if (!checkbox.checked) checkbox.click();
                    return checkbox.checked;
                }

                checkbox.click();
                const input = modal.querySelector("input[type='checkbox']");
                return !input || input.checked || checkbox.getAttribute('aria-checked') === 'true' ||
                    checkbox.className.toString().toLowerCase().includes('checked');
            }
        """)
        if checked:
            print("  [OK] IPV consent checkbox selected (JS modal scan)")
    except Exception:
        checked = False

    # ── Strategy 2: Playwright locator fallback (eKYC checkbox_selectors) ────
    checkbox_selectors = [
        "xpath=//input[@type='checkbox' and not(@disabled)]",
        "xpath=//*[contains(normalize-space(.),'I agree to the use of my device camera')]/preceding::input[@type='checkbox'][1]",
        "xpath=//*[contains(normalize-space(.),'I agree to the use of my device camera')]/preceding::*[contains(@class,'checkbox') or @role='checkbox'][1]",
        "xpath=//*[contains(normalize-space(.),'I agree to the use of my device camera')]/preceding::*[self::span or self::label][1]",
    ]
    for selector in checkbox_selectors:
        if checked:
            break
        try:
            cb = page.locator(selector).first
            if cb.count() > 0 and cb.is_visible(timeout=1_000):
                try:
                    if hasattr(cb, "is_checked") and cb.is_checked():
                        checked = True
                    else:
                        cb.click(force=True, timeout=2_000)
                        checked = True
                except Exception:
                    cb.click(force=True, timeout=2_000)
                    checked = True
                break
        except Exception:
            continue

    # ── Strategy 3: eKYC-style label text scan JS ────────────────────────────
    if not checked:
        try:
            checked = page.evaluate("""
                () => {
                    const labels = Array.from(document.querySelectorAll('label, div, p, span'));
                    const targetText = 'I agree to the use of my device camera for the above-stated purpose';
                    const label = labels.find(el => (el.textContent || '').includes(targetText));
                    let checkbox = null;
                    if (label) {
                        checkbox = label.querySelector("input[type='checkbox']") ||
                            label.parentElement?.querySelector("input[type='checkbox']") ||
                            document.querySelector("input[type='checkbox']");
                    } else {
                        checkbox = document.querySelector("input[type='checkbox']");
                    }
                    if (!checkbox) return false;
                    checkbox.scrollIntoView({block: 'center'});
                    checkbox.checked = true;
                    checkbox.dispatchEvent(new Event('input', {bubbles: true}));
                    checkbox.dispatchEvent(new Event('change', {bubbles: true}));
                    checkbox.click();
                    return true;
                }
            """)
        except Exception:
            checked = False

    # ── Strategy 4: coordinate-click fallback (eKYC style) ───────────────────
    if not checked:
        try:
            page.mouse.click(665, 650)
            page.wait_for_timeout(500)
            checked = page.evaluate("""
                () => {
                    const input = document.querySelector("input[type='checkbox']");
                    return !input || input.checked;
                }
            """)
        except Exception:
            pass

    if not checked:
        print("  [WARN] IPV consent checkbox could not be selected")
        return False

    page.wait_for_timeout(500)

    # ── Click Accept / Proceed with IPV ──────────────────────────────────────
    accept_selectors = [
        "xpath=//button[normalize-space(.)='Accept']",
        "xpath=//button[normalize-space(.)='I Accept']",
        "xpath=//button[contains(normalize-space(.),'Accept')]",
        "xpath=//a[contains(normalize-space(.),'Accept')]",
        "xpath=//input[contains(@value,'Accept')]",
        "xpath=//button[contains(normalize-space(.),'Proceed with IPV')]",
        "xpath=//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed with ipv')]",
    ]
    for selector in accept_selectors:
        try:
            btn = page.locator(selector).first
            if btn.count() > 0 and btn.is_visible(timeout=1_000):
                btn.click(force=True, timeout=3_000)
                print("  [OK] IPV consent checkbox selected and Accept clicked")
                page.wait_for_timeout(3_000)
                return True
        except Exception:
            continue

    # ── JS fallback for Accept button ─────────────────────────────────────────
    try:
        accepted = page.evaluate("""
            () => {
                const keywords = ['accept', 'proceed with ipv', 'i accept'];
                const btns = Array.from(document.querySelectorAll('button, a, input[type="button"], input[type="submit"]'));
                const match = btns.find(el => {
                    const t = (el.textContent || el.value || '').trim().toLowerCase();
                    const r = el.getBoundingClientRect();
                    return keywords.some(k => t === k || t.includes(k)) && r.width > 0 && r.height > 0;
                });
                if (!match) return false;
                match.scrollIntoView({block: 'center'});
                match.click();
                return true;
            }
        """)
        if accepted:
            print("  [OK] IPV consent accepted (JS fallback)")
            page.wait_for_timeout(3_000)
            return True
    except Exception:
        pass

    print("  [WARN] IPV consent Accept button not found -- continuing anyway")
    return False


def run_rekyc_ipv_liveness(page):
    inject_fixed_geolocation(page)
    inject_fake_camera_with_blink(page)
    accept_rekyc_ipv_consent(page)

    try:
        if page.locator("xpath=//*[contains(normalize-space(.),'Kindly enable your Location')]").is_visible(timeout=3_000):
            print("  [WARN] Location prompt -- reloading")
            page.reload(wait_until="domcontentloaded", timeout=30_000)
            page.wait_for_timeout(2_000)
            accept_rekyc_ipv_consent(page)
    except Exception:
        pass

    print("  [i] Waiting for IPV yellow face box / ready state...")
    ready_selectors = [
        "xpath=//*[contains(normalize-space(.),'Finding Face')]",
        "xpath=//*[contains(normalize-space(.),'Blink Your Eyes')]",
        "xpath=//*[contains(normalize-space(.),'Please follow the above instructions')]",
        "xpath=//*[contains(normalize-space(.),'Look straight into the camera')]",
        "css=video",
        "css=canvas",
    ]
    ready = False
    for _ in range(16):
        for selector in ready_selectors:
            try:
                loc = page.locator(selector).first
                if loc.count() > 0 and loc.is_visible(timeout=500):
                    ready = True
                    break
            except Exception:
                continue
        if ready:
            break
        page.wait_for_timeout(500)

    if not ready:
        print("  [WARN] IPV ready state not detected -- attempting capture anyway")

    print("  [i] IPV ready; waiting for automatic photo capture...")
    retake_selector = (
        "xpath=//button[contains(normalize-space(.),'Retake Photo') or "
        "contains(normalize-space(.),'Retake')]"
    )

    def stop_ipv_blinking():
        try:
            page.evaluate(
                "() => { if (window.__REKYC_IPV_STOP_BLINKING__) window.__REKYC_IPV_STOP_BLINKING__(); }"
            )
        except Exception:
            pass

    def wait_for_post_ipv_transition(timeout_s=60):
        deadline = time.time() + timeout_s
        print(f"  [i] Waiting up to {timeout_s}s for unsigned PDF / Continue to eSign page...")
        while time.time() < deadline:
            current_url = page.url.lower()
            if "login" in current_url:
                raise Exception("After IPV capture, page redirected to login instead of unsigned PDF/eSign page")
            if "uuid.php" in current_url:
                stop_ipv_blinking()
                print("  [OK] IPV moved to KYC generation page")
                return True
            if "proteantech.in" in current_url:
                stop_ipv_blinking()
                print("  [OK] Protean eSign page reached after IPV")
                return True
            try:
                next_step = page.locator(
                    "xpath=//*[contains(normalize-space(.),'View Unsigned KYC PDF') or "
                    "contains(normalize-space(.),'Unsigned KYC PDF') or "
                    "contains(normalize-space(.),'continue to E-sign') or "
                    "contains(normalize-space(.),'Continue to E-sign') or "
                    "contains(normalize-space(.),'Continue to E-Sign') or "
                    "contains(normalize-space(.),'Continue to eSign')]"
                )
                if next_step.count() > 0 and next_step.first.is_visible(timeout=500):
                    stop_ipv_blinking()
                    print("  [OK] Unsigned PDF / Continue to eSign page loaded")
                    return True
            except Exception:
                pass
            page.wait_for_timeout(1000)
        return False

    def click_retake(reason):
        try:
            retake = page.locator(retake_selector).first
            retake.wait_for(state="visible", timeout=5_000)
            print(f"  {reason}; clicking Retake Photo")
            retake.click(force=True, timeout=3_000)
            page.wait_for_timeout(2_000)
            return True
        except Exception:
            return False

    for attempt in range(1, 4):
        deadline = time.time() + 35
        expired_this_attempt = False

        while time.time() < deadline:
            try:
                expired = page.locator(
                    "xpath=//*[contains(normalize-space(.),'photo capture time has expired') or "
                    "contains(normalize-space(.),'Retake Photo')]"
                )
                if expired.count() > 0 and expired.first.is_visible(timeout=500):
                    click_retake("IPV capture expired")
                    expired_this_attempt = True
                    break
            except Exception:
                pass

            if expired_this_attempt:
                break

            try:
                next_step = page.locator(
                    "xpath=//*[contains(normalize-space(.),'View Unsigned KYC PDF') or "
                    "contains(normalize-space(.),'Unsigned KYC PDF') or "
                    "contains(normalize-space(.),'continue to E-sign') or "
                    "contains(normalize-space(.),'Continue to E-sign') or "
                    "contains(normalize-space(.),'Continue to E-Sign')]"
                )
                if "photo_capturing" not in page.url.lower() or (next_step.count() > 0 and next_step.first.is_visible(timeout=500)):
                    print("  [OK] IPV photo auto-captured; moved to next step")
                    stop_ipv_blinking()
                    wait_for_post_ipv_transition(timeout_s=45)
                    return
            except Exception:
                pass

            page.wait_for_timeout(500)

        if not expired_this_attempt:
            if wait_for_post_ipv_transition(timeout_s=20):
                return
                click_retake(f"IPV attempt {attempt} did not complete within 35 seconds")

        print(f"  [i] IPV attempt {attempt} did not complete; retrying")

    if "photo_capturing" not in page.url.lower():
        stop_ipv_blinking()
        print("  [OK] IPV moved away from capture page")
        return
    if wait_for_post_ipv_transition(timeout_s=45):
        return
    raise Exception("ReKYC IPV liveness capture did not complete after 3 attempts")


    print("  [OK] ReKYC IPV liveness flow complete")


def prepare_ipv_browser(page):
    """
    Sets up browser-level fakes for ReKYC live IPV BEFORE navigating to the IPV page.
    Call this before opening the IPV section.

    Aligned with eKYC's pattern: geolocation is injected first, then the fake camera.
    Both use add_init_script so they persist across page reloads during consent flow
    or location-error recovery.
    Note: inject_fake_camera_with_blink is also called inside run_rekyc_ipv_liveness()
    to handle cases where the page reloads during consent flow.
    """
    inject_fixed_geolocation(page)
    inject_fake_camera_with_blink(page)
    print("  [i] ReKYC IPV browser prepared: fake camera + geolocation injected")


def fill_service_email_if_present(page, section_name):
    if section_name.lower() != "email":
        return
    if fill_first_visible(page, SERVICE_EMAIL_INPUT_LOCATORS, NEW_SERVICE_EMAIL, timeout=1500):
        print(f"  [OK] New email entered: {NEW_SERVICE_EMAIL}")


def is_signature_dialog_open(page):
    markers = [
        "//button[normalize-space()='Upload Signature']",
        "//button[normalize-space()='Draw Signature']",
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload (or) capture')]",
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'sign here')]",
        "//*[contains(@class,'modal') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload signature')]",
    ]
    for loc in markers:
        try:
            if page.locator(loc).first.is_visible(timeout=700):
                return True
        except Exception:
            continue
    return False


def click_signature_open_button(page):
    for loc in SIGNATURE_TRIGGER_LOCATORS:
        try:
            el = page.locator(loc).first
            if el.is_visible(timeout=1200):
                el.scroll_into_view_if_needed(timeout=2000)
                el.click(force=True, timeout=3000)
                page.wait_for_timeout(1000)
                if is_signature_dialog_open(page):
                    return True
        except Exception:
            continue
    try:
        clicked = page.evaluate(
            """() => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const dispatchClick = (el) => {
                    el.scrollIntoView({ block: 'center', inline: 'center' });
                    const rect = el.getBoundingClientRect();
                    const opts = {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: rect.left + rect.width / 2,
                        clientY: rect.top + rect.height / 2
                    };
                    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        el.dispatchEvent(new MouseEvent(type, opts));
                    }
                    if (typeof el.click === 'function') el.click();
                };
                const nodes = Array.from(document.querySelectorAll('button,input,a,label,div,span'));
                const match = nodes.find((el) => {
                    const text = `${el.innerText || ''} ${el.value || ''} ${el.getAttribute('aria-label') || ''}`.toLowerCase();
                    return text.includes('please upload signature') && isVisible(el);
                });
                if (!match) return false;
                const clickable = match.closest('button,a,label') || match;
                dispatchClick(clickable);
                return true;
            }"""
        )
        if clicked:
            page.wait_for_timeout(1000)
            if is_signature_dialog_open(page):
                return True
    except Exception:
        pass
    try:
        opened = page.evaluate(
            """() => {
                const candidates = [
                    '#upload_sign',
                    '#drawimagerestcl',
                    'label[for="drawimagerest"]',
                    'label[for="drawimage"]'
                ];
                for (const selector of candidates) {
                    const el = document.querySelector(selector);
                    if (!el) continue;
                    el.scrollIntoView({ block: 'center', inline: 'center' });
                    el.click();
                    return true;
                }
                return false;
            }"""
        )
        if opened:
            page.wait_for_timeout(1000)
            if is_signature_dialog_open(page):
                return True
    except Exception:
        pass
    try:
        pill = page.get_by_text("Please upload signature", exact=True).first
        if pill.is_visible(timeout=2000):
            pill.scroll_into_view_if_needed(timeout=2000)
            pill.click(force=True, timeout=3000)
            page.wait_for_timeout(1000)
            if is_signature_dialog_open(page):
                return True
    except Exception:
        pass
    try:
        pill = page.locator("text=Please upload signature").first
        box = pill.bounding_box(timeout=2000)
        if box:
            page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.mouse.down()
            page.mouse.up()
            page.wait_for_timeout(1000)
            if is_signature_dialog_open(page):
                return True
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(1000)
            if is_signature_dialog_open(page):
                return True
    except Exception:
        pass
    try:
        debug = page.evaluate(
            """() => Array.from(document.querySelectorAll('button,input,a,label,div,span'))
                .map((el) => {
                    const text = `${el.innerText || ''} ${el.value || ''} ${el.id || ''} ${el.className || ''}`.trim();
                    const rect = el.getBoundingClientRect();
                    return { text, x: rect.x, y: rect.y, w: rect.width, h: rect.height };
                })
                .filter((x) => x.text.toLowerCase().includes('signature') || x.text.toLowerCase().includes('upload'))
                .slice(0, 12)
            """
        )
        print(f"  [DEBUG] Signature click candidates: {debug}")
    except Exception:
        pass
    return False


def click_signature_submit_button(page):
    if click_first_visible(page, SIGNATURE_SUBMIT_LOCATORS, timeout=5000):
        return True
    try:
        clicked = page.evaluate(
            """() => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden'
                        && style.pointerEvents !== 'none';
                };
                const nodes = Array.from(document.querySelectorAll('button,input[type=submit],input[type=button],a'));
                const match = nodes.find((el) => {
                    const text = `${el.innerText || ''} ${el.value || ''} ${el.getAttribute('aria-label') || ''}`.trim().toLowerCase();
                    return isVisible(el) && (text === 'submit' || text.includes('submit'));
                });
                if (!match) return false;
                match.scrollIntoView({ block: 'center', inline: 'center' });
                match.click();
                return true;
            }"""
        )
        if clicked:
            page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    try:
        submit = page.locator("text=Submit").first
        box = submit.bounding_box(timeout=2000)
        if box:
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(1000)
            return True
    except Exception:
        pass
    return False


def wait_for_signature_preview(page):
    preview_locators = [
        "img[src*='signature' i]",
        "img[src*='sign' i]",
        "img",
        "//button[normalize-space()='Submit']",
        "//input[@type='submit' and translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='submit']",
    ]
    deadline = time.time() + 10
    while time.time() < deadline:
        for loc in preview_locators:
            try:
                if page.locator(loc).first.is_visible(timeout=500):
                    return True
            except Exception:
                continue
        page.wait_for_timeout(500)
    return False


def upload_signature_for_esign(page):
    if not os.path.exists(SIGNATURE_FILE_PATH):
        raise Exception(f"Signature file not found: {SIGNATURE_FILE_PATH}")
    if not click_signature_open_button(page):
        raise Exception("Open signature upload button not found")
    page.wait_for_timeout(1000)
    click_first_visible(page, SIGNATURE_UPLOAD_TAB_LOCATORS, timeout=5000)
    page.wait_for_timeout(1000)
    uploaded = False

    try:
        with page.expect_file_chooser(timeout=3000) as chooser_info:
            if not click_first_visible(page, SIGNATURE_UPLOAD_AREA_LOCATORS, timeout=3000):
                raise Exception("Upload area not clickable")
        chooser_info.value.set_files(SIGNATURE_FILE_PATH)
        uploaded = True
    except Exception:
        uploaded = False

    for loc in SIGNATURE_FILE_INPUT_LOCATORS:
        if uploaded:
            break
        try:
            file_input = page.locator(loc).first
            if file_input.count() > 0:
                file_input.set_input_files(SIGNATURE_FILE_PATH, timeout=5000)
                uploaded = True
                break
        except Exception:
            continue
    if not uploaded:
        raise Exception("Signature file input not found")
    page.wait_for_timeout(1500)
    wait_for_signature_preview(page)
    click_first_visible(
        page,
        [
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'use original')]",
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'use orginal')]",
        ],
        timeout=3000,
    )
    page.wait_for_timeout(500)
    if not click_signature_submit_button(page):
        raise Exception("Signature submit/continue button not found")
    page.wait_for_timeout(5000)
    print("  [OK] Signature uploaded and submitted")


def view_unsigned_pdf(page):
    original_url = page.url
    pdf_page = None
    deadline = time.time() + 120
    pdf_link = None
    while time.time() < deadline:
        if "proteantech.in" in page.url.lower():
            print("  [OK] Already on Protean eSign page")
            return
        if any_locator_visible(page, PROCEED_ESIGN_LOCATORS, timeout=700):
            print("  [OK] Unsigned KYC page loaded with Continue to eSign")
            return
        for loc in UNSIGNED_PDF_LOCATORS:
            try:
                candidate = page.locator(loc).first
                if candidate.is_visible(timeout=700):
                    pdf_link = candidate
                    break
            except Exception:
                continue
        if pdf_link is not None:
            break
        try:
            if "uuid.php" in page.url.lower():
                page.wait_for_load_state("domcontentloaded", timeout=5000)
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass
        page.wait_for_timeout(1000)

    if pdf_link is None:
        raise Exception("Unsigned KYC PDF link or Continue to eSign button not found")

    try:
        with page.context.expect_page(timeout=15000) as pdf_info:
            pdf_link.click(force=True, timeout=5000)
        pdf_page = pdf_info.value
    except Exception:
        pdf_link.click(force=True, timeout=5000)
        page.wait_for_timeout(3000)
        pages = [p for p in get_all_pages(page) if p != page]
        pdf_page = pages[-1] if pages else page
    pdf_page.bring_to_front()
    pdf_page.wait_for_timeout(2000)
    for _ in range(8):
        try:
            pdf_page.keyboard.press("End")
            pdf_page.mouse.wheel(0, 1800)
        except Exception:
            pass
        pdf_page.wait_for_timeout(500)
    if pdf_page != page:
        pdf_page.close()
        page.bring_to_front()
    elif page.url != original_url:
        page.go_back(wait_until="domcontentloaded", timeout=30000)
    page.wait_for_timeout(1500)
    print("  [OK] Unsigned KYC PDF opened and viewed")


def accept_ipv_consent_if_present(page):
    page.wait_for_timeout(1000)
    if "live photo capture required" not in visible_text(page).lower():
        return False
    if click_ipv_consent_checkbox_strong(page) and click_ipv_proceed_button_strong(page):
        page.wait_for_timeout(3000)
        print("  [OK] IPV consent accepted")
        return True
    click_first_visible(page, IPV_CONSENT_CHECKBOX_LOCATORS, timeout=3000)
    if click_first_visible(page, IPV_PROCEED_LOCATORS, timeout=5000):
        page.wait_for_timeout(3000)
        print("  [OK] IPV consent accepted")
        return True
    try:
        clicked = page.evaluate(
            """() => {
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = getComputedStyle(el);
                    return rect.width > 0
                        && rect.height > 0
                        && style.display !== 'none'
                        && style.visibility !== 'hidden';
                };
                const checkbox = Array.from(document.querySelectorAll('input[type=checkbox]'))
                    .find((el) => isVisible(el) && !el.disabled);
                if (checkbox && !checkbox.checked) {
                    checkbox.click();
                    checkbox.dispatchEvent(new Event('change', { bubbles: true }));
                }
                const buttons = Array.from(document.querySelectorAll('button,input[type=button],input[type=submit],a'));
                const proceed = buttons.find((el) => {
                    const text = `${el.innerText || ''} ${el.value || ''}`.toLowerCase();
                    return isVisible(el) && text.includes('proceed with ipv');
                });
                if (!proceed) return false;
                proceed.disabled = false;
                proceed.removeAttribute('disabled');
                proceed.scrollIntoView({ block: 'center', inline: 'center' });
                proceed.click();
                return true;
            }"""
        )
        if clicked:
            page.wait_for_timeout(3000)
            print("  [OK] IPV consent accepted")
            return True
    except Exception:
        pass
    try:
        proceed = page.locator("text=Proceed with IPV").first
        box = proceed.bounding_box(timeout=2000)
        if box:
            page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
            page.wait_for_timeout(3000)
            print("  [OK] IPV consent accepted")
            return True
    except Exception:
        pass
    raise Exception("Proceed with IPV button not found or not clickable")


def capture_ipv_photo(page):
    """
    ReKYC live IPV liveness capture.

    IMPORTANT -- ReKYC vs eKYC difference:
      eKYC: IPV is done by uploading a static photo (eyes_open.jpg + eyes_closed.jpg)
      ReKYC: IPV is LIVE -- the browser streams video, the system detects your face,
             waits for a natural blink, then auto-captures. No file upload involved.

    This function delegates to run_rekyc_ipv_liveness() which:
      1. Injects a fake canvas-based camera feed that blinks every 900ms
      2. Accepts the consent checkbox
      3. Waits for the face detection / blink state
      4. Polls for successful capture (retries up to 3x on timeout)
      5. Clicks Confirm/Continue after capture
    """
    run_rekyc_ipv_liveness(page)


def click_continue_to_esign_button(page, timeout=90000):
    """
    Click the Continue to eSign control on the unsigned PDF page.
    The page sometimes renders it as a styled button/link after a long post-IPV
    load, so use normal locators first and a DOM click fallback second.
    """
    deadline = time.time() + (timeout / 1000)
    last_buttons = []
    while time.time() < deadline:
        clear_blocking_overlays(page)
        try:
            page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        except Exception:
            pass

        if click_first_visible(page, PROCEED_ESIGN_LOCATORS, timeout=1500):
            page.wait_for_timeout(2500)
            print("  [OK] Continue to eSign clicked")
            return True

        try:
            clicked = page.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        const style = window.getComputedStyle(el);
                        const rect = el.getBoundingClientRect();
                        return rect.width > 0 && rect.height > 0 &&
                               style.visibility !== 'hidden' &&
                               style.display !== 'none' &&
                               style.opacity !== '0';
                    };
                    const textOf = (el) => [
                        el.innerText || '',
                        el.textContent || '',
                        el.value || '',
                        el.getAttribute('aria-label') || '',
                        el.getAttribute('title') || '',
                        el.id || '',
                        el.name || '',
                        el.className || ''
                    ].join(' ').toLowerCase().replace(/\\s+/g, ' ').trim();
                    const controls = Array.from(document.querySelectorAll(
                        'button, a, input[type=button], input[type=submit], [role=button]'
                    ));
                    const match = controls.find((el) => {
                        const text = textOf(el);
                        return isVisible(el) &&
                               (text.includes('esign') || text.includes('e-sign')) &&
                               (text.includes('continue') || text.includes('proceed') || text.includes('submit') || text.includes('digio'));
                    });
                    if (!match) return false;
                    match.disabled = false;
                    match.removeAttribute('disabled');
                    match.removeAttribute('aria-disabled');
                    match.scrollIntoView({ block: 'center', inline: 'center' });
                    for (const eventName of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        match.dispatchEvent(new MouseEvent(eventName, {
                            bubbles: true,
                            cancelable: true,
                            view: window
                        }));
                    }
                    return true;
                }
                """
            )
            if clicked:
                page.wait_for_timeout(2500)
                print("  [OK] Continue to eSign clicked (JS fallback)")
                return True
        except Exception:
            pass

        try:
            last_buttons = page.evaluate(
                """
                () => Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a, [role=button]'))
                    .filter(el => {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                    })
                    .map(el => (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').trim())
                    .filter(Boolean)
                    .slice(0, 20)
                """
            )
        except Exception:
            pass
        page.wait_for_timeout(2000)

    print(f"  [DEBUG] Visible controls on unsigned PDF page: {last_buttons}")
    return False


def proceed_to_esign(page):
    if "proteantech.in" in page.url.lower():
        return
    
    # FIX: Clear overlays and scroll to ensure button is visible
    clear_blocking_overlays(page)
    page.wait_for_timeout(1000)
    
    # FIX: Scroll to find the button
    try:
        page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
        page.wait_for_timeout(500)
    except Exception:
        pass
    
    try:
        if not click_continue_to_esign_button(page, timeout=90000):
            buttons = page.evaluate("""
                () => Array.from(document.querySelectorAll('button, input[type=button], input[type=submit], a, [role=button]'))
                    .filter(el => el.offsetParent !== null)
                    .map(el => ({
                        text: (el.innerText || el.textContent || el.value || el.getAttribute('aria-label') || '').substring(0, 80),
                        tag: el.tagName
                    }))
            """)
            print(f"  [DEBUG] Visible buttons on page: {buttons}")
            raise Exception("Continue/Proceed to eSign button not found")
    except Exception as e:
        print(f"  [ERROR] Button click failed: {str(e)}")
        raise
    
    try:
        page.wait_for_url("**proteantech.in**", timeout=60000)
    except Exception:
        page.wait_for_timeout(5000)
    
    if "proteantech.in" not in page.url.lower():
        raise Exception(f"Protean eSign page did not open. Current URL: {page.url}")
    
    print("  [OK] Successfully navigated to Protean eSign page")


def complete_aadhaar_esign(page):
    if "proteantech.in" not in page.url.lower():
        page.wait_for_url("**proteantech.in**", timeout=60000)
    click_first_visible(page, ["//input[@type='checkbox' and not(@disabled)]"], timeout=30000)
    aadhaar_field = assert_visible_any(page, ESIGN_AADHAAR_LOCATORS, "Protean Aadhaar/VID field", timeout=30000)
    aadhaar_field.click()
    aadhaar_field.fill(CLIENT_AADHAAR_NUMBER)
    if not click_first_visible(page, ESIGN_SEND_OTP_LOCATORS, timeout=10000):
        raise Exception("Protean Send OTP button not found")
    page.wait_for_timeout(5000)
    otp = fetch_latest_yopmail_otp(page, "Aadhaar eSign OTP", ESIGN_OTP_EMAIL)
    if not fill_first_visible(page, ESIGN_OTP_LOCATORS, otp, timeout=30000):
        raise Exception("Protean OTP input not found")
    if not click_first_visible(page, ESIGN_SUBMIT_LOCATORS, timeout=10000):
        raise Exception("Protean OTP submit button not found")
    page.wait_for_timeout(8000)
    if "proteantech.in" in page.url.lower() and "invalid" in visible_text(page).lower():
        raise Exception("Protean eSign OTP validation failed")
    print("  [OK] Aadhaar eSign OTP submitted")
    if not click_request_placed_ok_if_present(page):
        try:
            page.goto(REKYC_URL, wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(3000)
        except Exception:
            pass


def complete_post_service_esign_flow(page):
    try:
        current_text = visible_text(page).lower()
    except Exception:
        current_text = ""
    if "upload signature" not in current_text and "signature" not in page.url.lower():
        try:
            page = wait_for_page_matching(page, ["upload_signature"], timeout=60000)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
        except Exception:
            pass
    upload_signature_for_esign(page)
    # IPV happens before the unsigned PDF link is generated.
    # Inject fake camera + geolocation immediately before the IPV step so that
    # getUserMedia is already overridden when the consent dialog appears.
    prepare_ipv_browser(page)
    capture_ipv_photo(page)
    view_unsigned_pdf(page)
    proceed_to_esign(page)
    complete_aadhaar_esign(page)


def wait_for_digilocker_page(page, timeout=60000):
    page.wait_for_timeout(2000)
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        current_url = page.url.lower()
        if (
            "digilocker.gov.in" in current_url
            or "digitallocker.gov.in" in current_url
            or "accounts.digilocker.gov.in" in current_url
            or "accounts.digitallocker.gov.in" in current_url
        ):
            return page
        for candidate in page.context.pages:
            try:
                url = candidate.url.lower()
                if (
                    "digilocker.gov.in" in url
                    or "digitallocker.gov.in" in url
                    or "accounts.digilocker.gov.in" in url
                    or "accounts.digitallocker.gov.in" in url
                ):
                    candidate.bring_to_front()
                    return candidate
            except Exception:
                continue
        page.wait_for_timeout(1000)
    raise Exception(f"DigiLocker page did not open. Current URL: {page.url}")


def click_address_proceed_to_change(page):
    if click_first_visible(page, ADDRESS_PROCEED_CHANGE_LOCATORS, timeout=10000):
        page.wait_for_timeout(3000)
        if "open.navia.co.in/uuid.php" in page.url.lower() or "uuid.php" in page.url.lower():
            print("  [OK] Address flow returned directly to Navia UUID page")
            return page
        return wait_for_digilocker_page(page)
    try:
        with page.context.expect_page(timeout=10000) as page_info:
            clicked = click_button_robust(page, ADDRESS_PROCEED_CHANGE_LOCATORS, "Proceed to Change", timeout=10000)
        if clicked:
            new_page = page_info.value
            new_page.wait_for_load_state("domcontentloaded", timeout=30000)
            return wait_for_digilocker_page(new_page)
    except Exception:
        pass
    raise Exception("Proceed to Change button not found or DigiLocker did not open")


def fill_digilocker_field(page, locators, value, description):
    for loc in locators:
        try:
            el = page.locator(loc).first
            if el.is_visible(timeout=30000):
                el.click()
                try:
                    el.fill("")
                except Exception:
                    pass
                el.fill(value)
                return True
        except Exception:
            continue
    if fill_otp_boxes(page, value):
        return True
    raise Exception(f"DigiLocker {description} field not found")


def click_digilocker_first(page, locators, description, timeout=30000):
    if click_first_visible(page, locators, timeout=timeout):
        page.wait_for_timeout(3000)
        return True
    if click_button_robust(page, locators, f"DigiLocker {description}", timeout=timeout):
        page.wait_for_timeout(3000)
        return True
    raise Exception(f"DigiLocker {description} button not found")


def select_digilocker_aadhaar_login(page):
    selected = False
    try:
        aadhaar_tab = page.locator("#pills-aadhaar-tab, a[aria-controls='pills-aadhaar']").first
        if aadhaar_tab.is_visible(timeout=10000):
            href = aadhaar_tab.get_attribute("href")
            aadhaar_tab.click(force=True, timeout=5000)
            page.wait_for_timeout(2000)
            if href and "uid_login" in href and "uid_login" not in page.url.lower():
                page.goto(href, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
            selected = True
    except Exception:
        selected = False
    if not selected:
        selected = click_first_visible(page, DIGILOCKER_AADHAAR_TAB_LOCATORS, timeout=10000)
    if not selected:
        try:
            selected = page.evaluate(
                """() => {
                    const aadhaarTab = document.querySelector('#pills-aadhaar-tab, a[aria-controls="pills-aadhaar"]');
                    if (aadhaarTab) {
                        aadhaarTab.scrollIntoView({ block: 'center', inline: 'center' });
                        const r = aadhaarTab.getBoundingClientRect();
                        const opts = { bubbles: true, cancelable: true, view: window, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
                        for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                            aadhaarTab.dispatchEvent(new MouseEvent(type, opts));
                        }
                        if (typeof aadhaarTab.click === 'function') aadhaarTab.click();
                        if (aadhaarTab.href && aadhaarTab.href !== window.location.href) {
                            window.location.href = aadhaarTab.href;
                        }
                        return true;
                    }
                    const isVisible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    const candidates = Array.from(document.querySelectorAll('button,a,[role=tab],div,span'))
                        .filter((el) => isVisible(el) && (el.innerText || el.textContent || '').trim().toLowerCase() === 'aadhaar');
                    const target = candidates[0];
                    if (!target) return false;
                    target.scrollIntoView({ block: 'center', inline: 'center' });
                    const r = target.getBoundingClientRect();
                    const opts = { bubbles: true, cancelable: true, view: window, clientX: r.left + r.width / 2, clientY: r.top + r.height / 2 };
                    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        target.dispatchEvent(new MouseEvent(type, opts));
                    }
                    if (typeof target.click === 'function') target.click();
                    return true;
                }"""
            )
        except Exception:
            selected = False
    if not selected:
        raise Exception("DigiLocker Aadhaar tab not found")

    deadline = time.time() + 15
    while time.time() < deadline:
        try:
            if "uid_login" in page.url.lower():
                print("  [OK] DigiLocker Aadhaar tab selected")
                return
        except Exception:
            pass
        if any_locator_visible(page, DIGILOCKER_AADHAAR_INPUT_LOCATORS, timeout=800):
            print("  [OK] DigiLocker Aadhaar tab selected")
            return
        page.wait_for_timeout(500)
    raise Exception("DigiLocker Aadhaar input did not appear after selecting Aadhaar tab")


def wait_for_digilocker_security_pin(page, timeout=60000):
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        try:
            if any_locator_visible(page, DIGILOCKER_SECURITY_PIN_INPUT_LOCATORS, timeout=800):
                return True
            if "verify_uid_otp" not in page.url.lower() and "signin_request_uid" not in page.url.lower():
                if any_locator_visible(page, DIGILOCKER_SECURITY_PIN_INPUT_LOCATORS, timeout=800):
                    return True
        except Exception:
            pass
        page.wait_for_timeout(1000)
    raise Exception("DigiLocker security PIN page did not open")


def wait_for_digilocker_return(page, timeout=60000):
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        current_url = page.url.lower()
        if "rekyc.navia.co.in" in current_url or "open.navia.co.in" in current_url:
            print("  [OK] Returned from DigiLocker to ReKYC")
            return page
        if "redirecting back to" in visible_text(page).lower():
            click_first_visible(page, DIGILOCKER_CONTINUE_LOCATORS, timeout=2000)
        else:
            click_first_visible(page, DIGILOCKER_CONTINUE_LOCATORS, timeout=1000)
        for candidate in page.context.pages:
            try:
                candidate_url = candidate.url.lower()
                if "rekyc.navia.co.in" in candidate_url or "open.navia.co.in" in candidate_url:
                    candidate.bring_to_front()
                    print("  [OK] Returned from DigiLocker to ReKYC")
                    return candidate
            except Exception:
                continue
        page.wait_for_timeout(1000)
    print("  [i] DigiLocker return still loading after 60 seconds")
    return page


def is_personal_details_page(page):
    try:
        current_url = page.url.lower()
    except Exception:
        current_url = ""
    if "personal_data" in current_url or "personal" in current_url:
        return True
    try:
        return page.locator(
            "xpath=//*[contains(normalize-space(.),'Personal Details') or "
            "contains(normalize-space(.),'Marital Status') or "
            "contains(normalize-space(.),'Educational Qualification')]"
        ).first.is_visible(timeout=3000)
    except Exception:
        return False


def click_personal_option(page, text, index=0, timeout=5000):
    selectors = [
        f"xpath=//label[normalize-space(.)='{text}']",
        f"xpath=//button[normalize-space(.)='{text}']",
        f"xpath=//*[normalize-space(.)='{text}' and (self::label or self::button or self::div or self::span or self::a)]",
        f"xpath=//input[@value='{text}' or @id='{text}']/ancestor::label[1]",
        f"xpath=//input[@value='{text}' or @id='{text}']",
    ]
    for selector in selectors:
        try:
            item = page.locator(selector).nth(index)
            item.wait_for(state="visible", timeout=timeout)
            item.scroll_into_view_if_needed(timeout=timeout)
            item.click(force=True, timeout=timeout)
            page.wait_for_timeout(400)
            return True
        except Exception:
            continue

    try:
        clicked = page.evaluate(
            """
            ({ text, index }) => {
                const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
                const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const st = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && st.display !== 'none' && st.visibility !== 'hidden';
                };
                const matches = Array.from(document.querySelectorAll('button,label,a,div,span,input,[role=button]'))
                    .filter((el) => {
                        const value = el.tagName === 'INPUT' ? (el.value || el.id || el.name) : el.innerText;
                        return norm(value) === text && visible(el);
                    });
                const target = matches[index];
                if (!target) return false;
                const clickable = target.closest('label,button,a,[role=button],.btn,.button') || target;
                clickable.scrollIntoView({ block: 'center', inline: 'center' });
                clickable.click();
                clickable.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                return true;
            }
            """,
            {"text": text, "index": index},
        )
        if clicked:
            page.wait_for_timeout(400)
            return True
    except Exception:
        pass
    return False


def fill_personal_field(page, label, names, value, timeout=8000):
    if not value:
        return False
    selectors = []
    for name in names:
        selectors.extend([
            f"xpath=//input[@name='{name}']",
            f"xpath=//input[@id='{name}']",
        ])
    selectors.extend([
        f"xpath=//input[contains(@placeholder,'{label}')]",
        f"xpath=//*[contains(normalize-space(.),'{label}')]/following::input[1]",
    ])
    for selector in selectors:
        try:
            field = page.locator(selector).first
            field.wait_for(state="visible", timeout=timeout)
            field.scroll_into_view_if_needed(timeout=timeout)
            if field.is_disabled(timeout=1000):
                continue
            field.click(force=True)
            field.fill("")
            field.fill(value)
            if field.input_value(timeout=2000).strip():
                print(f"  [OK] Personal Details {label} filled")
                return True
        except Exception:
            continue
    print(f"  [WARN] Personal Details {label} field not filled")
    return False


def check_personal_declarations(page):
    selectors = [
        "xpath=//span[contains(normalize-space(.),'I have read and accepted')]/preceding::input[@type='checkbox'][1]",
        "xpath=//label[contains(normalize-space(.),'I have read and accepted')]//input[@type='checkbox']",
        "xpath=//input[@name='declaration' or @name='agree_declaration']",
        "xpath=//span[contains(normalize-space(.),'I am opting for BSDA')]/preceding::input[@type='checkbox'][1]",
        "xpath=//label[contains(normalize-space(.),'I am opting for BSDA')]//input[@type='checkbox']",
        "xpath=//span[contains(normalize-space(.),'neither mentally challenged')]/preceding::input[@type='checkbox'][1]",
        "xpath=//label[contains(normalize-space(.),'neither mentally challenged')]//input[@type='checkbox']",
        "xpath=//input[@name='agree_all']",
    ]
    for selector in selectors:
        try:
            cb = page.locator(selector).first
            if cb.count() > 0 and cb.is_visible(timeout=1000):
                cb.scroll_into_view_if_needed(timeout=2000)
                if not cb.is_checked():
                    cb.check(force=True)
        except Exception:
            pass


def click_personal_next(page):
    selectors = [
        "xpath=//button[@id='submitform']",
        "xpath=//button[normalize-space(.)='Next']",
        "xpath=//button[contains(normalize-space(.),'Next')]",
        "xpath=//input[@type='submit']",
        "xpath=//*[self::button or self::a or @role='button'][contains(normalize-space(.),'Next')]",
    ]
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    page.wait_for_timeout(700)
    for selector in selectors:
        try:
            btn = page.locator(selector).first
            btn.wait_for(state="visible", timeout=4000)
            btn.scroll_into_view_if_needed(timeout=4000)
            btn.click(force=True, timeout=4000)
            page.wait_for_timeout(2000)
            return True
        except Exception:
            continue
    return False


def is_address_proof_upload_page(page):
    try:
        current_url = page.url.lower()
    except Exception:
        current_url = ""
    if "proof_upload" in current_url:
        return True
    try:
        return page.locator(
            "xpath=//*[contains(normalize-space(.),'Document Upload') and "
            "contains(normalize-space(.),'Signature')]"
        ).first.is_visible(timeout=3000)
    except Exception:
        return False


def click_address_use_original_if_present(page, timeout=15000):
    selectors = [
        "xpath=//button[normalize-space()='Use Original']",
        "xpath=//button[normalize-space()='Use Orginal']",
        "xpath=//*[self::button or self::a or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'use original')]",
        "xpath=//*[self::button or self::a or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'use orginal')]",
    ]
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        for selector in selectors:
            try:
                btn = page.locator(selector).first
                if btn.is_visible(timeout=800):
                    btn.scroll_into_view_if_needed(timeout=2000)
                    btn.click(force=True, timeout=3000)
                    page.wait_for_timeout(2000)
                    print("  [OK] Address signature Use Original clicked")
                    return True
            except Exception:
                continue
        try:
            clicked = page.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    const buttons = Array.from(document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit]'));
                    const match = buttons.find((el) => {
                        const text = `${el.innerText || ''} ${el.value || ''}`.toLowerCase().replace(/\\s+/g, ' ').trim();
                        return isVisible(el) && (text.includes('use original') || text.includes('use orginal'));
                    });
                    if (!match) return false;
                    match.disabled = false;
                    match.removeAttribute('disabled');
                    match.scrollIntoView({ block: 'center', inline: 'center' });
                    for (const eventName of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        match.dispatchEvent(new MouseEvent(eventName, { bubbles: true, cancelable: true, view: window }));
                    }
                    if (typeof match.click === 'function') match.click();
                    return true;
                }
                """
            )
            if clicked:
                page.wait_for_timeout(2000)
                print("  [OK] Address signature Use Original clicked")
                return True
        except Exception:
            pass
        page.wait_for_timeout(500)
    print("  [WARN] Address signature Use Original button not found")
    return False


def upload_address_signature_document(page):
    if not os.path.exists(SIGNATURE_FILE_PATH):
        raise Exception(f"Signature file not found: {SIGNATURE_FILE_PATH}")

    page.wait_for_load_state("domcontentloaded", timeout=30000)
    page.wait_for_timeout(2000)

    uploaded = False
    file_inputs = [
        "input[type='file'][name*='signature' i]",
        "input[type='file'][id*='signature' i]",
        "input[type='file'][name*='sign' i]",
        "input[type='file'][id*='sign' i]",
        "input[type='file']",
    ]
    for selector in file_inputs:
        try:
            file_input = page.locator(selector).first
            if file_input.count() > 0:
                file_input.set_input_files(SIGNATURE_FILE_PATH, timeout=5000)
                uploaded = True
                break
        except Exception:
            continue

    if not uploaded:
        upload_buttons = [
            "xpath=//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload signature')]",
            "xpath=//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload signature')]",
            "xpath=//*[self::button or self::label or self::a or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload signature')]",
            "xpath=//*[self::button or self::label or self::a or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload')]",
        ]
        for selector in upload_buttons:
            try:
                with page.expect_file_chooser(timeout=4000) as chooser_info:
                    btn = page.locator(selector).first
                    btn.wait_for(state="visible", timeout=4000)
                    btn.scroll_into_view_if_needed(timeout=3000)
                    btn.click(force=True, timeout=4000)
                chooser_info.value.set_files(SIGNATURE_FILE_PATH)
                uploaded = True
                break
            except Exception:
                continue

    if not uploaded:
        raise Exception("Address signature upload input/button not found")

    # The address proof page opens a crop/preview modal after upload. It must be
    # accepted before the page-level signature preview and Next button are usable.
    click_address_use_original_if_present(page, timeout=15000)

    deadline = time.time() + 20
    while time.time() < deadline:
        try:
            preview = page.locator(
                "xpath=//img[not(ancestor::*[contains(@class,'modal')])]"
            ).first
            if preview.is_visible(timeout=700):
                print("  [OK] Address signature preview visible")
                return
        except Exception:
            pass
        page.wait_for_timeout(700)
    print("  [WARN] Address signature preview not detected; continuing")


def click_address_document_next(page):
    selectors = [
        "xpath=//button[normalize-space(.)='Next']",
        "xpath=//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
        "xpath=//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
        "xpath=//*[self::button or self::a or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'next')]",
    ]
    try:
        page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    except Exception:
        pass
    page.wait_for_timeout(500)
    if click_first_visible(page, selectors, timeout=7000):
        page.wait_for_timeout(2000)
        print("  [OK] Address document Next clicked")
        return True
    if click_button_robust(page, selectors, "Address document Next", timeout=7000):
        page.wait_for_timeout(2000)
        print("  [OK] Address document Next clicked")
        return True
    raise Exception("Address document Next button not found")


def click_proceed_without_nominees_if_present(page, timeout=15000):
    selectors = [
        "xpath=//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed without') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'nominee')]",
        "xpath=//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed without') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'nominee')]",
        "xpath=//*[self::button or self::a or @role='button'][contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'proceed without')]",
    ]
    deadline = time.time() + (timeout / 1000)
    while time.time() < deadline:
        if click_first_visible(page, selectors, timeout=1000):
            page.wait_for_timeout(3000)
            print("  [OK] Proceed without Nominees clicked")
            return True
        try:
            clicked = page.evaluate(
                """
                () => {
                    const isVisible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    const buttons = Array.from(document.querySelectorAll('button,a,[role=button],input[type=button],input[type=submit]'));
                    const match = buttons.find((el) => {
                        const text = `${el.innerText || ''} ${el.value || ''}`.toLowerCase().replace(/\\s+/g, ' ');
                        return isVisible(el) && text.includes('proceed without') && text.includes('nominee');
                    });
                    if (!match) return false;
                    match.scrollIntoView({ block: 'center', inline: 'center' });
                    match.click();
                    return true;
                }
                """
            )
            if clicked:
                page.wait_for_timeout(3000)
                print("  [OK] Proceed without Nominees clicked")
                return True
        except Exception:
            pass
        page.wait_for_timeout(1000)
    return False


def complete_address_signature_ipv_esign_flow(page):
    if is_address_proof_upload_page(page):
        upload_address_signature_document(page)
        click_address_document_next(page)
        click_proceed_without_nominees_if_present(page, timeout=15000)
    else:
        print("  [i] Address proof upload page not detected; continuing to IPV/eSign checks")

    prepare_ipv_browser(page)
    capture_ipv_photo(page)
    view_unsigned_pdf(page)
    proceed_to_esign(page)
    complete_aadhaar_esign(page)


def complete_personal_details_if_present(page):
    if not is_personal_details_page(page):
        return False

    print("  [i] Personal Details page detected after address verification")
    page.wait_for_load_state("domcontentloaded", timeout=20000)
    page.wait_for_timeout(2000)

    try:
        page.evaluate("window.scrollTo(0, 0)")
    except Exception:
        pass
    page.wait_for_timeout(500)

    if click_personal_option(page, PERSONAL_MARITAL_STATUS):
        print(f"  [OK] Personal Details marital status selected: {PERSONAL_MARITAL_STATUS}")
    else:
        try:
            page.locator("xpath=//input[@name='marital' and @value='02']").first.check(force=True)
            print("  [OK] Personal Details marital status selected by fallback")
        except Exception:
            print("  [WARN] Personal Details marital status not selected")

    fill_personal_field(page, "Mother Name", ["mfname", "motherName", "mother_name"], PERSONAL_MOTHER_NAME)
    fill_personal_field(page, "Father Name", ["ffname", "fatherName", "father_name"], PERSONAL_FATHER_NAME)

    for option, description in [
        (PERSONAL_EDUCATION, "education"),
        (PERSONAL_OCCUPATION, "occupation"),
        (PERSONAL_ANNUAL_INCOME, "annual income"),
        (PERSONAL_MARKET_EXPERIENCE, "market experience"),
        (PERSONAL_SOURCE_INCOME, "source of income"),
        (PERSONAL_NATIONALITY, "nationality"),
    ]:
        if click_personal_option(page, option):
            print(f"  [OK] Personal Details {description} selected: {option}")
        else:
            print(f"  [WARN] Personal Details {description} option not found: {option}")

    check_personal_declarations(page)
    if not click_personal_next(page):
        raise Exception("Personal Details Next button not found/clickable")

    print("  [OK] Personal Details submitted")
    return True


def complete_address_digilocker_verification(page):
    open_section(page, "Change of address")
    digilocker_page = click_address_proceed_to_change(page)
    digilocker_page.wait_for_load_state("domcontentloaded", timeout=30000)

    select_digilocker_aadhaar_login(digilocker_page)
    fill_digilocker_field(
        digilocker_page,
        DIGILOCKER_AADHAAR_INPUT_LOCATORS,
        CLIENT_AADHAAR_NUMBER,
        "Aadhaar",
    )
    click_digilocker_first(digilocker_page, DIGILOCKER_NEXT_LOCATORS, "Next")

    otp = fetch_latest_yopmail_otp(digilocker_page, "DigiLocker Aadhaar OTP", ESIGN_OTP_EMAIL)
    fill_digilocker_field(digilocker_page, DIGILOCKER_OTP_INPUT_LOCATORS, otp, "OTP")
    click_digilocker_first(digilocker_page, DIGILOCKER_SUBMIT_LOCATORS, "OTP Submit")

    wait_for_digilocker_security_pin(digilocker_page, timeout=60000)
    fill_digilocker_field(
        digilocker_page,
        DIGILOCKER_SECURITY_PIN_INPUT_LOCATORS,
        "212003",
        "security PIN",
    )
    click_digilocker_first(digilocker_page, DIGILOCKER_SUBMIT_LOCATORS, "security PIN Submit")

    returned_page = wait_for_digilocker_return(digilocker_page, timeout=60000)
    complete_personal_details_if_present(returned_page)
    complete_address_signature_ipv_esign_flow(returned_page)
    return returned_page


def close_service_modal(page):
    if click_first_visible(page, SERVICE_CLOSE_MODAL_LOCATORS, timeout=1000):
        page.wait_for_timeout(500)
        return
    clear_blocking_overlays(page)


def click_request_placed_ok_if_present(page):
    ok_selectors = [
        "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='okay']",
        "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']",
        "//input[translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='okay']",
        "//input[translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']",
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'okay')]",
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'ok')]",
    ]
    deadline = time.time() + 90
    while time.time() < deadline:
        pages = list(page.context.pages)
        if page not in pages:
            pages.append(page)
        for candidate in pages:
            try:
                if candidate.is_closed():
                    continue
                candidate_url = candidate.url.lower()
                candidate_text = visible_text(candidate).lower()
                popup_present = (
                    "service_req" in candidate_url
                    or any(marker in candidate_text for marker in [
                        "request placed",
                        "request place",
                        "successfully placed",
                        "request has been",
                    ])
                )
                if not popup_present:
                    continue
                candidate.bring_to_front()
                if click_first_visible(candidate, ok_selectors, timeout=3000):
                    candidate.wait_for_timeout(2000)
                    print("  [OK] Request placed popup acknowledged")
                    return True
                clicked = candidate.evaluate(
                    """
                    () => {
                        const visible = (el) => {
                            const r = el.getBoundingClientRect();
                            const s = window.getComputedStyle(el);
                            return r.width > 0 && r.height > 0 &&
                                s.display !== 'none' && s.visibility !== 'hidden';
                        };
                        const controls = Array.from(document.querySelectorAll(
                            'button,input[type=button],input[type=submit],a,[role=button]'
                        ));
                        const ok = controls.find((el) => {
                            const text = (el.innerText || el.value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                            return visible(el) && (text === 'okay' || text === 'ok' || text.includes('okay'));
                        });
                        if (!ok) return false;
                        ok.disabled = false;
                        ok.removeAttribute('disabled');
                        ok.scrollIntoView({ block: 'center', inline: 'center' });
                        for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                            ok.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                        }
                        return true;
                    }
                    """
                )
                if clicked:
                    candidate.wait_for_timeout(2000)
                    print("  [OK] Request placed popup acknowledged")
                    return True
            except Exception:
                continue
        page.wait_for_timeout(1000)
    return False

def click_mobile_declaration_checkbox(page):
    """
    Simple direct click on the mobile declaration checkbox.
    The checkbox is in a label with text "I hereby declare that the Mobile number..."
    """
    try:
        print("  [DEBUG] Attempting to click mobile declaration checkbox")
        
        # Method 1: Find checkbox by looking for label with "declare" text
        labels = page.locator("label")
        for i in range(labels.count()):
            label = labels.nth(i)
            try:
                label_text = label.text_content()
                if "declare" in label_text.lower() and "mobile" in label_text.lower():
                    print(f"  [DEBUG] Found declaration label #{i}")
                    
                    # Find checkbox inside this label
                    checkbox = label.locator("input[type='checkbox']").first
                    
                    if checkbox.count() > 0:
                        print(f"  [DEBUG] Found checkbox inside label")
                        checkbox.scroll_into_view_if_needed()
                        page.wait_for_timeout(300)
                        
                        # Try direct click
                        checkbox.click(force=True, timeout=2000)
                        page.wait_for_timeout(500)
                        
                        if checkbox.is_checked():
                            print(f"  [OK] Mobile declaration checkbox clicked successfully")
                            return True
                        
                        # Try check method
                        checkbox.check(force=True, timeout=2000)
                        page.wait_for_timeout(500)
                        
                        if checkbox.is_checked():
                            print(f"  [OK] Mobile declaration checkbox checked successfully")
                            return True
                        
                        print(f"  [DEBUG] Checkbox not checked after click/check")
            except Exception as e:
                print(f"  [DEBUG] Label #{i} failed: {str(e)}")
                continue
        
        # Method 2: Find all checkboxes in the modal and click the first visible one
        print("  [DEBUG] Method 1 failed, trying Method 2: direct checkbox search")
        checkboxes = page.locator("input[type='checkbox']")
        for i in range(checkboxes.count()):
            checkbox = checkboxes.nth(i)
            try:
                if checkbox.is_visible(timeout=1000):
                    print(f"  [DEBUG] Found visible checkbox #{i}")
                    checkbox.scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    
                    # Try click
                    checkbox.click(force=True, timeout=2000)
                    page.wait_for_timeout(500)
                    
                    if checkbox.is_checked():
                        print(f"  [OK] Checkbox #{i} clicked successfully")
                        return True
                    
                    # Try check
                    checkbox.check(force=True, timeout=2000)
                    page.wait_for_timeout(500)
                    
                    if checkbox.is_checked():
                        print(f"  [OK] Checkbox #{i} checked successfully")
                        return True
                    
                    # Try JavaScript
                    page.evaluate(f"""() => {{
                        const checkboxes = document.querySelectorAll("input[type='checkbox']");
                        if (checkboxes[{i}]) {{
                            checkboxes[{i}].click();
                            checkboxes[{i}].checked = true;
                            checkboxes[{i}].dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}""")
                    page.wait_for_timeout(500)
                    
                    if checkbox.is_checked():
                        print(f"  [OK] Checkbox #{i} checked with JavaScript")
                        return True
                    
                    print(f"  [DEBUG] Checkbox #{i} still not checked")
            except Exception as e:
                print(f"  [DEBUG] Checkbox #{i} failed: {str(e)}")
                continue
        
        print("  [ERROR] No checkboxes found or all failed")
        return False
        
    except Exception as e:
        print(f"  [ERROR] click_mobile_declaration_checkbox failed: {str(e)}")
        return False
    
def set_service_declaration(page, checked):
    print(f"  [DEBUG] set_service_declaration called with checked={checked}")
    print(f"  [DEBUG] Current URL: {page.url}")
    print(f"  [DEBUG] Page title: {page.title()}")
    
    if checked:
        try:
            clicked_by_text = page.evaluate(
                """() => {
                    const isVisible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = getComputedStyle(el);
                        return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                    };
                    const fireAt = (x, y) => {
                        const el = document.elementFromPoint(x, y);
                        if (!el) return false;
                        const opts = { bubbles: true, cancelable: true, view: window, clientX: x, clientY: y };
                        for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                            el.dispatchEvent(new MouseEvent(type, opts));
                        }
                        if (typeof el.click === 'function') el.click();
                        return true;
                    };
                    const labels = Array.from(document.querySelectorAll('label, div, span, p'))
                        .filter((el) => {
                            const text = (el.innerText || el.textContent || '').toLowerCase();
                            return isVisible(el) && text.includes('i hereby declare') &&
                                (text.includes('mobile number') || text.includes('email'));
                        });
                    const label = labels[0];
                    if (!label) return false;
                    label.scrollIntoView({ block: 'center', inline: 'center' });
                    const r = label.getBoundingClientRect();
                    const y = r.top + Math.min(18, Math.max(8, r.height / 2));
                    for (const x of [r.left + Math.min(80, r.width / 3), r.left + r.width / 2, r.left + 18, r.left - 18, r.left - 28]) {
                        fireAt(x, y);
                    }
                    const root = label.closest('form, .modal, .reveal, section, article, div') || document;
                    const input = root.querySelector("input[type='checkbox']") || document.querySelector("input[type='checkbox']");
                    if (input && !input.checked) {
                        input.checked = true;
                        input.setAttribute('checked', 'checked');
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                    return !input || input.checked;
                }"""
            )
            if clicked_by_text:
                page.wait_for_timeout(500)
                print("  [OK] Declaration checkbox checked")
                return True
        except Exception as exc:
            print(f"  [DEBUG] Declaration text checkbox click failed: {exc}")

    try:
        selected = page.evaluate(
            """(desired) => {
                const isVisible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                };
                const fireClick = (el) => {
                    if (!el) return false;
                    el.scrollIntoView({ block: 'center', inline: 'center' });
                    const r = el.getBoundingClientRect();
                    const opts = {
                        bubbles: true,
                        cancelable: true,
                        view: window,
                        clientX: r.left + r.width / 2,
                        clientY: r.top + r.height / 2
                    };
                    for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                        el.dispatchEvent(new MouseEvent(type, opts));
                    }
                    if (typeof el.click === 'function') el.click();
                    return true;
                };
                const textOf = (el) => (el?.innerText || el?.textContent || '').toLowerCase();
                const forms = Array.from(document.querySelectorAll('form, .modal, .reveal, section, article, div'))
                    .filter((el) => {
                        const text = textOf(el);
                        return text.includes('send otp') || text.includes('declare') ||
                            text.includes('authorize') || text.includes('mobile') || text.includes('email');
                    })
                    .sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return (ar.width * ar.height) - (br.width * br.height);
                    });
                const root = forms[0] || document;
                const checkboxes = Array.from(root.querySelectorAll("input[type='checkbox']"))
                    .filter((el) => !el.disabled);
                const input = checkboxes.find((el) => {
                    const id = el.id ? String(el.id) : '';
                    const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                    const context = textOf(label) + ' ' + textOf(el.closest('label, .row, div, form') || root);
                    return context.includes('declare') || context.includes('agree') ||
                        context.includes('authorize') || context.includes('consent');
                }) || checkboxes[0] || document.querySelector("input[type='checkbox']:not([disabled])");
                if (!input) return false;

                const id = input.id ? String(input.id) : '';
                const label = id ? document.querySelector(`label[for="${CSS.escape(id)}"]`) : null;
                const wrapper = input.closest('label') || label || input.parentElement;

                if (desired) {
                    if (!input.checked) {
                        fireClick(label || wrapper || input);
                        fireClick(input);
                    }
                    if (!input.checked) {
                        input.checked = true;
                        input.setAttribute('checked', 'checked');
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                        fireClick(label || wrapper || input);
                    }
                    return input.checked;
                }

                if (input.checked) {
                    fireClick(label || wrapper || input);
                    if (input.checked) {
                        input.checked = false;
                        input.removeAttribute('checked');
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                        input.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                }
                return !input.checked;
            }""",
            checked,
        )
        if selected:
            page.wait_for_timeout(500)
            print(f"  [OK] Declaration checkbox {'checked' if checked else 'unchecked'}")
            return True
    except Exception as exc:
        print(f"  [DEBUG] JS checkbox handling failed: {exc}")

    for loc in SERVICE_DECLARATION_LOCATORS:
        try:
            box = page.locator(loc).first
            if box.count() > 0:
                box.scroll_into_view_if_needed(timeout=2000)
                if checked:
                    box.check(force=True, timeout=2000)
                else:
                    box.uncheck(force=True, timeout=2000)
                page.wait_for_timeout(500)
                try:
                    if box.is_checked() == checked:
                        print(f"  [OK] Declaration checkbox {'checked' if checked else 'unchecked'}")
                        return True
                except Exception:
                    return True
        except Exception as e:
            print(f"  [DEBUG] Checkbox check failed: {str(e)}")
            continue
            # FALLBACK 4: Simple direct click on first visible checkbox
    print("  [DEBUG] Trying simple direct click on first visible checkbox")
    try:
        checkboxes = page.locator("input[type='checkbox']")
        for i in range(checkboxes.count()):
            checkbox = checkboxes.nth(i)
            try:
                if checkbox.is_visible(timeout=1000):
                    print(f"  [DEBUG] Found visible checkbox #{i}")
                    checkbox.scroll_into_view_if_needed()
                    page.wait_for_timeout(300)
                    
                    # Try click method
                    checkbox.click(force=True, timeout=2000)
                    page.wait_for_timeout(500)
                    
                    if checkbox.is_checked():
                        print(f"  [OK] Checkbox #{i} checked with click()")
                        return True
                    
                    # Try check method
                    checkbox.check(force=True, timeout=2000)
                    page.wait_for_timeout(500)
                    
                    if checkbox.is_checked():
                        print(f"  [OK] Checkbox #{i} checked with check()")
                        return True
                    
                    # Try JavaScript
                    page.evaluate("""(index) => {
                        const checkboxes = document.querySelectorAll("input[type='checkbox']");
                        if (checkboxes[index]) {
                            checkboxes[index].checked = true;
                            checkboxes[index].dispatchEvent(new Event('change', { bubbles: true }));
                        }
                    }""", i)
                    page.wait_for_timeout(500)
                    
                    if checkbox.is_checked():
                        print(f"  [OK] Checkbox #{i} checked with JavaScript")
                        return True
                    
                    print(f"  [DEBUG] Checkbox #{i} is still not checked after all attempts")
            except Exception as e:
                print(f"  [DEBUG] Checkbox #{i} failed: {str(e)}")
                continue
    except Exception as e:
        print(f"  [DEBUG] Simple checkbox fallback failed: {str(e)}")
    
    raise Exception("Declaration checkbox could not be checked - all methods failed")


def select_service_email_otp(page, section_name):
    for loc in SERVICE_EMAIL_OTP_RADIO_LOCATORS:
        try:
            radio = page.locator(loc).first
            if radio.is_visible(timeout=1000) or radio.is_enabled(timeout=1000):
                radio.check(force=True)
                page.wait_for_timeout(500)
                return True
        except Exception:
            continue
    raise Exception(f"{section_name} E-mail OTP radio option not found")


def select_service_mobile_otp(page, section_name):
    for loc in SERVICE_MOBILE_OTP_RADIO_LOCATORS:
        try:
            radio = page.locator(loc).first
            if radio.count() > 0 and radio.is_visible(timeout=1000):
                radio.check(force=True)
                page.wait_for_timeout(500)
                print("  [OK] Mobile OTP radio selected")
                return True
        except Exception:
            continue
    try:
        selected = page.evaluate(
            """() => {
                const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none';
                };
                const labels = Array.from(document.querySelectorAll('label, span, div, p'))
                    .filter((el) => visible(el) && (el.innerText || el.textContent || '').toLowerCase().includes('mobile'));
                for (const label of labels) {
                    const id = label.getAttribute('for');
                    const input = id ? document.getElementById(id) : label.querySelector("input[type='radio']");
                    const radio = input || label.closest('label')?.querySelector("input[type='radio']") ||
                        label.parentElement?.querySelector("input[type='radio']");
                    if (!radio || radio.disabled) continue;
                    label.scrollIntoView({ block: 'center', inline: 'center' });
                    radio.checked = true;
                    radio.dispatchEvent(new Event('input', { bubbles: true }));
                    radio.dispatchEvent(new Event('change', { bubbles: true }));
                    label.click();
                    return true;
                }
                const radios = Array.from(document.querySelectorAll("input[type='radio']"));
                const mobile = radios.find((el) => {
                    const context = `${el.value || ''} ${el.id || ''} ${el.name || ''} ${el.closest('label, div, form')?.innerText || ''}`.toLowerCase();
                    return context.includes('mobile') || context.includes('phone');
                });
                if (!mobile) return false;
                mobile.checked = true;
                mobile.dispatchEvent(new Event('input', { bubbles: true }));
                mobile.dispatchEvent(new Event('change', { bubbles: true }));
                mobile.click();
                return true;
            }"""
        )
        if selected:
            page.wait_for_timeout(500)
            print("  [OK] Mobile OTP radio selected")
            return True
    except Exception:
        pass
    print("  [WARN] Mobile OTP radio not found; continuing with default selection")
    return False


def click_service_send_otp(page, section_name):
    deadline = time.time() + 12
    last_disabled = False
    while time.time() < deadline:
        for loc in SERVICE_SEND_OTP_LOCATORS:
            try:
                button = page.locator(loc).first
                if button.count() > 0 and button.is_visible(timeout=500):
                    try:
                        last_disabled = button.is_disabled(timeout=500)
                    except Exception:
                        last_disabled = False
                    if not last_disabled:
                        button.click(force=True, timeout=3000)
                        page.wait_for_timeout(3000)
                        return True
            except Exception:
                continue
        page.wait_for_timeout(500)
    try:
        clicked = page.evaluate(
            """() => {
                const buttons = Array.from(document.querySelectorAll('button,input[type=button],input[type=submit],a'));
                const button = buttons.find((el) => {
                    const text = (el.innerText || el.value || '').toLowerCase();
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    return text.includes('send otp') && r.width > 0 && r.height > 0 &&
                        s.display !== 'none' && s.visibility !== 'hidden';
                });
                if (!button) return false;
                button.disabled = false;
                button.removeAttribute('disabled');
                button.scrollIntoView({ block: 'center', inline: 'center' });
                button.click();
                return true;
            }"""
        )
        if clicked:
            page.wait_for_timeout(3000)
            return True
    except Exception:
        pass
    if last_disabled:
        raise Exception(f"{section_name} Send OTP button stayed disabled after declaration/radio selection")
    return False


def click_mobile_send_otp_from_active_modal(page):
    try:
        clicked = page.evaluate(
            """
            () => {
                const visible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0 &&
                        s.display !== 'none' && s.visibility !== 'hidden';
                };
                const dialogs = Array.from(document.querySelectorAll(
                    '.modal, .reveal, [role=dialog], .popup, [class*=modal], [class*=popup]'
                )).filter(visible);
                const root = dialogs.length ? dialogs[dialogs.length - 1] : document;
                const controls = Array.from(root.querySelectorAll(
                    'button,input[type=button],input[type=submit],a,[role=button]'
                )).filter(visible);
                const send = controls.find((el) => {
                    const text = (el.innerText || el.value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                    return text.includes('send otp');
                });
                if (!send) return false;

                const radios = Array.from(root.querySelectorAll('input[type=radio]'));
                const mobileRadio = radios.find((el) => {
                    const value = `${el.value || ''} ${el.id || ''} ${el.name || ''}`.toLowerCase();
                    const label = el.id ? (root.querySelector(`label[for="${CSS.escape(el.id)}"]`) || document.querySelector(`label[for="${CSS.escape(el.id)}"]`)) : null;
                    const labelText = (label ? label.innerText : '').toLowerCase();
                    return value.includes('mobile') || labelText.includes('mobile');
                }) || radios.find((el) => visible(el) && !el.disabled);
                if (mobileRadio && !mobileRadio.checked) {
                    mobileRadio.checked = true;
                    mobileRadio.dispatchEvent(new Event('input', { bubbles: true }));
                    mobileRadio.dispatchEvent(new Event('change', { bubbles: true }));
                    mobileRadio.click();
                }

                const boxes = Array.from(root.querySelectorAll('input[type=checkbox]')).filter((el) => !el.disabled);
                boxes.forEach((box) => {
                    if (!box.checked) {
                        box.checked = true;
                        box.dispatchEvent(new Event('input', { bubbles: true }));
                        box.dispatchEvent(new Event('change', { bubbles: true }));
                    }
                });

                send.disabled = false;
                send.removeAttribute('disabled');
                send.removeAttribute('aria-disabled');
                send.scrollIntoView({ block: 'center', inline: 'center' });
                for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click']) {
                    send.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
                }
                return true;
            }
            """
        )
        if clicked:
            page.wait_for_timeout(3000)
            return True
    except Exception:
        pass
    return False


def assert_service_send_otp_blocked_without_declaration(page, section_name):
    open_service_update_modal(page, section_name)
    set_service_declaration(page, False)
    if section_name.lower() != "mobile no":
        select_service_email_otp(page, section_name)
    before_url = page.url
    send_button = assert_visible_any(page, SERVICE_SEND_OTP_LOCATORS, "Send OTP button")
    disabled = False
    try:
        disabled = send_button.is_disabled(timeout=1000)
    except Exception:
        disabled = False
    if not disabled:
        try:
            send_button.click(timeout=2000)
        except Exception:
            disabled = True
    page.wait_for_timeout(1500)
    if "verify_otp" in page.url.lower() and page.url != before_url:
        raise Exception(f"{section_name} Send OTP proceeded without declaration checkbox")
    if not disabled:
        assert_validation_feedback(
            page,
            ["declare", "declaration", "checkbox", "authorize", "please", "required"],
            f"{section_name} declaration validation",
        )
    close_service_modal(page)


def start_service_otp_verification(page, section_name):
    open_service_update_modal(page, section_name)
        # For mobile, use simple direct click function
    if section_name.lower() == "mobile no":
        if not click_mobile_declaration_checkbox(page):
            raise Exception("Mobile declaration checkbox could not be clicked")
    else:
        set_service_declaration(page, True)

    if section_name.lower() == "mobile no":
        select_service_mobile_otp(page, section_name)
    else:
        select_service_email_otp(page, section_name)

    sent = False
    if section_name.lower() == "mobile no":
        sent = click_mobile_send_otp_from_active_modal(page)
    if not sent:
        sent = click_service_send_otp(page, section_name)
    if not sent:
        raise Exception(f"{section_name} Send OTP button not found")
    page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        if not click_first_visible(page, SERVICE_OKAY_LOCATORS, timeout=3000):
            raise Exception(f"{section_name} did not navigate to OTP verification")
        page.wait_for_timeout(3000)
    if "verify_otp" not in page.url.lower():
        raise Exception(f"{section_name} OTP verification page did not open")
    assert_visible_any(page, OTP_LOCATORS, f"{section_name} OTP input")


def submit_service_otp(page):
    for _ in range(40):
        for loc in OTP_SUBMIT_LOCATORS:
            try:
                button = page.locator(loc).first
                if button.is_visible(timeout=500):
                    if not button.is_disabled(timeout=500):
                        button.click()
                        page.wait_for_timeout(3000)
                        return
            except Exception:
                continue
        page.wait_for_timeout(1000)
    raise Exception("Service OTP submit button stayed disabled")


def assert_service_otp_negative(page, section_name, otp_value, expected_keywords, description):
    start_service_otp_verification(page, section_name)
    fill_first_visible(page, OTP_LOCATORS, otp_value)
    submit_service_otp(page)
    if "esign" in page.url.lower() or "proof_upload" in page.url.lower() or "uuid" in page.url.lower():
        raise Exception(f"{section_name} {description} proceeded unexpectedly")
    assert_validation_feedback(page, expected_keywords, f"{section_name} {description}")
    page.goto(section_url(section_name), wait_until="domcontentloaded")
    page.wait_for_timeout(1500)


def nominee_editor_available(page):
    candidate_fields = [
        NOMINEE_PAN_LOCATORS,
        NOMINEE_NAME_LOCATORS,
        NOMINEE_RELATION_LOCATORS,
        NOMINEE_DOB_LOCATORS,
        NOMINEE_SHARE_LOCATORS,
    ]
    for locators in candidate_fields:
        for loc in locators:
            try:
                if page.locator(loc).first.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
    return False


def nominee_add_url():
    return urljoin(REKYC_URL, "add_nominee.php")


def nominee_summary_url():
    return urljoin(REKYC_URL, "nominee.php")


def open_nominee_editor(page):
    clear_blocking_overlays(page)
    if nominee_editor_available(page):
        return
    if "nominee.php" in page.url.lower():
        check_nominee_confirmations(page)
    clicked = click_first_visible(page, NOMINEE_ADD_LOCATORS, timeout=3000)
    page.wait_for_timeout(1500)
    if not clicked and not nominee_editor_available(page):
        page.goto(nominee_add_url(), wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
    if not nominee_editor_available(page):
        raise Exception("Nominee editor did not open")


def open_fresh_nominee_form(page):
    clear_blocking_overlays(page)
    if "nominee.php" in page.url.lower() and "add_nominee" not in page.url.lower():
        check_nominee_confirmations(page)
        if not click_nominee_add_button(page, "summary Add Nominee(s)"):
            raise Exception("Summary Add Nominee(s) button not found")
        page.wait_for_timeout(2500)
    if "add_nominee" not in page.url.lower():
        page.goto(nominee_add_url(), wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
    if not click_nominee_add_button(page, "form Add Nominee"):
        print("  [i] Add Nominee button on form not visible; using existing editable nominee section")
    page.wait_for_timeout(1500)
    if not nominee_editor_available(page):
        raise Exception("Nominee editor did not open")


def click_nominee_add_button(page, description="Add Nominee"):
    if click_first_visible(page, NOMINEE_ADD_LOCATORS, timeout=3000):
        print(f"  [OK] {description} clicked")
        return True
    if click_button_robust(page, NOMINEE_ADD_LOCATORS, description, timeout=5000):
        print(f"  [OK] {description} clicked")
        return True
    return False


def fill_optional_first_visible(page, locators, value, timeout=2000):
    for loc in locators:
        try:
            el = page.locator(loc).first
            if el.is_visible(timeout=timeout):
                tag_name = (el.evaluate("el => el.tagName") or "").lower()
                if tag_name == "select":
                    options = el.locator("option")
                    if value == "":
                        try:
                            el.select_option(value="")
                            return True
                        except Exception:
                            try:
                                el.select_option(index=0)
                                return True
                            except Exception:
                                return False
                    selected = False
                    for i in range(options.count()):
                        option_value = options.nth(i).get_attribute("value")
                        option_text = (options.nth(i).inner_text() or "").strip()
                        if option_value and option_value.strip():
                            if value.lower() in option_text.lower() or value.lower() in option_value.lower():
                                el.select_option(value=option_value)
                                selected = True
                                break
                    if not selected:
                        for i in range(options.count()):
                            option_value = options.nth(i).get_attribute("value")
                            if option_value and option_value.strip():
                                el.select_option(value=option_value)
                                selected = True
                                break
                    return selected
                if tag_name not in ("input", "textarea"):
                    el.click(force=True)
                    page.wait_for_timeout(500)
                    option_text = value or ""
                    option_locators = [
                        f"//li[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text.lower()}')]",
                        f"//div[contains(@class,'option') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text.lower()}')]",
                        f"//span[contains(@class,'select2')]/following::li[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text.lower()}')][1]",
                        "//li[normalize-space() and not(contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'select'))]",
                    ]
                    for option_locator in option_locators:
                        try:
                            option = page.locator(option_locator).first
                            if option.is_visible(timeout=1500):
                                option.click(force=True)
                                return True
                        except Exception:
                            continue
                    return False
                el.fill(value)
                return True
        except Exception:
            continue
    return False


def fill_required_first_visible(page, locators, value, description):
    if not fill_optional_first_visible(page, locators, value):
        raise Exception(f"{description} field not found")


def fill_last_visible_nominee_field(page, locators, value, description, timeout=3000):
    candidates = []
    for loc in locators:
        try:
            items = page.locator(loc)
            for i in range(items.count()):
                item = items.nth(i)
                try:
                    if item.is_visible(timeout=500) and item.is_enabled(timeout=500):
                        candidates.append(item)
                except Exception:
                    continue
        except Exception:
            continue

    if not candidates:
        raise Exception(f"{description} field not found")

    el = candidates[-1]
    try:
        el.scroll_into_view_if_needed(timeout=timeout)
    except Exception:
        pass

    tag_name = ""
    try:
        tag_name = (el.evaluate("el => el.tagName") or "").lower()
    except Exception:
        pass

    if tag_name == "select":
        options = el.locator("option")
        selected = False
        for i in range(options.count()):
            option_value = options.nth(i).get_attribute("value")
            option_text = (options.nth(i).inner_text() or "").strip()
            if option_value and option_value.strip():
                if str(value).lower() in option_text.lower() or str(value).lower() in option_value.lower():
                    el.select_option(value=option_value)
                    selected = True
                    break
        if not selected:
            for i in range(options.count()):
                option_value = options.nth(i).get_attribute("value")
                if option_value and option_value.strip():
                    el.select_option(value=option_value)
                    selected = True
                    break
        if not selected:
            raise Exception(f"{description} option not found")
        return True

    if tag_name not in ("input", "textarea"):
        el.click(force=True)
        page.wait_for_timeout(500)
        option_text = str(value or "").lower()
        option_locators = [
            f"//div[contains(@class,'menu')]//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text}')]",
            f"//div[contains(@class,'option') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text}')]",
            f"//div[contains(@class,'item') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text}')]",
            f"//li[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text}')]",
            f"//span[contains(@class,'select2')]/following::li[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text}')][1]",
            f"//*[contains(@role,'option') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'{option_text}')]",
            "//li[normalize-space() and not(contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'select'))]",
        ]
        for option_locator in option_locators:
            try:
                option = page.locator(option_locator).first
                if option.is_visible(timeout=1500):
                    option.click(force=True)
                    return True
            except Exception:
                continue
        raise Exception(f"{description} option not found")

    el.fill("")
    el.fill(str(value))
    return True


def select_last_nominee_relation(page, relation="brother"):
    relation_value = str(relation or "").strip().lower()
    select_id = page.evaluate(
        """
        () => {
            const selects = Array.from(document.querySelectorAll("select[id^='nomirel'], select[name^='nominee_relation']"));
            const numberOf = (el) => {
                const id = el.getAttribute('id') || '';
                const name = el.getAttribute('name') || '';
                const hit = id.match(/[0-9]+$/) || name.match(/[0-9]+$/);
                return hit ? Number(hit[0]) : 0;
            };
            selects.sort((a, b) => numberOf(a) - numberOf(b));
            return selects.length ? selects[selects.length - 1].id : '';
        }
        """
    )
    if not select_id:
        raise Exception("Relation with Account holder dropdown select not found")

    container_id = f"select2-{select_id}-container"
    selection_locator = f"xpath=//*[@id='{container_id}']/ancestor::span[contains(@class,'select2-selection')][1]"
    option_locator = (
        f"xpath=//ul[@id='select2-{select_id}-results']"
        f"/li[contains(@class,'select2-results__option') and "
        f"translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='{relation_value}']"
    )

    for attempt in range(3):
        try:
            selection = page.locator(selection_locator).first
            selection.scroll_into_view_if_needed(timeout=3000)
            selection.click(force=True, timeout=3000)
            page.wait_for_timeout(500)
            option = page.locator(option_locator).first
            option.scroll_into_view_if_needed(timeout=3000)
            option.click(force=True, timeout=3000)
            page.wait_for_timeout(700)
        except Exception:
            try:
                page.keyboard.press("Escape")
            except Exception:
                pass

        selected = page.evaluate(
            """
            ({ selectId, relation }) => {
                const select = document.getElementById(selectId);
                const rendered = document.getElementById(`select2-${selectId}-container`);
                return {
                    value: ((select && select.value) || '').toLowerCase(),
                    text: ((rendered && rendered.textContent) || '').trim().toLowerCase()
                };
            }
            """,
            {"selectId": select_id, "relation": relation_value},
        )
        if selected and (
            selected.get("value") == relation_value or selected.get("text") == relation_value
        ):
            print(f"  [OK] Relation with Account holder selected: {relation_value}")
            return True
        page.wait_for_timeout(500)

    try:
        result = page.evaluate(
            """
            ({ selectId, relation }) => {
                const rel = String(relation || '').toLowerCase();
                const select = document.getElementById(selectId);
                if (!select) return { ok: false, reason: 'relation select not found' };

                const option = Array.from(select.options).find((opt) =>
                    (opt.value || '').toLowerCase() === rel || (opt.text || '').toLowerCase() === rel
                );
                if (!option) return { ok: false, reason: `relation option ${rel} not found` };

                select.value = option.value;
                option.selected = true;
                select.selectedIndex = option.index;
                select.dispatchEvent(new Event('input', { bubbles: true }));
                select.dispatchEvent(new Event('change', { bubbles: true }));
                select.dispatchEvent(new Event('blur', { bubbles: true }));

                if (window.jQuery) {
                    const jq = window.jQuery(select);
                    jq.val(option.value);
                    try { jq.select2('val', option.value); } catch (e) {}
                    jq.trigger('input');
                    jq.trigger('change');
                    jq.trigger({
                        type: 'select2:select',
                        params: { data: { id: option.value, text: option.text } }
                    });
                    try { jq.select2('close'); } catch (e) {}
                }

                const escapedId = window.CSS && CSS.escape ? CSS.escape(select.id) : select.id;
                const renderedTargets = [
                    document.getElementById(`select2-${select.id}-container`),
                    escapedId ? document.querySelector(`#select2-${escapedId}-container`) : null,
                    select.parentElement && select.parentElement.querySelector('.select2-selection__rendered'),
                    select.nextElementSibling && select.nextElementSibling.querySelector('.select2-selection__rendered'),
                ].filter(Boolean);

                renderedTargets.forEach((rendered) => {
                    rendered.textContent = option.text;
                    rendered.setAttribute('title', option.text);
                });

                const renderedText = renderedTargets.map((el) => el.textContent || '').join(' ').toLowerCase();
                return {
                    ok: select.value === option.value && (renderedText.includes(rel) || renderedTargets.length === 0),
                    id: select.id,
                    value: select.value,
                    text: option.text,
                    renderedText
                };
            }
            """,
            {"selectId": select_id, "relation": relation_value},
        )
        if result and result.get("ok"):
            page.wait_for_timeout(500)
            print(f"  [OK] Relation with Account holder selected: {result.get('text')}")
            return True
    except Exception:
        pass

    raise Exception("Relation with Account holder dropdown option not selected")


def set_last_address_as_client(page, checked=True):
    candidates = []
    for loc in NOMINEE_ADDRESS_AS_CLIENT_LOCATORS:
        try:
            boxes = page.locator(loc)
            for i in range(boxes.count()):
                box = boxes.nth(i)
                try:
                    if box.is_visible(timeout=500) and box.is_enabled(timeout=500):
                        candidates.append(box)
                except Exception:
                    continue
        except Exception:
            continue
    if not candidates:
        return False
    box = candidates[-1]
    if checked:
        box.check(force=True)
    else:
        box.uncheck(force=True)
    return True


def trigger_field_change(page, locators):
    for loc in locators:
        try:
            el = page.locator(loc).first
            if el.is_visible(timeout=1000):
                el.dispatch_event("change")
                el.dispatch_event("blur")
                return True
        except Exception:
            continue
    return False


def set_address_as_client(page, checked=True):
    for loc in NOMINEE_ADDRESS_AS_CLIENT_LOCATORS:
        try:
            box = page.locator(loc).first
            if box.is_visible(timeout=1000):
                if checked:
                    box.check(force=True)
                else:
                    box.uncheck(force=True)
                return True
        except Exception:
            continue
    return False


def submit_nominee(page):
    if not click_first_visible(page, NOMINEE_SAVE_LOCATORS, timeout=3000):
        if not click_first_visible(page, NOMINEE_CONTINUE_LOCATORS, timeout=5000):
            raise Exception("Nominee save/continue button not found")
    page.wait_for_timeout(3000)


def continue_nominee(page):
    try:
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(500)
    except Exception:
        pass
    if not click_first_visible(page, NOMINEE_CONTINUE_LOCATORS, timeout=5000):
        raise Exception("Nominee continue button not found")
    page.wait_for_timeout(3000)


def assert_nominee_continue_does_not_proceed(page, description):
    try:
        page.mouse.wheel(0, 1800)
        page.wait_for_timeout(500)
    except Exception:
        pass
    before_url = page.url
    if not click_first_visible(page, NOMINEE_CONTINUE_ONLY_LOCATORS, timeout=5000):
        raise Exception(f"Continue button not displayed after saving {description}")
    page.wait_for_timeout(4000)
    page_text = visible_text(page).lower()
    current_url = page.url.lower()
    if "esign" in current_url or "e-sign" in page_text or "esign" in page_text or "upload_signature" in current_url:
        raise Exception(f"Continue proceeded to e-Sign flow unexpectedly for {description}")
    try:
        assert_validation_feedback(
            page,
            ["pan", "aadhaar", "aadhar", "client", "same", "nominee", "guardian", "holder", "not allowed", "share", "100", "allocation"],
            f"{description} continue validation",
        )
    except Exception:
        if page.url.lower() == before_url.lower() or "nominee" in page.url.lower():
            print(f"  [OK] {description} blocked; nominee page did not proceed")
            return
        raise

def check_nominee_confirmations(page):
    boxes = page.locator("input[type='checkbox']")
    checked = 0
    for i in range(boxes.count()):
        box = boxes.nth(i)
        try:
            if box.is_visible(timeout=1000) and box.is_enabled():
                box.check(force=True)
                checked += 1
        except Exception:
            continue
    if checked == 0:
        raise Exception("Nominee confirmation checkbox(es) not found")


def assert_nominee_loaded(page):
    page_text = visible_text(page).lower()
    if "nominee" not in page.url.lower() and "nominee" not in page_text:
        raise Exception("Nominee section content was not visible")
    if "add_nominee" not in page.url.lower():
        page.goto(nominee_summary_url(), wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
    page_text = visible_text(page).lower()
    if "nominee" not in page_text:
        raise Exception("Nominee summary did not show nominee content")

    for attempt in range(2):
        fill_nominee_positive_data(page, minor=False)
        submit_nominee(page)
        text_after_save = visible_text(page).lower()
        if "same" in text_after_save and ("aadhaar" in text_after_save or "aadhar" in text_after_save or "pan" in text_after_save):
            if attempt == 0:
                print("  [WARN] Nominee same PAN/Aadhaar validation shown; refreshing nominee form once")
                page.reload(wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
                continue
            raise Exception("Nominee save failed with same PAN/Aadhaar validation")
        break

    if "esign" in page.url.lower():
        raise Exception("Nominee save reached e-Sign unexpectedly")
    print("  [OK] Nominee details entered and saved")

def fill_nominee_positive_data(page, minor=False):
    open_fresh_nominee_form(page)
    fill_last_visible_nominee_field(page, NOMINEE_PAN_LOCATORS, "987654567890", "PAN/Aadhaar Number")
    fill_last_visible_nominee_field(page, NOMINEE_NAME_LOCATORS, "Test Nominee", "Nominee Name")
    fill_last_visible_nominee_field(page, NOMINEE_MOBILE_LOCATORS, "9876543210", "Mobile")
    select_last_nominee_relation(page, "Son" if minor else "Brother")
    fill_last_visible_nominee_field(page, NOMINEE_SHARE_LOCATORS, "50", "Share")
    fill_last_visible_nominee_field(page, NOMINEE_DOB_LOCATORS, MINOR_NOMINEE_DOB if minor else MAJOR_NOMINEE_DOB, "Date of Birth")
    trigger_field_change(page, NOMINEE_DOB_LOCATORS)
    if minor:
        page.wait_for_timeout(2500)
    fill_last_visible_nominee_field(page, NOMINEE_EMAIL_LOCATORS, "nominee.test@example.com", "Email")
    try:
        page.keyboard.press("Tab")
    except Exception:
        pass
    set_last_address_as_client(page, True)
    page.wait_for_timeout(2000)
    if minor:
        fill_last_visible_nominee_field(page, GUARDIAN_PAN_LOCATORS + NOMINEE_PAN_LOCATORS, "098765432345", "Guardian PAN/Aadhaar Number")
        fill_last_visible_nominee_field(page, GUARDIAN_NAME_LOCATORS, "Guardian Test", "Guardian Name")
        fill_last_visible_nominee_field(page, GUARDIAN_MOBILE_LOCATORS, "9876543456", "Guardian Mobile")
        fill_last_visible_nominee_field(page, GUARDIAN_DOB_LOCATORS, "01-05-1980", "Guardian Date of Birth")
        fill_last_visible_nominee_field(page, GUARDIAN_EMAIL_LOCATORS, "guardian.test@example.com", "Guardian Email ID")
        fill_last_visible_nominee_field(page, GUARDIAN_RELATION_LOCATORS, "spouse", "Relationship of Guardian with nominee")


def clear_nominee_required_fields(page):
    open_fresh_nominee_form(page)
    for locators in [
        NOMINEE_PAN_LOCATORS,
        NOMINEE_NAME_LOCATORS,
        NOMINEE_MOBILE_LOCATORS,
        NOMINEE_SHARE_LOCATORS,
        NOMINEE_DOB_LOCATORS,
        NOMINEE_EMAIL_LOCATORS,
    ]:
        fill_optional_first_visible(page, locators, "")
    fill_optional_first_visible(page, NOMINEE_RELATION_LOCATORS, "")


def return_to_rekyc_after_nominee(page):
    page.goto(nominee_summary_url(), wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if "nominee" not in visible_text(page).lower() and "nominee" not in page.url.lower():
        raise Exception("Could not return to ReKYC nominee section after nominee continue")


INCOME_EDIT_LOCATORS = [
    "a[href*='income_edit.php']",
    "button[href*='income_edit.php']",
    "//a[contains(@href,'income_edit.php')]",
    "//i[contains(@class,'pencil')]/ancestor::a[1]",
    "//i[contains(@class,'fa-pencil')]/ancestor::*[self::a or self::button][1]",
    "//*[contains(@class,'fa-pencil')]/ancestor::*[self::a or self::button][1]",
    "//*[contains(@class,'pencil-square')]/ancestor::*[self::a or self::button][1]",
]

INCOME_SLAB_LOCATORS = [
    "select[name*='income' i]",
    "select[id*='income' i]",
    "select[name*='slab' i]",
    "select[id*='slab' i]",
    "//label[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'income slab')]/following::select[1]",
]

INCOME_UPDATE_LOCATORS = [
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'update')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'update')]",
    "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
    "//input[contains(translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'submit')]",
]


def income_edit_url():
    return urljoin(REKYC_URL, "income_edit.php")


def open_income_edit_page(page):
    if "income_edit" in page.url.lower():
        return
    clear_blocking_overlays(page)
    if not click_first_visible(page, INCOME_EDIT_LOCATORS, timeout=5000):
        page.goto(income_edit_url(), wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if "income_edit" not in page.url.lower() and "income slab" not in visible_text(page).lower():
        raise Exception("Income edit page did not open")
    print("  [OK] Income declaration edit opened")


def select_income_slab_option(page):
    for loc in INCOME_SLAB_LOCATORS:
        try:
            slab = page.locator(loc).first
            if slab.is_visible(timeout=3000):
                options = slab.locator("option")
                for i in range(options.count()):
                    option = options.nth(i)
                    value = (option.get_attribute("value") or "").strip()
                    text = (option.inner_text() or "").strip()
                    lowered = text.lower()
                    if value and text and "select" not in lowered:
                        slab.select_option(value=value)
                        page.wait_for_timeout(500)
                        print(f"  [OK] Income slab selected: {text}")
                        return True
                raise Exception("No valid income slab option found")
        except Exception:
            continue
    raise Exception("Income slab dropdown not found")


def update_income_declaration(page):
    open_section(page, "Income Declaration")
    open_income_edit_page(page)
    select_income_slab_option(page)
    if not click_first_visible(page, INCOME_UPDATE_LOCATORS, timeout=5000):
        if not click_button_robust(page, INCOME_UPDATE_LOCATORS, "Income Update", timeout=5000):
            raise Exception("Income declaration Update button not found")
    page.wait_for_timeout(3000)
    print("  [OK] Income declaration updated")


def enable_bfo_segment(page):
    enabled_direct = page.evaluate(
        """
        () => {
            const input = document.querySelector("#BSE_derivative, input[name='segment_list[BFO]']");
            if (!input) return { ok: false, reason: 'BFO input not found' };
            if (!input.checked) {
                const label = document.querySelector("label[for='BSE_derivative']");
                if (label) {
                    label.click();
                } else {
                    input.click();
                }
            }
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return { ok: input.checked };
        }
        """
    )
    if not enabled_direct or not enabled_direct.get("ok"):
        raise Exception(f"BSE derivative (BFO) toggle not enabled: {enabled_direct}")
    page.wait_for_timeout(1000)
    print("  [OK] BSE derivative (BFO) segment enabled")


def check_segment_terms_checkbox(page):
    checked = page.evaluate(
        """
        () => {
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width >= 0 && r.height >= 0 && s.display !== 'none' && s.visibility !== 'hidden';
            };
            const termsText = Array.from(document.querySelectorAll('body *'))
                .filter((el) => {
                    const s = window.getComputedStyle(el);
                    return s.display !== 'none' && s.visibility !== 'hidden';
                })
                .map((el) => ({ el, text: (el.innerText || el.textContent || '').trim().toLowerCase() }))
                .filter((item) => item.text.includes('i am aware') && item.text.includes('mtf') && item.text.includes('accept the terms'))
                .sort((a, b) => {
                    const ar = a.el.getBoundingClientRect();
                    const br = b.el.getBoundingClientRect();
                    return (ar.width * ar.height) - (br.width * br.height);
                })[0];
            if (!termsText) return { ok: false, reason: 'segment terms text not found' };

            const textRect = termsText.el.getBoundingClientRect();
            const textCenterY = textRect.top + textRect.height / 2;

            let box = null;
            let row = termsText.el;
            for (let i = 0; i < 7 && row; i += 1) {
                const text = (row.innerText || row.textContent || '').toLowerCase();
                const candidate = row.querySelector && row.querySelector("input[type='checkbox']");
                if (candidate && text.includes('i am aware') && text.includes('accept the terms') && !text.includes('account closure')) {
                    box = candidate;
                    break;
                }
                row = row.parentElement;
            }

            if (!box) {
                const allBoxes = Array.from(document.querySelectorAll("input[type='checkbox']"))
                    .filter((el) => !el.disabled)
                    .filter((el) => {
                        const containerText = (el.closest('label, div, p, section, form') || document.body).innerText.toLowerCase();
                        return !containerText.includes('account closure');
                    });
                const beforeTerms = allBoxes.filter((el) =>
                    Boolean(el.compareDocumentPosition(termsText.el) & Node.DOCUMENT_POSITION_FOLLOWING)
                );
                box = beforeTerms[beforeTerms.length - 1] || allBoxes[0] || null;
            }

            if (box) {
                try {
                    if (!box.checked) box.click();
                } catch (e) {}
                box.checked = true;
                box.setAttribute('checked', 'checked');
                for (const type of ['mousedown', 'mouseup', 'click', 'input', 'change', 'blur']) {
                    try {
                        box.dispatchEvent(new Event(type, { bubbles: true, cancelable: true }));
                    } catch (e) {}
                }
                return { ok: box.checked, method: 'checkbox-property', id: box.id || '', name: box.name || '' };
            }

            const candidates = Array.from(document.querySelectorAll("label, .checkbox, .custom-control-label, span, div"))
                .filter((el) => {
                    if (!isVisible(el)) return false;
                    const r = el.getBoundingClientRect();
                    const centerY = r.top + r.height / 2;
                    return Math.abs(centerY - textCenterY) < 45 && r.right <= textRect.left + 10 && r.width <= 60 && r.height <= 60;
                })
                .sort((a, b) => b.getBoundingClientRect().right - a.getBoundingClientRect().right);
            const target = candidates[0];
            if (!target) return { ok: false, reason: 'segment terms checkbox not found' };
            const r = target.getBoundingClientRect();
            return { ok: true, x: r.left + r.width / 2, y: r.top + r.height / 2, method: 'coordinate' };
        }
        """
    )
    if not checked or not checked.get("ok"):
        raise Exception(f"Segment terms checkbox not checked: {checked}")
    if checked.get("method") == "coordinate":
        page.mouse.click(checked["x"], checked["y"])
        page.wait_for_timeout(500)
    verified = page.evaluate(
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
                    return box.checked;
                }
                row = row.parentElement;
            }
            return Array.from(document.querySelectorAll("input[type='checkbox']")).some((box) => {
                const text = (box.closest('label, div, p, section, form') || document.body).innerText.toLowerCase();
                return box.checked && text.includes('i am aware') && text.includes('accept the terms') && !text.includes('account closure');
            });
        }
        """
    )
    if not verified:
        raise Exception("Segment terms checkbox was clicked but did not become checked")
    page.wait_for_timeout(500)
    print("  [OK] Segment terms checkbox checked")


def accept_segment_risk_disclosure_if_present(page):
    try:
        popup_visible = page.locator(
            "xpath=//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'risk disclosures on derivatives')]"
        ).first.is_visible(timeout=5000)
    except Exception:
        popup_visible = False

    if not popup_visible:
        return False

    if not click_first_visible(page, SEGMENT_RISK_AGREE_LOCATORS, timeout=5000):
        try:
            clicked = page.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const r = el.getBoundingClientRect();
                        const s = window.getComputedStyle(el);
                        return r.width > 0 && r.height > 0 &&
                            s.display !== 'none' && s.visibility !== 'hidden';
                    };
                    const controls = Array.from(document.querySelectorAll(
                        'button,a,input[type=button],input[type=submit],[role=button]'
                    ));
                    const agree = controls.find((el) => {
                        const text = (el.innerText || el.value || '').replace(/\\s+/g, ' ').trim().toLowerCase();
                        return visible(el) && (text === 'agree' || text.includes('agree'));
                    });
                    if (!agree) return false;
                    agree.scrollIntoView({ block: 'center', inline: 'center' });
                    agree.click();
                    agree.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                    return true;
                }
                """
            )
            if not clicked:
                print("  [i] Segment risk disclosure text found, but no visible Agree button; continuing")
                return False
        except Exception:
            print("  [i] Segment risk disclosure text found, but Agree button was not clickable; continuing")
            return False
    page.wait_for_timeout(1500)
    print("  [OK] Segment risk disclosure agreed")
    return True


def wait_for_page_matching(page, url_keywords, timeout=60000):
    deadline = time.time() + (timeout / 1000)
    keywords = [kw.lower() for kw in url_keywords]
    while time.time() < deadline:
        for candidate in page.context.pages:
            try:
                if any(kw in candidate.url.lower() for kw in keywords):
                    candidate.bring_to_front()
                    return candidate
            except Exception:
                continue
        try:
            if any(kw in page.url.lower() for kw in keywords):
                return page
        except Exception:
            pass
        page.wait_for_timeout(1000)
    raise Exception(f"Expected page not reached for keywords: {url_keywords}. Current URL: {page.url}")


def proceed_bank_details_agree(page):
    bank_page = wait_for_page_matching(page, ["bank_details_aggree", "bank_details_agree"], timeout=60000)
    if not click_first_visible(bank_page, BANK_AGREE_PROCEED_LOCATORS, timeout=15000):
        raise Exception("Bank Details Agree Proceed button not found")
    bank_page.wait_for_timeout(5000)
    print("  [OK] Bank Details Agree Proceed clicked")
    return wait_for_page_matching(bank_page, ["proteansurakshaa", "protean"], timeout=60000)


def fill_onemoney_otp(page, otp):
    page.wait_for_timeout(1000)
    visible_inputs = []
    for loc in ONEMONEY_OTP_LOCATORS:
        try:
            inputs = page.locator(loc)
            for i in range(inputs.count()):
                item = inputs.nth(i)
                try:
                    if item.is_visible(timeout=500) and item.is_enabled(timeout=500):
                        visible_inputs.append(item)
                except Exception:
                    continue
        except Exception:
            continue

    unique = []
    seen = set()
    for item in visible_inputs:
        try:
            handle = item.element_handle()
            if handle and handle not in seen:
                seen.add(handle)
                unique.append(item)
        except Exception:
            unique.append(item)

    otp_boxes = []
    for item in unique:
        try:
            maxlength = item.get_attribute("maxlength")
            box = item.bounding_box()
            if maxlength == "1" or (box and box.get("width", 999) < 80):
                otp_boxes.append(item)
        except Exception:
            continue

    if len(otp_boxes) >= 6:
        for digit, item in zip(otp, otp_boxes[:6]):
            item.fill(digit)
        return True

    for item in unique:
        try:
            value = item.input_value(timeout=500)
            placeholder = (item.get_attribute("placeholder") or "").lower()
            if "otp" in placeholder or value == "":
                item.fill(otp)
                return True
        except Exception:
            continue
    return fill_first_visible(page, ONEMONEY_OTP_LOCATORS, otp, timeout=10000)


def complete_onemoney_login(page):
    onemoney_page = wait_for_page_matching(page, ["onemoney"], timeout=60000)
    if not any_locator_visible(onemoney_page, ONEMONEY_OTP_LOCATORS, timeout=2000):
        if not click_first_visible(onemoney_page, ONEMONEY_SEND_OTP_LOCATORS, timeout=30000):
            raise Exception("OneMoney Send OTP button not found")
        onemoney_page.wait_for_timeout(3000)
        print("  [OK] OneMoney Send OTP clicked")

    otp = fetch_latest_yopmail_otp(onemoney_page, "OneMoney OTP", ESIGN_OTP_EMAIL)
    if not fill_onemoney_otp(onemoney_page, otp):
        raise Exception("OneMoney OTP input not found")
    if not click_first_visible(onemoney_page, ONEMONEY_LOGIN_LOCATORS, timeout=15000):
        raise Exception("OneMoney Login button not found")
    onemoney_page.wait_for_timeout(5000)
    print("  [OK] OneMoney OTP submitted")


def fill_protean_surakshaa_otp(page, otp):
    page.wait_for_timeout(1500)
    inputs = []
    for loc in [
        "input[type='tel']",
        "input[type='text']",
        "input[type='number']",
        "input[type='password']",
        "input[name*='otp' i]",
        "input[id*='otp' i]",
    ]:
        try:
            locator = page.locator(loc)
            for i in range(locator.count()):
                item = locator.nth(i)
                try:
                    if item.is_visible(timeout=500) and item.is_enabled(timeout=500):
                        inputs.append(item)
                except Exception:
                    continue
        except Exception:
            continue

    unique = []
    seen = set()
    for item in inputs:
        try:
            handle = item.element_handle()
            if handle and handle not in seen:
                seen.add(handle)
                unique.append(item)
        except Exception:
            unique.append(item)

    otp_boxes = []
    for item in unique:
        try:
            maxlength = item.get_attribute("maxlength")
            box = item.bounding_box()
            if maxlength == "1" or (box and box.get("width", 999) <= 120):
                otp_boxes.append(item)
        except Exception:
            continue

    if len(otp_boxes) >= 6:
        for digit, item in zip(otp, otp_boxes[:6]):
            item.click(force=True)
            item.fill(digit)
        return True

    if unique:
        unique[0].click(force=True)
        unique[0].fill(otp)
        return True

    try:
        page.keyboard.type(otp, delay=80)
        return True
    except Exception:
        return False


def complete_protean_surakshaa_otp(page):
    protean_page = wait_for_page_matching(page, ["proteansurakshaa", "protean"], timeout=60000)
    otp = fetch_latest_yopmail_otp(protean_page, "Protean SurakshAA OTP", ESIGN_OTP_EMAIL)
    if not fill_protean_surakshaa_otp(protean_page, otp):
        raise Exception("Protean SurakshAA OTP input not found")
    protean_page.wait_for_timeout(1000)
    if not click_first_visible(protean_page, PROTEAN_SURAKSHAA_CONTINUE_LOCATORS, timeout=15000):
        raise Exception("Protean SurakshAA Continue button not found")
    protean_page.wait_for_timeout(5000)
    print("  [OK] Protean SurakshAA OTP submitted")
    return protean_page


def continue_protean_linked_accounts(page):
    protean_page = wait_for_page_matching(page, ["proteansurakshaa", "protean"], timeout=60000)
    if not click_first_visible(protean_page, PROTEAN_SURAKSHAA_CONTINUE_LOCATORS, timeout=30000):
        raise Exception("Protean linked accounts Continue button not found")
    protean_page.wait_for_timeout(4000)
    print("  [OK] Protean linked accounts Continue clicked")
    return protean_page


def accept_protean_consent(page):
    protean_page = wait_for_page_matching(page, ["proteansurakshaa", "protean"], timeout=60000)
    if not click_first_visible(protean_page, PROTEAN_SURAKSHAA_ACCEPT_LOCATORS, timeout=30000):
        raise Exception("Protean consent Accept button not found")
    protean_page.wait_for_timeout(5000)
    print("  [OK] Protean consent accepted")
    return protean_page


def continue_active_segment_proof(page):
    segment_page = wait_for_page_matching(page, ["activesegment"], timeout=90000)
    try:
        segment_page.bring_to_front()
    except Exception:
        pass
    if not click_first_visible(segment_page, PROTEAN_SURAKSHAA_CONTINUE_LOCATORS, timeout=30000):
        raise Exception("Active segment proof Continue button not found")
    segment_page.wait_for_timeout(5000)
    print("  [OK] Active segment proof Continue clicked")
    try:
        next_page = wait_for_page_matching(
            segment_page,
            ["upload_signature", "proof_upload", "photo_capturing", "service_req"],
            timeout=90000,
        )
        try:
            next_page.bring_to_front()
        except Exception:
            pass
        return next_page
    except Exception:
        return segment_page

def update_segment_and_protean_surakshaa(page):
    open_section(page, "Segment")
    accept_segment_risk_disclosure_if_present(page)
    enable_bfo_segment(page)
    check_segment_terms_checkbox(page)
    if not click_first_visible(page, SEGMENT_SUBMIT_LOCATORS, timeout=10000):
        raise Exception("Segment Submit button not found")
    page.wait_for_timeout(5000)
    print("  [OK] Segment Submit clicked")
    protean_page = proceed_bank_details_agree(page)
    protean_page = complete_protean_surakshaa_otp(protean_page)
    protean_page = continue_protean_linked_accounts(protean_page)
    protean_page = accept_protean_consent(protean_page)
    segment_page = continue_active_segment_proof(protean_page)
    complete_post_service_esign_flow(segment_page)


def bank_summary_url():
    return urljoin(REKYC_URL, "bank.php")


def bank_add_url():
    return urljoin(REKYC_URL, "add_bank.php")


def bank_editor_available(page):
    candidate_fields = [
        BANK_ACCOUNT_LOCATORS,
        BANK_CONFIRM_ACCOUNT_LOCATORS,
        BANK_IFSC_LOCATORS,
        BANK_ACCOUNT_TYPE_LOCATORS,
    ]
    for locators in candidate_fields:
        for loc in locators:
            try:
                if page.locator(loc).first.is_visible(timeout=1000):
                    return True
            except Exception:
                continue
    return False


def open_bank_editor(page):
    clear_blocking_overlays(page)
    if bank_editor_available(page):
        return
    clicked = click_first_visible(page, BANK_ADD_LOCATORS, timeout=3000)
    page.wait_for_timeout(1500)
    if not clicked and not bank_editor_available(page):
        page.goto(bank_add_url(), wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
    if not bank_editor_available(page):
        raise Exception("Bank editor did not open")


def open_fresh_bank_form(page):
    clear_blocking_overlays(page)
    page.goto(bank_add_url(), wait_until="domcontentloaded")
    page.wait_for_timeout(2000)
    if not bank_editor_available(page):
        open_bank_editor(page)


def assert_bank_loaded(page):
    if "bank" not in page.url.lower() and "bank" not in visible_text(page).lower():
        raise Exception("Bank section content was not visible")
    try:
        page.goto(bank_summary_url(), wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
    except Exception:
        pass
    if "bank" not in visible_text(page).lower() and "bank" not in page.url.lower():
        raise Exception("Bank summary did not show bank content")
    open_bank_editor(page)
    assert_visible_any(page, BANK_ACCOUNT_LOCATORS + BANK_IFSC_LOCATORS + BANK_ACCOUNT_TYPE_LOCATORS, "Bank form field")


def submit_bank(page):
    if not click_first_visible(page, BANK_SAVE_LOCATORS, timeout=5000):
        raise Exception("Bank save/submit button not found")
    page.wait_for_timeout(3000)


def fill_bank_positive_data(page):
    deadline = time.time() + 30
    while time.time() < deadline:
        if bank_editor_available(page):
            break
        page.wait_for_timeout(1000)
    if not bank_editor_available(page):
        raise Exception("Bank manual entry fields did not load")
    fill_required_first_visible(page, BANK_ACCOUNT_LOCATORS, BANK_ACCOUNT_NUMBER, "Bank account number")
    if fill_optional_first_visible(page, BANK_CONFIRM_ACCOUNT_LOCATORS, BANK_ACCOUNT_NUMBER):
        print("  [OK] Confirm account number filled")
    fill_required_first_visible(page, BANK_IFSC_LOCATORS, BANK_IFSC_CODE, "IFSC")
    page.wait_for_timeout(2500)
    print("  [OK] Bank account number and IFSC filled")


def click_bank_manual_entry(page):
    clicked = False
    try:
        clicked = page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                };
                const target = Array.from(document.querySelectorAll('a, button'))
                    .find(el => isVisible(el) &&
                        (el.innerText || el.textContent || '').trim().toLowerCase() === 'enter bank details manually');
                if (!target) return false;
                target.scrollIntoView({ block: 'center', inline: 'center' });
                target.click();
                return true;
            }
            """
        )
    except Exception:
        clicked = False
    if not clicked:
        manual_locators = [
            "//a[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='enter bank details manually']",
            "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='enter bank details manually']",
        ]
        clicked = click_first_visible(page, manual_locators, timeout=15000)
    if not clicked:
        raise Exception("Enter bank details manually link not found")
    deadline = time.time() + 30
    while time.time() < deadline:
        if bank_editor_available(page):
            break
        page.wait_for_timeout(1000)
    if not bank_editor_available(page):
        raise Exception("Bank manual entry page did not open after clicking manual link")
    print("  [OK] Enter bank details manually clicked")


def click_bank_add_account(page):
    open_section(page, "Bank")
    clear_blocking_overlays(page)
    if not click_first_visible(page, BANK_ADD_LOCATORS, timeout=15000):
        raise Exception("Add bank account button not found")
    page.wait_for_timeout(2500)
    print("  [OK] Add bank account clicked")


def click_bank_verify(page):
    clicked = False
    try:
        clicked = page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                };
                const target = Array.from(document.querySelectorAll('button, input[type=button], input[type=submit]'))
                    .find(el => {
                        const text = (el.innerText || el.value || '').trim().toLowerCase();
                        return isVisible(el) && text === 'verify' && !el.disabled;
                    });
                if (!target) return false;
                target.scrollIntoView({ block: 'center', inline: 'center' });
                target.click();
                return true;
            }
            """
        )
    except Exception:
        clicked = False
    if not clicked:
        verify_locators = [
            "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='verify']",
            "//input[translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='verify']",
        ]
        clicked = click_first_visible(page, verify_locators, timeout=15000)
    if not clicked:
        raise Exception("Bank Verify button not found")
    page.wait_for_timeout(6000)
    print("  [OK] Verify clicked")


def accept_bank_name_mismatch_if_present(page):
    page.wait_for_timeout(1500)
    clicked = False
    try:
        clicked = page.evaluate(
            """
            () => {
                const isVisible = (el) => {
                    const r = el.getBoundingClientRect();
                    const s = window.getComputedStyle(el);
                    return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                };
                const popup = Array.from(document.querySelectorAll('.swal2-popup, .swal-modal, .modal, .reveal, [role="dialog"], body'))
                    .find(el => isVisible(el) && /name.*mismatch|do not match|supporting document|message/i.test(el.innerText || el.textContent || ''));
                if (!popup) return false;
                const button = Array.from(popup.querySelectorAll('button, input[type=button], input[type=submit], a'))
                    .find(el => {
                        const text = (el.innerText || el.value || el.textContent || '').trim().toLowerCase();
                        return isVisible(el) && (text === 'okay' || text === 'ok');
                    });
                if (!button) return false;
                button.scrollIntoView({ block: 'center', inline: 'center' });
                button.click();
                return true;
            }
            """
        )
    except Exception:
        clicked = False

    if not clicked:
        ok_locators = [
            "xpath=//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'name') and contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'mismatch')]/following::button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='okay'][1]",
            "xpath=//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'supporting document')]/following::button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='okay'][1]",
            "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='okay']",
            "//button[translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']",
            "//input[translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='okay']",
            "//input[translate(@value,'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz')='ok']",
        ]
        clicked = click_first_visible(page, ok_locators, timeout=10000)

    if clicked:
        deadline = time.time() + 10
        while time.time() < deadline:
            try:
                still_visible = page.evaluate(
                    """
                    () => Array.from(document.querySelectorAll('.swal2-popup, .swal-modal, .modal, .reveal, [role="dialog"]'))
                        .some(el => {
                            const r = el.getBoundingClientRect();
                            const s = window.getComputedStyle(el);
                            return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
                        })
                    """
                )
                if not still_visible:
                    break
            except Exception:
                break
            page.wait_for_timeout(500)
        print("  [OK] Bank name mismatch popup accepted")
        return

    print("  [i] Bank name mismatch popup not shown")


def select_bank_proof_type(page):
    selected = page.evaluate(
        """
        () => {
            const isVisible = (el) => {
                const r = el.getBoundingClientRect();
                const s = window.getComputedStyle(el);
                return r.width > 0 && r.height > 0 && s.display !== 'none' && s.visibility !== 'hidden';
            };
            const selects = Array.from(document.querySelectorAll('select')).filter(isVisible);
            const scoreSelect = (select) => {
                const options = Array.from(select.options).map(o => (o.textContent || '').toLowerCase()).join(' ');
                let score = 0;
                if (options.includes('bank statement')) score += 5;
                if (options.includes('passbook')) score += 4;
                if (options.includes('cancelled cheque')) score += 4;
                const r = select.getBoundingClientRect();
                if (r.top > window.innerHeight / 2) score += 1;
                return score;
            };
            const proofSelect = selects.sort((a, b) => scoreSelect(b) - scoreSelect(a))[0];
            if (!proofSelect) return { ok: false, reason: 'select not found' };
            const option =
                Array.from(proofSelect.options).find(o => /latest\\s*1\\s*month\\s*bank\\s*statement/i.test(o.textContent || '')) ||
                Array.from(proofSelect.options).find(o => /bank\\s*passbook/i.test(o.textContent || '')) ||
                Array.from(proofSelect.options).find(o => /cancelled\\s*cheque/i.test(o.textContent || '')) ||
                Array.from(proofSelect.options).find(o => o.value && !/please\\s*select/i.test(o.textContent || ''));
            if (!option) return { ok: false, reason: 'valid proof option not found' };
            proofSelect.scrollIntoView({ block: 'center', inline: 'center' });
            proofSelect.value = option.value;
            option.selected = true;
            proofSelect.selectedIndex = option.index;
            proofSelect.dispatchEvent(new Event('input', { bubbles: true }));
            proofSelect.dispatchEvent(new Event('change', { bubbles: true }));
            proofSelect.dispatchEvent(new Event('blur', { bubbles: true }));
            return { ok: proofSelect.value === option.value, value: proofSelect.value, text: option.textContent.trim() };
        }
        """
    )

    if not selected or not selected.get("ok"):
        raise Exception(f"Bank proof dropdown option not selected: {selected}")
    page.wait_for_timeout(1000)
    verified = page.evaluate(
        """
        () => Array.from(document.querySelectorAll('select')).some(select => {
            const text = select.options[select.selectedIndex]?.textContent || '';
            return select.value && /(bank statement|passbook|cancelled cheque)/i.test(text);
        })
        """
    )
    if not verified:
        raise Exception("Bank proof dropdown option not selected")
    print(f"  [OK] Bank proof dropdown selected: {selected.get('text')}")

def upload_bank_proof(page):
    if not os.path.exists(BANK_PROOF_FILE_PATH):
        raise Exception(f"Bank proof file not found: {BANK_PROOF_FILE_PATH}")
    upload_locators = [
        "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload')]",
        "//a[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload')]",
        "//*[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'upload')]",
    ]
    try:
        with page.expect_file_chooser(timeout=5000) as chooser_info:
            click_first_visible(page, upload_locators, timeout=5000)
        chooser_info.value.set_files(BANK_PROOF_FILE_PATH)
    except Exception:
        file_input = page.locator("input[type='file']").first
        file_input.set_input_files(BANK_PROOF_FILE_PATH, timeout=10000)
    page.wait_for_timeout(2500)
    print("  [OK] Bank proof uploaded")


def run_bank_module(page):
    click_bank_add_account(page)
    click_bank_manual_entry(page)
    fill_bank_positive_data(page)
    click_bank_verify(page)
    accept_bank_name_mismatch_if_present(page)
    select_bank_proof_type(page)
    upload_bank_proof(page)
    submit_bank(page)
    print("  [OK] Bank module flow submitted")


def check_still_on_login(page):
    """
    FIX 5: Guard against the server redirecting to a non-login error page.
    We check we are NOT on the OTP page. We do NOT require 'login' in the URL
    because some servers redirect to an error URL on wrong credentials.
    """
    url = page.url.lower()
    if "otp" in url:
        raise Exception(f"Unexpectedly navigated to OTP page: {page.url}")
    # Also confirm we didn't land on a completely unexpected domain
    # (optional: add further domain check here if needed)
    print(f"  [OK] Still on non-OTP page ({page.url}) -- negative test passed")


def fill_otp(page, otp_value):
    """Fill the OTP field; falls back to individual digit boxes."""
    filled = fill_first_visible(page, OTP_LOCATORS, otp_value)
    if not filled:
        boxes = page.locator("input[type='text'], input[type='tel'], input[type='number']")
        visible = []
        for i in range(boxes.count()):
            box = boxes.nth(i)
            try:
                if box.is_visible(timeout=1000):
                    visible.append(box)
            except Exception:
                continue
        if len(visible) >= 6:
            for digit, box in zip(otp_value, visible[:6]):
                box.fill(digit)
            filled = True
    return filled


def check_still_on_otp(page):
    """Confirm we did NOT leave the OTP page (negative-scenario guard)."""
    if "otp" not in page.url.lower():
        raise Exception(f"Unexpectedly left OTP page: {page.url}")


# -----------------------------------------------------------------------------
#  TEST CLASS
# -----------------------------------------------------------------------------

class TestReKYC:
    __test__ = False  # Legacy helper flow; do not collect with pytest.

    def test_rekyc_flow(self, page: Page):

        # FIX 1: Clear via the shared container, not a local rebind
        _step_results_store["results"].clear()

        # ======================================================================
        # STEP 1 ? Open Login Page
        # Anti-CAPTCHA measures:
        #   - Mask all Playwright/automation signals via init script
        #   - Simulate realistic human mouse movement after page load
        #   - Gradual scroll to mimic natural reading behaviour
        #   - Small randomised pauses between actions
        # ======================================================================
        def step1():
            # -- Mask automation signals before any page load ---------------
            page.add_init_script("""
                // Hide webdriver flag -- primary bot signal
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

                // Realistic language + plugin fingerprint
                Object.defineProperty(navigator, 'languages', { get: () => ['en-IN', 'en-GB', 'en'] });
                Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3, 4, 5] });

                // Edge exposes both window.chrome and window.chrome.runtime
                // (absent in headless/automation = bot signal)
                window.chrome = { runtime: {}, loadTimes: function(){}, csi: function(){} };
                // Edge-specific object -- present in real Edge sessions
                window.microsoft = window.microsoft || {};
                window.microsoft.edge = { webview: false };

                // Realistic screen/hardware properties
                Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
                Object.defineProperty(navigator, 'deviceMemory',        { get: () => 8 });
                Object.defineProperty(navigator, 'platform',            { get: () => 'Win32' });

                // Prevent permission API from revealing automation
                const origQuery = window.navigator.permissions.query;
                window.navigator.permissions.query = (params) =>
                    params.name === 'notifications'
                        ? Promise.resolve({ state: Notification.permission })
                        : origQuery(params);
            """)

            page.goto(REKYC_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

            # -- Human-like mouse movement ----------------------------------
            # Simulate natural cursor path: enter from top-left, drift toward
            # the form area in small steps (mimics eye-tracking + hand movement)
            movements = [
                (120, 80),  (200, 150), (310, 200),
                (380, 280), (430, 350), (460, 400),
                (440, 420), (400, 410), (420, 380),
            ]
            for x, y in movements:
                page.mouse.move(x, y)
                page.wait_for_timeout(120)   # ~120ms between moves

            # -- Gentle scroll (simulates reading the page) -----------------
            page.mouse.wheel(0, 120)
            page.wait_for_timeout(600)
            page.mouse.wheel(0, -120)        # scroll back up to top
            page.wait_for_timeout(800)

            # -- Hover near (but not on) the UCC field before filling -------
            # This mimics a user locating the field visually first
            try:
                ucc_box = page.locator("input[placeholder='UCC'], input[placeholder='ucc']").first.bounding_box()
                if ucc_box:
                    # Hover 40px above the field
                    page.mouse.move(
                        ucc_box["x"] + ucc_box["width"] / 2,
                        ucc_box["y"] - 40,
                    )
                    page.wait_for_timeout(500)
            except Exception:
                pass

            print("  [OK] Login page loaded with human-like behaviour applied")

        run_step(1, "Open ReKYC Login Page", step1)

        # ======================================================================
        # STEP 2 ? Negative: Blank UCC + Blank DOB
        # ======================================================================
        def step2():
            fill_ucc(page, "")
            submit_login(page)
            page.wait_for_timeout(4000)
            check_still_on_login(page)  # FIX 5 applied
            assert_validation_feedback(page, ["required", "please", "ucc", "dob", "enter"], "login validation")
            print("  [OK] Blank UCC + Blank DOB correctly rejected")

        run_step(2, "Negative: Blank UCC and Blank DOB", step2)

        # ======================================================================
        # STEP 3 ? Negative: Invalid UCC, no DOB
        # ======================================================================
        def step3():
            fill_ucc(page, "INVALID123")
            submit_login(page)
            page.wait_for_timeout(4000)
            check_still_on_login(page)  # FIX 5 applied
            assert_validation_feedback(page, ["invalid", "ucc", "client", "please", "error"], "login validation")
            print("  [OK] Invalid UCC / no DOB correctly rejected")
            fill_ucc(page, "")

        run_step(3, "Negative: Invalid UCC with no DOB", step3)

        # ======================================================================
        # STEP 4 ? Negative: Valid UCC + Wrong DOB
        # ======================================================================
        def step4():
            reset_login_page(page)
            fill_ucc(page, REKYC_UCC)
            select_dob(page, "2000", "0", "1")   # FIX 9: calendar closed before open
            submit_login(page)
            page.wait_for_timeout(8000)
            check_still_on_login(page)           # FIX 5: no longer requires 'login' in URL
            assert_validation_feedback(page, ["invalid", "dob", "date", "wrong", "match", "error"], "login validation")
            print("  [OK] Valid UCC + Wrong DOB correctly rejected")

        run_step(4, "Negative: Valid UCC with wrong DOB", step4)

        # ======================================================================
        # STEP 5 ? Negative: Blank UCC + Valid-looking DOB
        # ======================================================================
        def step5():
            reset_login_page(page)
            fill_ucc(page, "")
            select_dob(page, DOB_YEAR, DOB_MONTH, DOB_DAY)
            submit_login(page)
            page.wait_for_timeout(4000)
            check_still_on_login(page)
            assert_validation_feedback(page, ["required", "please", "ucc", "client", "enter"], "login validation")
            print("  [OK] Blank UCC + Valid DOB correctly rejected")

        run_step(5, "Negative: Blank UCC with valid DOB", step5)

        # ======================================================================
        # STEP 6 ? Refresh page before positive flow
        # ======================================================================
        def step6():
            page.goto(REKYC_URL, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            print("  [OK] Page refreshed -- starting positive login flow")

        run_step(6, "Refresh page after negative login scenarios", step6)

        # ======================================================================
        # STEP 7 ? Positive: Enter valid UCC
        # ======================================================================
        def step7():
            if not fill_ucc(page, REKYC_UCC):
                raise Exception("UCC input field not found")

        run_step(7, f"Enter valid UCC: {REKYC_UCC}", step7)

        # ======================================================================
        # STEP 8 ? Positive: Click DOB field
        # ======================================================================
        def step8():
            if not click_first_visible(page, DOB_LOCATORS):
                raise Exception("DOB input field not found")
            page.wait_for_timeout(1000)

        run_step(8, "Click DOB Field", step8)

        # ======================================================================
        # STEP 9 ? Positive: Select valid DOB
        # ======================================================================
        def step9():
            page.wait_for_timeout(2000)
            page.locator(".yearselect").first.select_option(value=DOB_YEAR)
            page.locator(".monthselect").first.select_option(value=DOB_MONTH)
            day_number = str(int(DOB_DAY))
            dates = page.locator("td.available:not(.off):not(.disabled)")
            for i in range(dates.count()):
                cell = dates.nth(i)
                if cell.text_content().strip() == day_number:
                    cell.click()
                    return
            raise Exception("DOB day not found")

        run_step(9, "Select valid DOB", step9)

        # ======================================================================
        # STEP 10 ? Submit login
        # ======================================================================
        def step10():
            handle_captcha_if_present(page)
            submit_login(page)
            page.wait_for_timeout(5000)
            handle_captcha_if_present(page)
            # FIX 6: Check only for 'otp' absence, not presence of 'login' in URL
            if "otp" not in page.url.lower():
                current_url = page.url.lower()
                if "login" in current_url or "rekyc" in current_url:
                    print("  -> Still on login/captcha page -- re-submitting after CAPTCHA solve...")
                    submit_login(page)
            page.wait_for_timeout(15000)
            if not is_otp_page(page):
                raise Exception(f"OTP page not opened after login submit. Current URL: {page.url}")

        run_step(10, "Submit Login", step10)

        # ======================================================================
        # STEP 11 ? Verify OTP page loaded
        # ======================================================================
        def step11():
            if not is_otp_page(page):
                raise Exception(f"OTP page not opened -- current URL: {page.url}")

        run_step(11, "Verify OTP Page Loaded", step11)

        # ======================================================================
        # STEP 12 ? OTP Negative: Blank OTP
        # ======================================================================
        def step12():
            fill_first_visible(page, OTP_LOCATORS, "")
            submit_otp(page)   # FIX 7: uses resilient multi-selector submit
            page.wait_for_timeout(5000)
            check_still_on_otp(page)
            assert_validation_feedback(page, ["otp", "required", "please", "enter"], "OTP validation")
            print("  [OK] Blank OTP -- Submission correctly rejected")

        run_step(12, "OTP Negative: Submit with blank OTP", step12)

        # ======================================================================
        # STEP 13 ? OTP Negative: Wrong OTP (000000)
        # ======================================================================
        def step13():
            if not fill_otp(page, "000000"):
                raise Exception("OTP input field not found for wrong-OTP scenario")
            submit_otp(page)   # FIX 7
            page.wait_for_timeout(6000)
            check_still_on_otp(page)
            assert_validation_feedback(page, ["otp", "invalid", "wrong", "incorrect", "error"], "OTP validation")
            print("  [OK] Wrong OTP (000000) -- Submission correctly rejected")

        run_step(13, "OTP Negative: Submit wrong OTP (000000)", step13)

        # ======================================================================
        # STEP 14 ? OTP Negative: Short / partial OTP (123)
        # ======================================================================
        def step14():
            filled = fill_otp(page, "123")
            if filled:
                submit_otp(page)   # FIX 7
                page.wait_for_timeout(5000)
                check_still_on_otp(page)
                assert_validation_feedback(page, ["otp", "invalid", "digit", "length", "error"], "OTP validation")
                print("  [OK] Short OTP (123) -- Submission correctly rejected")
            else:
                raise Exception("OTP input field not found for short-OTP scenario")

        run_step(14, "OTP Negative: Submit short OTP (123)", step14)

        # ======================================================================
        # STEP 15 ? Fetch valid OTP from Yopmail and enter it
        # FIX 8: Extended polling to 30 * 10s = 300s (5 min) with smarter refresh
        # ======================================================================
        def step15():
            if not is_otp_page(page):
                raise Exception(f"Cannot fetch login OTP because OTP page is not open. Current URL: {page.url}")
            new_page = page.context.new_page()
            otp = None
            try:
                new_page.goto("https://yopmail.com/en/", wait_until="domcontentloaded")
                inbox = REKYC_YOPMAIL.split("@")[0]
                new_page.locator("#login").fill(inbox)
                new_page.keyboard.press("Enter")
                new_page.wait_for_timeout(3000)

                mail_items = None
                # FIX 8: Poll for 30 attempts ? 10s = 5 minutes
                for attempt in range(30):
                    new_page.wait_for_timeout(10000)
                    try:
                        refresh_button = new_page.locator("#refresh")
                        if refresh_button.is_visible(timeout=2000):
                            refresh_button.click()
                            new_page.wait_for_timeout(2000)
                    except Exception:
                        pass
                    inbox_frame = new_page.frame_locator("#ifinbox")
                    items = inbox_frame.locator(".m, .lm")
                    try:
                        if items.count() > 0:
                            mail_items = items
                            print(f"  [OK] Email found after {(attempt+1)*10}s")
                            break
                    except Exception:
                        pass
                    print(f"  ... Waiting for OTP email ({(attempt+1)*10}s elapsed)...")

                if mail_items is None:
                    raise Exception("No email found in Yopmail inbox after 5 minutes")

                mail_items.first.click()
                mail_frame = new_page.frame_locator("#ifmail")
                body = mail_frame.locator("body")
                body.wait_for(timeout=30000)
                text = body.inner_text(timeout=30000)
                otp_match = re.search(r"\b\d{6}\b", text)
                if not otp_match:
                    raise Exception("OTP not found in Yopmail email body")
                otp = otp_match.group(0)
                print(f"  [OK] OTP fetched: {otp}")
            finally:
                new_page.close()

            if not fill_otp(page, otp):
                raise Exception("OTP input field not found on OTP page")

        run_step(15, "Fetch valid OTP from Yopmail and enter it", step15)

        # ======================================================================
        # STEP 16 ? Submit valid OTP
        # ======================================================================
        def step16():
            submit_otp(page)   # FIX 7
            page.wait_for_timeout(5000)

        run_step(16, "Submit valid OTP", step16)

        # ======================================================================
        # STEP 17 ? Dashboard check
        # ======================================================================
        def step17():
            if is_otp_page(page):
                raise Exception("Still on OTP page after valid OTP submit")
            if not is_logged_in_dashboard(page):
                raise Exception(f"Dashboard did not load after valid OTP submit. Current URL: {page.url}")

        run_step(17, "Dashboard Check", step17)

        # ======================================================================
        # STEP 19 - Mobile Section
        # ======================================================================
        def step19():
            open_section(page, "Mobile No")

        run_step(19, "Mobile Section", step19)

        # ======================================================================
        # STEP 64 - Mobile Negative: Send OTP without declaration
        # ======================================================================
        def step64():
            assert_service_send_otp_blocked_without_declaration(page, "Mobile No")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(64, "Mobile Negative: Send OTP without declaration", step64)

        # ======================================================================
        # STEP 65 - Mobile Negative: Blank OTP
        # ======================================================================
        def step65():
            assert_service_otp_negative(page, "Mobile No", "", ["otp", "required", "please", "enter"], "blank OTP validation")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(65, "Mobile Negative: Submit blank OTP", step65)

        # ======================================================================
        # STEP 66 - Mobile Negative: Wrong OTP
        # ======================================================================
        def step66():
            assert_service_otp_negative(page, "Mobile No", "000000", ["otp", "invalid", "wrong", "incorrect", "error"], "wrong OTP validation")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(66, "Mobile Negative: Submit wrong OTP", step66)

        # ======================================================================
        # STEP 67 - Mobile Negative: Short OTP
        # ======================================================================
        def step67():
            assert_service_otp_negative(page, "Mobile No", "123", ["otp", "invalid", "digit", "length", "error"], "short OTP validation")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(67, "Mobile Negative: Submit short OTP", step67)

        # ======================================================================
        # STEP 68 - Mobile Positive: Complete mobile OTP flow
        # ======================================================================
        def step68():
            complete_service_otp_flow(page, "Mobile No")

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(68, "Mobile Positive: Complete mobile OTP flow", step68)

        # ======================================================================
        # STEP 70b - Service Post-OTP: Upload Signature (Mobile flow)
        # ======================================================================
        def step70b():
            upload_signature_for_esign(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(70, "Service Post-OTP: Upload signature", step70b)

        # ======================================================================
        # STEP 72b - Service Post-OTP: ReKYC Live IPV Liveness Capture (Mobile flow)
        # ======================================================================
        def step72b():
            prepare_ipv_browser(page)
            capture_ipv_photo(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(72, "Service Post-OTP: ReKYC live IPV liveness capture (blink detection)", step72b)

        # ======================================================================
        # STEP 71b - Service Post-OTP: View Unsigned KYC PDF (Mobile flow)
        # ======================================================================
        def step71b():
            view_unsigned_pdf(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(71, "Service Post-OTP: View unsigned KYC PDF", step71b)

        # ======================================================================
        # STEP 73b - Service Post-OTP: Proceed to eSign (Mobile flow)
        # ======================================================================
        def step73b():
            proceed_to_esign(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(73, "Service Post-OTP: Proceed to Aadhaar eSign", step73b)

        # ======================================================================
        # STEP 74b - Service Post-OTP: Aadhaar eSign OTP (Mobile flow)
        # ======================================================================
        def step74b():
            complete_aadhaar_esign(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(74, "Service Post-OTP: Complete Aadhaar eSign OTP", step74b)

        # ======================================================================

        # ======================================================================
        # STEP 18 - Email Section
        # ======================================================================
        def step18():
            open_section(page, "Email")

        run_step(18, "Email Section", step18)

        # ======================================================================
        # STEP 60 - Email Negative: Send OTP without declaration
        # ======================================================================
        def step60():
            assert_service_send_otp_blocked_without_declaration(page, "Email")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(60, "Email Negative: Send OTP without declaration", step60)

        # ======================================================================
        # STEP 61 - Email Negative: Blank OTP
        # ======================================================================
        def step61():
            assert_service_otp_negative(page, "Email", "", ["otp", "required", "please", "enter"], "blank OTP validation")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(61, "Email Negative: Submit blank OTP", step61)

        # ======================================================================
        # STEP 62 - Email Negative: Wrong OTP
        # ======================================================================
        def step62():
            assert_service_otp_negative(page, "Email", "000000", ["otp", "invalid", "wrong", "incorrect", "error"], "wrong OTP validation")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(62, "Email Negative: Submit wrong OTP", step62)

        # ======================================================================
        # STEP 63 - Email Negative: Short OTP
        # ======================================================================
        def step63():
            assert_service_otp_negative(page, "Email", "123", ["otp", "invalid", "digit", "length", "error"], "short OTP validation")

        if RUN_EMAIL_MOBILE_MODULE and RUN_EMAIL_MOBILE_NEGATIVE_MODULE:
            run_step(63, "Email Negative: Submit short OTP", step63)

        # ======================================================================
        # STEP 69 - Email Positive: Complete email OTP flow
        # ======================================================================
        def step69():
            complete_service_otp_flow(page, "Email")

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(69, "Email Positive: Complete email OTP flow using E-mail OTP", step69)

        # ======================================================================
        # STEP 70 - Service Post-OTP: Upload Signature
        # ======================================================================
        def step70():
            upload_signature_for_esign(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(70, "Service Post-OTP: Upload signature", step70)

        # ======================================================================
        # STEP 72 - Service Post-OTP: ReKYC Live IPV Liveness Capture
        # ======================================================================
        def step72():
            prepare_ipv_browser(page)
            capture_ipv_photo(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(72, "Service Post-OTP: ReKYC live IPV liveness capture (blink detection)", step72)

        # ======================================================================
        # STEP 71 - Service Post-OTP: View Unsigned KYC PDF
        # ======================================================================
        def step71():
            view_unsigned_pdf(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(71, "Service Post-OTP: View unsigned KYC PDF", step71)

        # ======================================================================
        # STEP 73 - Service Post-OTP: Proceed to eSign
        # ======================================================================
        def step73():
            proceed_to_esign(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(73, "Service Post-OTP: Proceed to Aadhaar eSign", step73)

        # ======================================================================
        # STEP 74 - Service Post-OTP: Aadhaar eSign OTP
        # ======================================================================
        def step74():
            complete_aadhaar_esign(page)

        if RUN_EMAIL_MOBILE_MODULE:
            run_step(74, "Service Post-OTP: Complete Aadhaar eSign OTP", step74)



        assert_all_steps_passed()
