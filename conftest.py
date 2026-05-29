import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

import pytest

# -- Headless auto-detection (Jenkins / CI) ------------------------------------
# Set REKYC_HEADLESS=false to force a visible browser locally
_headless = os.environ.get("REKYC_HEADLESS", "").lower()
if _headless == "false":
    HEADLESS = False
elif _headless == "true":
    HEADLESS = True
else:
    HEADLESS = bool(
        os.environ.get("CI") or
        os.environ.get("JENKINS_URL") or
        os.environ.get("JENKINS_HOME")
    )

print(f"\n[conftest] Browser : Microsoft Edge")
print(f"[conftest] Headless: {HEADLESS} (set REKYC_HEADLESS=true/false to override)\n")


# -- Tell pytest-playwright to launch Edge instead of Chromium -----------------
@pytest.fixture(scope="session")
def browser_name():
    return "chromium"          # Playwright's internal engine (Edge uses Chromium)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    return {
        **browser_type_launch_args,
        "headless": HEADLESS,
        "slow_mo":  500 if HEADLESS else 1000,
        # 'channel' switches Playwright from its bundled Chromium to the
        # locally installed Microsoft Edge browser
        "channel": "msedge",
        "args": [
            "--use-fake-ui-for-media-stream",
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
        ],
    }


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    return {
        **browser_context_args,
        "viewport": {
            "width":  1280,
            "height": 720,
        },
        "record_video_dir":  "reports/videos",
        "record_video_size": {
            "width":  854,
            "height": 480,
        },
        "permissions": ["camera", "geolocation"],
        "geolocation": {
            "latitude": 13.0827,
            "longitude": 80.2707,
            "accuracy": 25,
        },
        # Microsoft Edge user-agent -- must match the 'channel' above
        "user_agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36 "
            "Edg/124.0.0.0"          # ? Edge-specific token
        ),
    }
