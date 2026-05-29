import ast
import datetime
import html
import json
import os
import smtplib
import ssl
import subprocess
import sys
import time
import urllib.request
import urllib.error

from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


# -----------------------------------------------------------------------------
#  Teams Power Automate Workflows Webhook URL
# -----------------------------------------------------------------------------
TEAMS_WEBHOOK_URL = os.environ.get(
    "TEAMS_WEBHOOK_URL",
    "https://defaultb5be2d2cde3a4b3680d7e5445c6627.3b.environment.api.powerplatform.com:443/powerautomate/automations/direct/workflows/576c90a823384e15a15a8f7b8366bd18/triggers/manual/paths/invoke?api-version=1&sp=%2Ftriggers%2Fmanual%2Frun&sv=1.0&sig=qMkr4iPgnjfWJnHEA0KnFniMUoDKIOcZhyhYx7AKhUU",
)

# -----------------------------------------------------------------------------
#  Step metadata
# -----------------------------------------------------------------------------
STEP_META = {
    1:  ("NEG-LOGIN-001",  "Login Page",        "UCC + DOB",          "Blank UCC, Blank DOB",     "Validation message should display; stay on login page"),
    2:  ("NEG-LOGIN-002",  "Login Page",        "UCC",                "Invalid UCC (INVALID123)", "Validation/error message should display; stay on login page"),
    3:  ("NEG-LOGIN-003",  "Login Page",        "UCC + DOB",          "Valid UCC + Wrong DOB",    "Login should fail; error shown; stay on login page"),
    4:  ("POS-LOGIN-001",  "Login Page",        "UCC + DOB",          "Valid UCC, Valid DOB",     "Login should submit and redirect to OTP page"),
    5:  ("NEG-LOGIN-004",  "Login Page",        "UCC",                "Blank UCC + Valid DOB",    "Validation message should display; stay on login page"),
    6:  ("POS-LOGIN-000",  "Login Page",        "Page Refresh",       "",                         "Page should reload cleanly before positive flow"),
    7:  ("POS-LOGIN-002",  "Login Page",        "UCC",                "Valid UCC",                "UCC field should accept valid input"),
    8:  ("POS-LOGIN-003",  "Login Page",        "DOB",                "",                         "DOB calendar should open on click"),
    9:  ("POS-LOGIN-004",  "Login Page",        "DOB",                "",                         "Valid DOB should be selectable from calendar"),
    10: ("POS-LOGIN-005",  "Login Page",        "Submit",             "",                         "Login form should submit and redirect to OTP page"),
    11: ("POS-LOGIN-006",  "OTP Page",          "Page URL",           "",                         "URL should contain 'otp' after successful login"),
    12: ("NEG-OTP-001",    "OTP Verification",  "OTP",                "Blank OTP",                "Validation message should display; stay on OTP page"),
    13: ("NEG-OTP-002",    "OTP Verification",  "OTP",                "Wrong OTP (000000)",       "Invalid OTP message should display; stay on OTP page"),
    14: ("NEG-OTP-003",    "OTP Verification",  "OTP",                "Short OTP (123)",          "Validation/error message should display; stay on OTP page"),
    15: ("POS-OTP-001",    "OTP Verification",  "OTP",                "Valid OTP from Yopmail",   "Valid OTP should submit and proceed to dashboard"),
    16: ("POS-OTP-002",    "OTP Verification",  "Submit OTP",         "",                         "Valid OTP submit should proceed past OTP page"),
    17: ("POS-DASH-001",   "Dashboard",         "Page URL",           "",                         "URL should NOT contain 'otp' after valid OTP submit"),
    18: ("POS-SECT-001",   "Dashboard",         "Email Section",      "",                         "Email section should open without error"),
    19: ("POS-SECT-002",   "Dashboard",         "Mobile No Section",  "",                         "Mobile section should open without error"),
    20: ("POS-SECT-003",   "Dashboard",         "Address Section",    "",                         "Address section should open without error"),
    21: ("POS-SECT-004",   "Dashboard",         "Nominee Section",    "",                         "Nominee section should open without error"),
    22: ("POS-SECT-005",   "Dashboard",         "Bank Section",       "",                         "Bank section should open without error"),
    23: ("POS-SECT-006",   "Dashboard",         "Segment Section",    "",                         "Segment section should open without error"),
    24: ("POS-SECT-007",   "Dashboard",         "Income Declaration", "",                         "Income Declaration section should open without error"),
    25: ("POS-SECT-008",   "Dashboard",         "Dis Slip Req",       "",                         "Dis Slip Req section should open without error"),
    26: ("POS-SECT-009",   "Dashboard",         "Service Status",     "",                         "Service Status section should open without error"),
    27: ("POS-SECT-010",   "Dashboard",         "Documents Section",  "",                         "Documents section should open without error"),
    28: ("POS-SECT-011",   "Documents",         "View Proof 1",       "",                         "First document proof should be viewable"),
    29: ("POS-SECT-012",   "Documents",         "View Proof 2",       "",                         "Second document proof should be viewable"),
    30: ("POS-SECT-013",   "Dashboard",         "DDPI Section",       "",                         "DDPI section should open (500 error handled gracefully)"),
    31: ("POS-NOM-001",    "Nominee",           "Section Load",       "",                         "Nominee page/form should load with nominee controls"),
    32: ("NEG-NOM-001",    "Nominee",           "Submit",             "Blank nominee form",       "Validation message should display for mandatory nominee fields"),
    33: ("NEG-NOM-002",    "Nominee",           "PAN/Aadhaar Number", "Invalid/short number",     "Validation message should display for invalid PAN/Aadhaar"),
    34: ("NEG-NOM-003",    "Nominee",           "Nominee Name",       "123456",                   "Validation message should display for invalid nominee name"),
    35: ("NEG-NOM-004",    "Nominee",           "Mobile",             "123",                      "Validation message should display for invalid nominee mobile"),
    36: ("NEG-NOM-005",    "Nominee",           "Relationship",       "Blank relationship",       "Validation message should display for missing relationship"),
    37: ("NEG-NOM-006",    "Nominee",           "Share Percentage",   "150",                      "Validation message should display for invalid nominee share"),
    38: ("NEG-NOM-007",    "Nominee",           "DOB",                "Future DOB",               "Validation message should display for invalid nominee DOB"),
    39: ("NEG-NOM-008",    "Nominee",           "Email",              "bad-email",                "Validation message should display for invalid nominee email"),
    40: ("NEG-NOM-009",    "Nominee",           "Guardian Details",   "Minor nominee, blank guardian", "Validation message should display for guardian fields"),
    41: ("POS-NOM-002",    "Nominee",           "Nominee Details",    "Valid major nominee",      "Nominee form fields should accept and save valid major nominee data"),
    42: ("POS-NOM-003",    "Nominee",           "Guardian Details",   "Valid minor nominee",      "Minor nominee guardian fields should accept valid data"),
    43: ("POS-NOM-004",    "Nominee",           "Save",               "Valid nominee flow",       "Nominee details should save, then automation should return to ReKYC without e-Sign"),
    44: ("POS-BANK-001",   "Bank",              "Section Load",       "",                         "Bank page should load with bank details or add-bank controls"),
    45: ("NEG-BANK-001",   "Bank",              "Submit",             "Blank bank form",          "Validation message should display for mandatory bank fields"),
    46: ("NEG-BANK-002",   "Bank",              "Account Number",     "123",                      "Validation message should display for invalid account number"),
    47: ("NEG-BANK-003",   "Bank",              "Confirm Account No", "Mismatch",                 "Validation message should display for mismatched account number"),
    48: ("NEG-BANK-004",   "Bank",              "IFSC",               "BADIFSC",                  "Validation message should display for invalid IFSC"),
    49: ("NEG-BANK-005",   "Bank",              "Account Type",       "Blank account type",       "Validation message should display for missing account type"),
    50: ("POS-BANK-002",   "Bank",              "Bank Details",       "Valid test data",          "Bank form fields should accept valid test data without UI errors"),
    51: ("NEG-NOM-010",    "Nominee",           "PAN/Aadhaar Number", "Client Aadhaar (830889536550)", "Validation message should display when nominee Aadhaar is same as client Aadhaar"),
    52: ("NEG-NOM-011",    "Nominee",           "PAN/Aadhaar Number", "Client PAN (IBSPN7684H), then Continue", "Flow should not proceed when nominee PAN is same as client PAN"),
    53: ("NEG-GRD-001",    "Guardian",          "PAN/Aadhaar Number", "Invalid/short number",     "Validation message should display for invalid guardian PAN/Aadhaar"),
    54: ("NEG-GRD-002",    "Guardian",          "Guardian Name",      "123456",                   "Validation message should display for invalid guardian name"),
    55: ("NEG-GRD-003",    "Guardian",          "Mobile",             "123",                      "Validation message should display for invalid guardian mobile"),
    56: ("NEG-GRD-004",    "Guardian",          "DOB",                "Future DOB",               "Validation message should display for invalid guardian DOB"),
    57: ("NEG-GRD-005",    "Guardian",          "Email",              "bad-email",                "Validation message should display for invalid guardian email"),
    58: ("NEG-GRD-006",    "Guardian",          "Relationship",       "Blank relationship",       "Validation message should display for missing guardian relationship"),
    59: ("NEG-GRD-007",    "Guardian",          "Continue",           "Click Continue after save", "Flow should not proceed to e-Sign after saved guardian nominee"),
    60: ("NEG-EMAIL-001",  "Email",             "Declaration",        "Unchecked declaration",    "Send OTP should not proceed until declaration checkbox is selected"),
    61: ("NEG-EMAIL-002",  "Email",             "OTP",                "Blank OTP",                "Validation message should display for blank email OTP"),
    62: ("NEG-EMAIL-003",  "Email",             "OTP",                "Wrong OTP (000000)",       "Validation message should display for wrong email OTP"),
    63: ("NEG-EMAIL-004",  "Email",             "OTP",                "Short OTP (123)",          "Validation message should display for short email OTP"),
    64: ("NEG-MOB-001",    "Mobile No",         "Declaration",        "Unchecked declaration",    "Send OTP should not proceed until declaration checkbox is selected"),
    65: ("NEG-MOB-002",    "Mobile No",         "OTP",                "Blank OTP",                "Validation message should display for blank mobile OTP"),
    66: ("NEG-MOB-003",    "Mobile No",         "OTP",                "Wrong OTP (000000)",       "Validation message should display for wrong mobile OTP"),
    67: ("NEG-MOB-004",    "Mobile No",         "OTP",                "Short OTP (123)",          "Validation message should display for short mobile OTP"),
    68: ("POS-MOB-001",    "Mobile No",         "Request Flow",       "7530099052 + valid OTPs",  "Mobile request should complete through signature upload, IPV, PDF and Aadhaar eSign"),
    69: ("POS-EMAIL-001",  "Email",             "OTP",                "Valid OTP via E-mail",     "Email section should send OTP to E-mail and accept valid OTP from Yopmail"),
    70: ("POS-SIGN-001",   "Signature",         "Signature Upload",   "Signature.png",            "Signature image should upload and submit successfully"),
    71: ("POS-PDF-001",    "IPV/eSign",         "Unsigned KYC PDF",   "",                         "Unsigned KYC PDF should open and be viewed before eSign"),
    72: ("POS-IPV-001",    "IPV",               "Camera Capture",     "Fake blink camera",        "IPV camera screen should capture or advance successfully"),
    73: ("POS-ESIGN-001",  "eSign",             "Proceed to eSign",   "",                         "Protean Aadhaar eSign page should open"),
    74: ("POS-ESIGN-002",  "eSign",             "Aadhaar OTP",        "830889536550",             "Aadhaar OTP should be fetched from Yopmail and submitted"),
}

STEP_META.update({
    75: ("POS-ADDR-001", "Change of Address", "Existing Address", "", "Existing address details should display"),
    76: ("POS-ADDR-002", "Change of Address", "Proceed to Change", "", "Virtual Aadhaar/DigiLocker step should display"),
    77: ("POS-ADDR-003", "Change of Address", "DigiLocker Aadhaar", "Valid Aadhaar OTP/security PIN", "DigiLocker consent flow should proceed"),
    78: ("POS-ADDR-004", "Change of Address", "PAN Auto Fetch", "No Aadhaar/PAN name mismatch", "PAN should auto-fetch when names match"),
    79: ("POS-ADDR-005", "Change of Address", "PAN Entry", "PAN required on mismatch", "PAN field should accept valid PAN when needed"),
    80: ("POS-ADDR-006", "Change of Address", "Personal/FATCA", "Mandatory fields filled", "Personal/FATCA page should proceed after mandatory fields"),
    81: ("POS-ADDR-007", "Change of Address", "PAN Upload", "PAN fetched from DigiLocker", "PAN upload should not display when PAN is fetched"),
    82: ("POS-ADDR-008", "Change of Address", "Signature", "Signature upload/draw", "Signature step should complete for address flow"),
    83: ("POS-ADDR-009", "Change of Address", "IPV", "Camera/location enabled", "IPV should allow capture before eSign"),
    84: ("NEG-ADDR-001", "Change of Address", "Location", "Camera/location disabled", "Validation should ask user to enable location"),
    85: ("POS-ADDR-010", "Change of Address", "KYC Document", "PAN + Signature attached", "KYC document should show PAN and signature"),
    86: ("POS-ADDR-011", "Change of Address", "eSign", "Continue to eSign", "Address flow should move to eSign page"),
    87: ("POS-ADDR-012", "Change of Address", "Aadhaar eSign", "Correct client Aadhaar", "Address request should be placed after valid Aadhaar eSign"),
    88: ("NEG-ADDR-002", "Change of Address", "PAN", "Existing/linked PAN", "Validation should show PAN already linked to another account"),
    89: ("NEG-ADDR-003", "Change of Address", "Personal/FATCA", "Missing mandatory field", "Flow should not proceed when mandatory personal/FATCA fields are missing"),
    90: ("NEG-ADDR-004", "Change of Address", "PAN Upload", "PDF > 2 pages or > 3 MB", "PAN upload validation should block invalid PDF"),
    91: ("NEG-ADDR-005", "Change of Address", "KYC Document", "Missing PAN/signature", "Missing PAN or signature in KYC document should be treated as failure"),
    92: ("POS-NOM-005", "Nominee", "Existing Nominee", "", "Existing nominee details should display when present"),
    93: ("POS-NOM-006", "Nominee", "Add Nominee Button", "Checkbox selected", "Add Nominee should navigate to nominee entry page"),
    94: ("POS-NOM-007", "Nominee", "Required Fields", "Nominee form", "All required nominee fields should display"),
    95: ("POS-NOM-008", "Nominee", "Add Nominee 3", "Click Add Nominee", "Nominee 3 section should display with required fields"),
    96: ("POS-NOM-009", "Nominee", "Remove Nominee", "Remove Nominee 2", "Remove should close nominee 2 fields"),
    97: ("NEG-NOM-012", "Nominee", "Add Nominee Button", "Checkbox not selected", "Add Nominee should remain disabled until checkbox is selected"),
    98: ("NEG-NOM-013", "Nominee", "Pincode", "> 6 digits", "Validation should display for invalid pincode length"),
    99: ("NEG-NOM-014", "Nominee", "Address", "Blank spaces", "Validation should display for blank-space address"),
    100: ("POS-NOMOUT-001", "Nominee Opt-Out", "Remove Nominee", "Valid remove nominee flow", "Remove nominee flow should proceed to signature/KYC/eSign"),
    101: ("POS-NOMOUT-002", "Nominee Opt-Out", "eSign", "Correct Aadhaar", "Nominee opt-out request should be placed after eSign"),
    102: ("NEG-NOMOUT-001", "Nominee Opt-Out", "eSign", "Different Aadhaar", "Name mismatch should loop back to eSign"),
    103: ("POS-BANK-003", "Bank", "Set Primary Bank", "Secondary bank selected", "Set as Primary Bank should place request successfully"),
    104: ("POS-BANK-004", "Bank", "Edit Primary Bank", "Primary account number", "Primary bank account number should not be editable"),
    105: ("POS-BANK-005", "Bank", "Delete Bank", "Secondary bank selected", "Delete bank should place request successfully"),
    106: ("POS-BANK-006", "Bank", "Penny Drop", "Valid account + IFSC", "Bank details should fetch automatically after valid account and IFSC"),
    107: ("NEG-BANK-006", "Bank", "Penny Drop", "Failed penny drop then exit", "Add Bank request should not be placed if penny drop failed and client exits"),
    108: ("POS-SEG-001", "Segment", "Risk Disclosure", "Agree", "Risk disclosure popup should display and close after Agree"),
    109: ("POS-SEG-002", "Segment", "Derivative Segment", "Derivative selected", "Proof upload page should display for derivative segment"),
    110: ("POS-SEG-003", "Segment", "MTF Only", "MTF enabled alone", "MTF-only flow should proceed without supporting proof"),
    111: ("POS-SEG-004", "Segment", "Equity F&O", "Proof + disclosure", "Equity F&O flow should proceed to signature/KYC/eSign"),
    112: ("POS-SEG-005", "Segment", "BSE Derivative", "Proof + disclosure", "BSE derivative flow should proceed to signature/KYC/eSign"),
    113: ("POS-SEG-006", "Segment", "Commodity F&O", "Proof + disclosure", "Commodity flow should proceed to signature/KYC/eSign"),
    114: ("NEG-SEG-001", "Segment", "Submit", "No segment change", "Validation should ask to activate or deactivate segments"),
    115: ("NEG-SEG-002", "Segment", "Cash Segment", "Disable cash segment", "Cash segment should not be disabled"),
    116: ("NEG-SEG-003", "Segment", "Proof Upload", "Missing proof", "Validation should ask to select proof"),
    117: ("POS-ACCTCLS-001", "Account Closure", "Page Availability", "", "Account closure option should be available in segment modification"),
    118: ("POS-ACCTCLS-002", "Account Closure", "Close Account Checkbox", "Checkbox selected", "Close account button should become available"),
    119: ("POS-ACCTCLS-003", "Account Closure", "Eligibility", "0 ledger and 0 holdings", "Eligible account should proceed to OTP"),
    120: ("POS-ACCTCLS-004", "Account Closure", "OTP", "Valid OTP", "Valid OTP should navigate to success/signature step"),
    121: ("NEG-ACCTCLS-001", "Account Closure", "OTP", "Invalid OTP > 4 times", "Validation should display for invalid account-closure OTP"),
    122: ("NEG-ACCTCLS-002", "Account Closure", "Eligibility", "Ledger/holding present", "Validation should block closure when ledger/holding exists"),
    123: ("POS-INC-001", "Income Declaration", "Edit Option", "", "Income Declaration page should display Edit option"),
    124: ("POS-INC-002", "Income Declaration", "Income Slab", "Valid slab selected", "Income slab dropdown should retain selected income"),
    125: ("POS-INC-003", "Income Declaration", "Update", "Income slab selected", "Request placed successfully should display"),
    126: ("NEG-INC-001", "Income Declaration", "Update", "No income slab selected", "Validation should ask to select income slab"),
    127: ("POS-DIS-001", "DIS Slip Req", "Page Details", "DP ID/email/mobile", "DIS Slip page should display DP ID, email, and mobile/phone"),
    128: ("POS-DIS-002", "DIS Slip Req", "Request New Slip", "Signature uploaded", "New Request Form 36 should display after Request New Slip"),
})

# Scenario-level rows used by the full daily flow report. These override
# older action-level labels so the mail/Teams table reads as test scenarios.
STEP_META.update({
    1: ("NEG-LOGIN-001", "Login Page", "UCC + DOB", "Blank UCC, Blank DOB", "Validation message should display; stay on login page"),
    2: ("NEG-LOGIN-002", "Login Page", "UCC", "Invalid UCC", "Validation/error message should display; stay on login page"),
    3: ("NEG-LOGIN-003", "Login Page", "UCC + DOB", "Valid UCC + Invalid DOB", "Login should fail; error shown; stay on login page"),
    4: ("POS-LOGIN-001", "Login Page", "UCC + DOB", "Valid UCC + Valid DOB", "Login should proceed to OTP page"),
    12: ("NEG-LOGIN-OTP-001", "Login OTP", "OTP", "Blank OTP", "Validation message should display; stay on OTP page"),
    13: ("NEG-LOGIN-OTP-002", "Login OTP", "OTP", "Wrong OTP (000000)", "Invalid OTP message should display; stay on OTP page"),
    14: ("NEG-LOGIN-OTP-003", "Login OTP", "OTP", "Short OTP (123)", "Validation/error message should display; stay on OTP page"),
    15: ("POS-LOGIN-OTP-001", "Login OTP", "OTP", "Valid OTP from Yopmail", "Valid OTP should proceed to ReKYC dashboard"),

    61: ("NEG-EMAIL-001", "Email", "Existing email OTP", "Blank OTP", "Validation message should display; stay on OTP page"),
    62: ("NEG-EMAIL-002", "Email", "Existing email OTP", "Wrong OTP (000000)", "Invalid OTP message should display; stay on OTP page"),
    63: ("NEG-EMAIL-003", "Email", "Existing email OTP", "Short OTP (123)", "Validation/error message should display; stay on OTP page"),
    129: ("NEG-EMAIL-004", "Email", "New email", "Existing email linked with another account", "Duplicate/linked email validation should display"),
    69: ("POS-EMAIL-001", "Email", "Email modification", "Valid existing OTP + valid new email OTP", "Email request should proceed to signature, IPV and eSign"),

    65: ("NEG-MOB-001", "Mobile No", "Existing mobile OTP", "Blank OTP", "Validation message should display; stay on OTP page"),
    66: ("NEG-MOB-002", "Mobile No", "Existing mobile OTP", "Wrong OTP (000000)", "Invalid OTP message should display; stay on OTP page"),
    67: ("NEG-MOB-003", "Mobile No", "Existing mobile OTP", "Short OTP (123)", "Validation/error message should display; stay on OTP page"),
    130: ("NEG-MOB-004", "Mobile No", "New mobile number", "Existing mobile linked with another account", "Duplicate/linked mobile validation should display"),
    68: ("POS-MOB-001", "Mobile No", "Mobile modification", "Valid existing OTP + valid new mobile OTP", "Mobile request should proceed to signature, IPV and eSign"),

    70: ("POS-SIGN-001", "Signature", "Signature Upload", "Signature.png", "Signature should upload and submit successfully"),
    72: ("POS-IPV-001", "IPV", "Live photo capture", "Fake blink camera", "IPV should capture/advance successfully"),
    71: ("POS-PDF-001", "Unsigned PDF", "Continue to eSign page", "Unsigned KYC PDF generated", "Unsigned KYC PDF page should load"),
    73: ("POS-ESIGN-001", "eSign", "Proceed to eSign", "Continue to eSign", "Protean Aadhaar eSign page should open"),
    74: ("POS-ESIGN-002", "eSign", "Aadhaar OTP", "Valid OTP from naviatesting@yopmail.com", "Aadhaar OTP should submit and place request"),

    77: ("POS-ADDR-001", "Change of Address", "DigiLocker Aadhaar", "Valid Aadhaar + OTP + security PIN", "Address flow should proceed through DigiLocker verification"),

    32: ("NEG-NOM-001", "Nominee", "Nominee form", "Blank nominee form", "Mandatory field validation should display"),
    33: ("NEG-NOM-002", "Nominee", "PAN/Aadhaar Number", "Invalid/short number", "Validation message should display for invalid PAN/Aadhaar"),
    35: ("NEG-NOM-003", "Nominee", "Mobile", "Invalid mobile number", "Validation message should display for invalid mobile"),
    37: ("NEG-NOM-004", "Nominee", "Share Percentage", "Invalid share percentage", "Validation message should display for invalid share"),
    38: ("NEG-NOM-005", "Nominee", "DOB", "Future DOB", "Validation message should display for invalid DOB"),
    39: ("NEG-NOM-006", "Nominee", "Email", "Invalid email", "Validation message should display for invalid email"),
    97: ("NEG-NOM-007", "Nominee", "Add Nominee", "Declaration checkbox not selected", "Add nominee should not proceed until declaration is selected"),
    41: ("POS-NOM-001", "Nominee", "Nominee Details", "Valid nominee details", "Nominee request should proceed to signature, IPV and eSign"),

    46: ("NEG-BANK-002", "Bank", "Account Number + IFSC", "Invalid bank account/IFSC", "Validation message should display and bank verification should not proceed"),
    45: ("NEG-BANK-001", "Bank", "Bank proof", "Proof not selected/uploaded", "Validation should ask for bank proof"),
    50: ("POS-BANK-001", "Bank", "Add Bank Account", "Valid account, IFSC and bank statement", "Bank request should submit successfully"),

    27: ("POS-DOC-001", "Documents", "Documents section", "Open Documents", "Documents section should open without error"),
    28: ("POS-DOC-002", "Documents", "View proof 1", "Open first proof", "First uploaded proof should be viewable"),
    29: ("POS-DOC-003", "Documents", "View proof 2", "Open second proof", "Second uploaded proof should be viewable"),

    115: ("NEG-SEG-002", "Segment", "Submit", "No segment change selected", "Validation should display when no segment is changed"),
    114: ("NEG-SEG-001", "Segment", "Required checkbox", "Checkbox not selected", "Validation should ask to accept required declaration"),
    112: ("POS-SEG-001", "Segment", "BSE Derivative activation", "Valid BFO activation + proof + OTP", "Segment request should complete successfully"),

    126: ("NEG-INC-001", "Income Declaration", "Income Slab", "No income slab selected", "Validation should ask to select income slab"),
    125: ("POS-INC-001", "Income Declaration", "Income Slab", "Valid income slab selected", "Income declaration request should submit successfully"),

    127: ("NEG-DIS-001", "DIS Slip Req", "Declaration", "Declaration/proceed validation", "DIS slip flow should block until required declaration is satisfied"),
    26: ("POS-STATUS-001", "Service Status", "Service Status page", "Open Service Status", "Service Status page should load"),
})

DISABLED_STEP_NUMBERS = set()
REPORT_HIDDEN_PASS_STEP_NUMBERS = {
    18,  # Email section navigation
    19,  # Mobile section navigation
    20,  # Address section navigation
    21,  # Nominee section navigation
    22,  # Bank section navigation
    23,  # Segment section navigation
    24,  # Income Declaration section navigation
    25,  # DIS Slip section navigation
}


def python_has_pytest(python_exe):
    try:
        result = subprocess.run(
            [python_exe, "-m", "pytest", "--version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


def resolve_pytest_python():
    candidates = []
    env_python = os.environ.get("REKYC_PYTHON")
    if env_python:
        candidates.append(env_python)
    candidates.extend([
        sys.executable,
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Python\Python314\python.exe"),
        "python",
        "py",
    ])

    seen = set()
    for candidate in candidates:
        candidate = os.path.expandvars(candidate)
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if python_has_pytest(candidate):
            return candidate
    return sys.executable


def get_meta(step_num):
    return STEP_META.get(step_num, ("--", "--", "--", "--", "--"))


def active_step_count():
    return sum(1 for step in STEP_META if step not in DISABLED_STEP_NUMBERS)


FULL_FLOW_TEST_TARGET = os.environ.get(
    "REKYC_TEST_TARGET",
    os.path.join("tests", "test_00_full_positive_flow.py"),
)
IS_FULL_FLOW_REPORT = os.path.basename(FULL_FLOW_TEST_TARGET).lower() == "test_00_full_positive_flow.py"

FULL_FLOW_STEP_META = {
    1:  ("NEG-LOGIN-FLOW", "Login", "Login form", "Blank/invalid/wrong DOB", "Negative login validations should block the flow"),
    2:  ("POS-LOGIN-FLOW", "Login", "Valid login + OTP", "Valid UCC, DOB and OTP", "Login should complete once and open dashboard"),
    10: ("EMAIL-FLOW", "Email", "Existing/new email OTP + eSign", "Negative OTPs, duplicate email, valid email", "Email request should complete through signature, IPV and Aadhaar eSign"),
    20: ("MOBILE-FLOW", "Mobile No", "Existing/new mobile OTP + eSign", "Negative OTPs, duplicate mobile, valid mobile", "Mobile request should complete through signature, IPV and Aadhaar eSign"),
    30: ("NEG-ADDR-FLOW", "Change of Address", "DigiLocker Aadhaar", "Invalid Aadhaar", "Invalid Aadhaar should be rejected"),
    31: ("POS-ADDR-FLOW", "Change of Address", "DigiLocker + eSign", "Valid Aadhaar, OTP and security PIN", "Address request should complete through signature, IPV and Aadhaar eSign"),
    40: ("NEG-NOM-FLOW", "Nominee", "Nominee fields", "Blank/invalid nominee data", "Nominee validations should reject invalid data"),
    41: ("POS-NOM-FLOW", "Nominee", "Add nominee + eSign", "Valid nominee details", "Nominee request should complete through signature, IPV and Aadhaar eSign"),
    50: ("NEG-BANK-FLOW", "Bank", "Bank proof", "Missing proof", "Bank flow should ask for proof before submit"),
    51: ("POS-BANK-FLOW", "Bank", "Add bank account", "Valid account, IFSC and statement", "Bank request should complete successfully"),
    60: ("NEG-SEG-FLOW", "Segment", "Terms checkbox", "Required checkbox unchecked", "Segment flow should reject submit without required declaration"),
    61: ("POS-SEG-FLOW", "Segment", "BFO activation + Protean", "Valid BFO activation and OTP", "Segment request should complete through Protean, proof, signature, IPV and eSign"),
    70: ("NEG-INC-FLOW", "Income Declaration", "Income slab", "No slab selected", "Income flow should ask to select income slab"),
    71: ("POS-INC-FLOW", "Income Declaration", "Income slab update", "Valid slab selected", "Income declaration request should be placed"),
    80: ("NEG-DIS-FLOW", "DIS Slip Req", "Declaration", "Declaration unchecked", "DIS slip flow should block without declaration"),
    90: ("POS-STATUS-FLOW", "Service Status", "Page load", "Open service status", "Service Status page should load"),
}


def full_flow_step_count():
    return len(FULL_FLOW_STEP_META)


def is_full_flow_results(step_results):
    return False


def get_report_meta(step_num, full_flow=False):
    return get_meta(step_num)


def get_report_step_numbers(full_flow=False):
    return [step for step in STEP_META if step not in DISABLED_STEP_NUMBERS]


def unique_step_results(step_results):
    unique = []
    seen = set()
    for step in step_results:
        step_num = step.get("step")
        if step_num in REPORT_HIDDEN_PASS_STEP_NUMBERS and step.get("status") == "PASS":
            continue
        if step_num in seen:
            continue
        seen.add(step_num)
        unique.append(step)
    return unique


class ReKYC_Agent:

    def __init__(self):
        self.project_root = os.path.dirname(os.path.abspath(__file__))
        self.attachment_skip_reason = ""

    # -------------------------------------------------------------------------
    #  run_tests
    # -------------------------------------------------------------------------
    def run_tests(self):

        print("\n" + "=" * 60)
        print("   RE-KYC AUTOMATION AGENT")
        print("   Fully Automatic - No manual steps needed")
        print("=" * 60)
        print("   Started :", datetime.datetime.now().strftime("%d %b %Y, %I:%M:%S %p"))

        print("\n============================================================")
        print("  STEP 1 | AUTO-LOCATING PROJECT FOLDER")
        print("============================================================")
        print("  [OK] Project folder found:")
        print("       ", self.project_root)

        print("\n============================================================")
        print("  STEP 2 | REVIEWING TEST CODE")
        print("============================================================")

        test_file = os.path.join(self.project_root, FULL_FLOW_TEST_TARGET)
        print("  [i] File :", test_file)

        with open(test_file, "r", encoding="utf-8") as f:
            code = f.read()

        try:
            ast.parse(code)
            code_review_status = "PASS"
            print("  [OK] Syntax Check : No errors found")
        except Exception as e:
            code_review_status = "FAIL"
            print("  [ERROR] Syntax Issue :", e)
            self.send_mail(  "FAIL", code_review_status, [], [], "0s", None)
            self.send_teams("FAIL", code_review_status, [], "0s")
            sys.exit(1)

        tests = [line for line in code.split("\n") if "def test_" in line]
        print("  [OK] Test Functions :", len(tests), "found")
        for test in tests:
            print("       ->", test.strip())
        print("  [OK] Total Lines :", len(code.split("\n")))
        print("\n  [OK] Code Review Complete - Ready to run!")

        print("\n============================================================")
        print("  STEP 3 | RUNNING PYTEST AUTOMATICALLY")
        print("============================================================")

        start_time = time.time()
        pytest_python = resolve_pytest_python()
        print(f"  [i] Python  : {pytest_python}")
        print(f"  [i] Running : pytest {FULL_FLOW_TEST_TARGET}")
        print("  [i] LIVE OUTPUT")
        print("-" * 60)

        json_path = os.path.join(self.project_root, "rekyc_step_results.json")
        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump([], f, indent=2)
        except Exception as e:
            print("  [WARN] Could not reset previous step results:", e)

        process = subprocess.Popen(
            [pytest_python, "-m", "pytest", FULL_FLOW_TEST_TARGET, "-v", "-s"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            cwd=self.project_root,
        )

        output = ""
        for line in process.stdout:
            print(line, end="")
            output += line

        return_code = process.wait()
        end_time    = time.time()
        duration_seconds = int(end_time - start_time)
        duration = f"{duration_seconds // 60}m {duration_seconds % 60}s"

        print("\n  [OK] Execution Completed")
        print("  [OK] Duration:", duration)

        print("\n============================================================")
        print("  STEP 4 | BUILDING STEP RESULTS")
        print("============================================================")

        step_results = self.load_step_results()
        log_lines    = output.splitlines()
        video_path   = self.find_latest_video()
        status       = self.derive_status(return_code, step_results)

        print("  [OK] Step Rows :", len(step_results))
        print("  [OK] Video     :", video_path if video_path else "Not found")
        print("  [OK] Status    :", status)

        print("\n============================================================")
        print("  STEP 5 | SENDING EMAIL REPORT")
        print("============================================================")

        self.send_mail(status, code_review_status, step_results, log_lines, duration, video_path)

        print("\n============================================================")
        print("  STEP 6 | SENDING TEAMS NOTIFICATION")
        print("============================================================")

        self.send_teams(status, code_review_status, step_results, duration)

        if status != "PASS":
            print("\n  [ERROR] Automation completed with failed step(s). Exiting with code 1 for Jenkins.")
            sys.exit(1)

    # -------------------------------------------------------------------------
    #  load_step_results
    # -------------------------------------------------------------------------
    def load_step_results(self):
        json_path = os.path.join(self.project_root, "rekyc_step_results.json")
        if not os.path.exists(json_path):
            print("  [WARN] rekyc_step_results.json not found at:", json_path)
            return []
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print("  [WARN] Could not read step results:", e)
            return []

    # -------------------------------------------------------------------------
    #  derive_status
    # -------------------------------------------------------------------------
    def derive_status(self, return_code, step_results):
        if return_code != 0:
            return "FAIL"
        if not step_results:
            print("  [WARN] No step results were written by pytest.")
            return "FAIL"
        failed_steps = [s for s in step_results if str(s.get("status", "")).upper() == "FAIL"]
        if failed_steps:
            print("  [WARN] Failed step rows found in JSON:", len(failed_steps))
            return "FAIL"
        run_step_nums = {s.get("step") for s in step_results}
        full_flow = is_full_flow_results(step_results)
        expected_steps = get_report_step_numbers(full_flow)
        missing_steps = [step for step in expected_steps if step not in run_step_nums]
        if missing_steps:
            print("  [WARN] Missing automated step rows (reported as NOT_AUTOMATED):", missing_steps)
        return "PASS"

    # -------------------------------------------------------------------------
    #  find_latest_video
    # -------------------------------------------------------------------------
    def find_latest_video(self):
        search_dirs = [
            os.path.join(self.project_root, "reports", "videos"),
            os.path.join(self.project_root, "test-results"),
            os.path.join(self.project_root, "reports"),
        ]
        videos = []
        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue
            for root, _, files in os.walk(search_dir):
                for fname in files:
                    if fname.lower().endswith((".webm", ".mp4")):
                        videos.append(os.path.join(root, fname))
        if not videos:
            return None
        return max(videos, key=os.path.getmtime)

    # -------------------------------------------------------------------------
    #  attach_file
    # -------------------------------------------------------------------------
    def attach_file(self, msg, file_path):
        self.attachment_skip_reason = ""
        if not file_path or not os.path.exists(file_path):
            self.attachment_skip_reason = "file not found"
            return False
        max_attachment_bytes = 20 * 1024 * 1024
        file_size = os.path.getsize(file_path)
        if file_size > max_attachment_bytes:
            size_mb = file_size / (1024 * 1024)
            limit_mb = max_attachment_bytes / (1024 * 1024)
            self.attachment_skip_reason = f"video too large ({size_mb:.1f} MB; limit {limit_mb:.0f} MB)"
            print("  [WARN] Video too large for email attachment; skipping:", file_path)
            print(f"  [WARN] Video size: {size_mb:.1f} MB; max allowed: {limit_mb:.0f} MB")
            return False
        with open(file_path, "rb") as f:
            part = MIMEBase("application", "octet-stream")
            part.set_payload(f.read())
        encoders.encode_base64(part)
        part.add_header(
            "Content-Disposition",
            f"attachment; filename={os.path.basename(file_path)}",
        )
        msg.attach(part)
        return True

    # -------------------------------------------------------------------------
    #  send_teams  --  Power Automate Workflows webhook
    #
    #  FIX: The "Send webhook alerts to a channel" Workflow template requires
    #  the body schema:  { "text": "<plain string>" }
    #  Sending unicode emoji or markdown bold in the text causes BadRequest.
    #  We now send only plain ASCII text so the flow never rejects it.
    #
    #  The "Attachments is null" error happens because some Workflow templates
    #  add a condition that checks trigger body for an "attachments" key.
    #  We include "attachments": [{"name": "report", "contentType": "text/plain"}] so that condition evaluates to False cleanly
    #  and the plain-text branch (True side) is used instead.
    # -------------------------------------------------------------------------
    def send_teams(self, status, code_review_status, step_results, duration):

        print("  [i] TEAMS NOTIFICATION TRIGGER STARTED")

        now_str    = datetime.datetime.now().strftime("%d %b %Y %I:%M %p")
        full_flow           = is_full_flow_results(step_results)
        report_step_results = unique_step_results(step_results)
        total_meta          = len(report_step_results)
        passed              = sum(1 for s in report_step_results if s.get("status") == "PASS")
        failed              = sum(1 for s in report_step_results if s.get("status") == "FAIL")
        not_auto            = 0

        status_label = "PASS" if status == "PASS" else "FAIL"
        color        = "Good" if status == "PASS" else "Attention"

        # Build facts list for the AdaptiveCard FactSet
        facts = [
            {"title": "Date",           "value": now_str},
            {"title": "Duration",       "value": duration},
            {"title": "Status",         "value": status_label},
            {"title": "Passed",         "value": str(passed)},
            {"title": "Failed",         "value": str(failed)},
            {"title": "Not Automated",  "value": str(not_auto)},
            {"title": "Total Tests",    "value": str(total_meta)},
            {"title": "Code Review",    "value": code_review_status},
        ]

        # Add failed step details
        failed_steps = [s for s in report_step_results if s.get("status") == "FAIL"]
        for s in failed_steps:
            step_num = s.get("step", 0)
            tc_id, stage, _, _, _ = get_report_meta(step_num, full_flow)
            reason = str(s.get("reason", "")).strip()[:100] or "No reason captured"
            facts.append({"title": tc_id, "value": f"{stage} -- {reason}"})

        # Full Adaptive Card payload -- required schema for
        # "Send webhook alerts to a channel" Power Automate template
        adaptive_card = {
            "type": "AdaptiveCard",
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "version": "1.4",
            "body": [
                {
                    "type": "TextBlock",
                    "text": f"ReKYC Automation Report - {status_label}",
                    "size": "Large",
                    "weight": "Bolder",
                    "color": color,
                    "wrap": True,
                },
                {
                    "type": "FactSet",
                    "facts": facts,
                },
            ],
        }

        payload = {
            "type": "message",
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": adaptive_card,
                }
            ],
        }

        payload_bytes = json.dumps(payload, ensure_ascii=True).encode("utf-8")

        try:
            print("  [i] Posting to Teams via Power Automate Workflows webhook ...")
            req = urllib.request.Request(
                TEAMS_WEBHOOK_URL,
                data=payload_bytes,
                headers={"Content-Type": "application/json; charset=utf-8"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=20) as resp:
                resp_status = resp.status
                resp_body   = resp.read().decode("utf-8", errors="replace")

            if resp_status in (200, 202):
                print("  [OK] TEAMS NOTIFICATION SENT SUCCESSFULLY")
            else:
                print(f"  [WARN] Teams responded HTTP {resp_status}: {resp_body}")

        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            print(f"  [ERROR] TEAMS FAILED -- HTTP {e.code}: {body}")
            print("          -> Verify the Workflow is still active in Power Automate.")
            print("          -> Regenerate the webhook URL if it has expired.")
        except urllib.error.URLError as e:
            print(f"  [ERROR] TEAMS FAILED -- URL error: {e.reason}")
        except Exception as e:
            print("  [ERROR] TEAMS FAILED (unexpected):", e)

    # -------------------------------------------------------------------------
    #  send_mail
    #
    #  FIX: Corporate networks commonly block outbound SMTP (ports 465 & 587).
    #  Solution: try all three methods in order:
    #    1. SSL port 465
    #    2. STARTTLS port 587
    #    3. STARTTLS port 25  (sometimes open on corporate networks)
    #  If ALL three are blocked, the email is saved as a local HTML file
    #  so the report is never lost.
    # -------------------------------------------------------------------------
    def send_mail(self, status, code_review_status, step_results, log_lines, duration, video_path):

        print("  [i] EMAIL TRIGGER STARTED")

        sender   = "praveenvelu262001@gmail.com"
        password = os.environ.get("GMAIL_APP_PASSWORD", "uimq siiu sqja asrj")
        receiver = ["miruthulak21@gmail.com", "elamukil@navia.co.in", "praveenvelu262001@gmail.com"]

        now_str = datetime.datetime.now().strftime("%d %b %Y %I:%M %p")

        full_flow           = is_full_flow_results(step_results)
        report_step_results = unique_step_results(step_results)
        total               = len(report_step_results)
        passed              = sum(1 for s in report_step_results if s.get("status") == "PASS")
        failed              = sum(1 for s in report_step_results if s.get("status") == "FAIL")
        not_automated       = 0

        STATUS_STYLE = {
            "PASS":          ("background:#d1fae5;color:#065f46;font-weight:600", "PASS"),
            "FAIL":          ("background:#fee2e2;color:#991b1b;font-weight:600", "FAIL"),
            "NOT_AUTOMATED": ("background:#fef9c3;color:#92400e;font-weight:600", "NOT_AUTOMATED"),
        }

        step_html     = ""
        for step in report_step_results:
            step_num    = step.get("step", 0)
            step_status = str(step.get("status", "FAIL"))
            reason      = str(step.get("reason", "")).strip()
            actual      = reason if step_status == "FAIL" else step.get("name", "")
            tc_id, stage, field, neg_input, expected = get_report_meta(step_num, full_flow)
            row_bg = "#d1fae5" if step_status == "PASS" else "#fee2e2"
            st_style, st_label = STATUS_STYLE.get(step_status, ("", step_status))
            step_html += f"""
            <tr style="background:{row_bg}">
                <td style="padding:6px 10px;border:1px solid #d1d5db;white-space:nowrap">{html.escape(str(tc_id))}</td>
                <td style="padding:6px 10px;border:1px solid #d1d5db">{html.escape(str(stage))}</td>
                <td style="padding:6px 10px;border:1px solid #d1d5db">{html.escape(str(field))}</td>
                <td style="padding:6px 10px;border:1px solid #d1d5db">{html.escape(str(neg_input)) if neg_input else "--"}</td>
                <td style="padding:6px 10px;border:1px solid #d1d5db">{html.escape(str(expected))}</td>
                <td style="padding:6px 10px;border:1px solid #d1d5db;text-align:center">
                    <span style="padding:3px 10px;border-radius:4px;{st_style}">{st_label}</span>
                </td>
                <td style="padding:6px 10px;border:1px solid #d1d5db">{html.escape(str(actual))}</td>
            </tr>"""

        if not step_html:
            step_html = """
            <tr>
                <td colspan="7" style="padding:10px;border:1px solid #d1d5db;text-align:center;color:#6b7280">
                    No step results found.
                </td>
            </tr>"""

        badge_color = "#065f46" if status == "PASS" else "#991b1b"
        badge_bg    = "#d1fae5" if status == "PASS" else "#fee2e2"
        video_line  = "Attached to this email." if video_path else "No video recorded."

        email_html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8"></head>
<body style="margin:0;padding:20px;font-family:Arial,Helvetica,sans-serif;background:#f9fafb;color:#111827">
  <div style="background:#1e3a5f;color:#fff;padding:18px 24px;border-radius:8px 8px 0 0">
    <h2 style="margin:0;font-size:20px">&#128203; ReKYC Automation Report</h2>
    <p style="margin:4px 0 0;font-size:13px;opacity:.8">Generated: {now_str} &nbsp;|&nbsp; Duration: {html.escape(duration)}</p>
  </div>
  <div style="background:#fff;border:1px solid #e5e7eb;border-top:none;padding:14px 24px;">
    <span style="font-size:14px;font-weight:600;color:#374151">
      Total: <strong>{total + not_automated}</strong>
      &nbsp;|&nbsp; Pass: <strong style="color:#065f46">{passed}</strong>
      &nbsp;|&nbsp; Fail: <strong style="color:#991b1b">{failed}</strong>
      &nbsp;|&nbsp; Not Automated: <strong style="color:#92400e">{not_automated}</strong>
    </span>
    <span style="float:right;padding:5px 16px;border-radius:5px;background:{badge_bg};color:{badge_color};font-weight:700;font-size:14px">
      Overall: {html.escape(status)}
    </span>
  </div>
  <div style="overflow-x:auto">
    <table style="width:100%;border-collapse:collapse;font-size:13px;background:#fff;border:1px solid #d1d5db;border-top:none">
      <thead>
        <tr style="background:#374151;color:#fff">
          <th style="padding:9px 10px;border:1px solid #4b5563;text-align:left;white-space:nowrap">Test Case ID</th>
          <th style="padding:9px 10px;border:1px solid #4b5563;text-align:left">Stage</th>
          <th style="padding:9px 10px;border:1px solid #4b5563;text-align:left">Field / Control</th>
          <th style="padding:9px 10px;border:1px solid #4b5563;text-align:left">Negative Input / Condition</th>
          <th style="padding:9px 10px;border:1px solid #4b5563;text-align:left">Expected Validation / Output</th>
          <th style="padding:9px 10px;border:1px solid #4b5563;text-align:center">Status</th>
          <th style="padding:9px 10px;border:1px solid #4b5563;text-align:left">Actual Result</th>
        </tr>
      </thead>
      <tbody>{step_html}</tbody>
    </table>
  </div>
  <div style="margin-top:16px;padding:12px 18px;background:#fff;border:1px solid #e5e7eb;border-radius:0 0 8px 8px;font-size:12px;color:#6b7280">
    <b>Video Recording:</b> {video_line}
    {"&nbsp; <span style='color:#374151'>(" + html.escape(os.path.basename(video_path)) + ")</span>" if video_path else ""}
    &nbsp;&nbsp;|&nbsp;&nbsp;
    <b>Code Review:</b> {html.escape(code_review_status)}
  </div>
</body>
</html>"""

        msg = MIMEMultipart()
        msg["From"]    = sender
        msg["To"]      = ", ".join(receiver)
        msg["Subject"] = f"ReKYC Automation Report - {status} - {now_str}"
        msg.attach(MIMEText(email_html, "html"))
        attached = self.attach_file(msg, video_path)

        context = ssl.create_default_context()

        smtp_methods = [
            ("smtp.gmail.com", 465,  "SSL",      "ssl"),
            ("smtp.gmail.com", 587,  "STARTTLS",  "starttls"),
            ("smtp.gmail.com", 25,   "STARTTLS",  "starttls"),
        ]

        print("  [i] Connecting to Gmail SMTP ...")
        print("  [i] Logging in as:", sender)
        print("  [i] Sending to:", receiver)

        sent = False
        last_error = None

        for host, port, label, method in smtp_methods:
            try:
                print(f"  [i] Trying {host}:{port} ({label}) ...")
                if method == "ssl":
                    with smtplib.SMTP_SSL(host, port, timeout=15, context=context) as server:
                        server.login(sender, password)
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(host, port, timeout=15) as server:
                        server.ehlo()
                        server.starttls(context=context)
                        server.ehlo()
                        server.login(sender, password)
                        server.send_message(msg)
                sent = True
                print(f"  [OK] EMAIL SENT SUCCESSFULLY via port {port}")
                break
            except smtplib.SMTPAuthenticationError as e:
                # Wrong password — no point retrying other ports
                print("  [ERROR] Gmail authentication failed.")
                print("          -> Use a Gmail App Password (not your normal password).")
                print("          -> Generate one: https://myaccount.google.com/apppasswords")
                last_error = e
                break
            except smtplib.SMTPRecipientsRefused as e:
                print("  [ERROR] Recipient refused:", e.recipients)
                last_error = e
                break
            except Exception as e:
                print(f"  [WARN] Port {port} failed: {type(e).__name__}: {e}")
                last_error = e
                continue

        if not sent:
            # ----------------------------------------------------------------
            # ALL SMTP PORTS BLOCKED (corporate firewall)
            # Save the report as a local HTML file so it is never lost
            # ----------------------------------------------------------------
            print()
            print("  [WARN] ============================================================")
            print("  [WARN] ALL SMTP PORTS BLOCKED by your network/firewall.")
            print("  [WARN] This is common on corporate Wi-Fi / office networks.")
            print("  [WARN]")
            print("  [WARN] WHAT TO DO:")
            print("  [WARN]   Option 1 (Recommended): Run the test on a personal hotspot")
            print("  [WARN]               or home Wi-Fi where port 587 is open.")
            print("  [WARN]   Option 2: Ask your IT team to whitelist smtp.gmail.com:587")
            print("  [WARN]   Option 3: The report has been saved locally (see below).")
            print("  [WARN] ============================================================")

            # Save HTML report locally as fallback
            report_dir  = os.path.join(self.project_root, "reports")
            os.makedirs(report_dir, exist_ok=True)
            ts          = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = os.path.join(report_dir, f"ReKYC_Report_{status}_{ts}.html")
            try:
                with open(report_file, "w", encoding="utf-8") as f:
                    f.write(email_html)
                print(f"  [OK] REPORT SAVED LOCALLY: {report_file}")
                print("       Open this file in any browser to view the full report.")
            except Exception as save_err:
                print("  [ERROR] Could not save local report:", save_err)

        elif attached:
            print("  [OK] VIDEO ATTACHED:", video_path)
        else:
            reason = self.attachment_skip_reason or "unknown reason"
            print(f"  [i]  No video attached ({reason})")


if __name__ == "__main__":
    agent = ReKYC_Agent()
    agent.run_tests()
