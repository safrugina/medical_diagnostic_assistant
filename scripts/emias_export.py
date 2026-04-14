"""
emias_export.py — Script for automated export of medical data from EMIAS.

Sources:
  - Personal account "My Electronic Medical Record": https://lk.emias.mos.ru/
  - EMIAS.INFO portal (doctor inspections):          https://emias.info/login/
  Authentication via ESIA (Gosuslugi).

Supports export of:
- Inspections and consultations (documents/inspections/)
- Laboratory analyzes (documents/analyzes/)
- Instrumental researches (documents/researches/)

Usage:
    python emias_export.py
    python emias_export.py --period 90 --headless
    python emias_export.py --username +79001234567 --period 365

Configuration via .env:
    EMIAS_USERNAME=+7XXXXXXXXXX   (or SNILS: XXX-XXX-XXX XX)
    EMIAS_PASSWORD=your_password
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    TimeoutError as PlaywrightTimeoutError,
    async_playwright,
)
from rich.console import Console
from rich.progress import (
    Progress,
    SpinnerColumn,
    TextColumn,
    BarColumn,
    TaskProgressColumn,
)
from tqdm.asyncio import tqdm

# Import common project utilities
sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    EMIAS_INSPECTIONS_DIR,
    EMIAS_RESEARCHES_DIR,
    EMIAS_ANALYZES_DIR,
    build_target_filename,
    is_duplicate,
    print_import_summary,
    request_2fa_code,
    safe_click,
    safe_fill,
    save_file,
    setup_logging,
    wait_for_download,
)

# ─── Constants ───────────────────────────────────────────────────────────────

# Personal account "My Electronic Medical Record" (main patient portal)
EMIAS_LK_URL = "https://lk.emias.mos.ru"

# EMIAS.INFO portal (doctor inspections, secondary source)
EMIAS_INFO_URL = "https://emias.info"
EMIAS_INFO_LOGIN_URL = f"{EMIAS_INFO_URL}/login/"

# Entry point (lk.emias.mos.ru redirects to ESIA)
EMIAS_BASE_URL = EMIAS_LK_URL
EMIAS_LOGIN_URL = EMIAS_LK_URL + "/"

ESIA_URL = "https://esia.gosuslugi.ru"
GOSUSLUGI_URL = "https://gosuslugi.ru"

# Maximum number of retry attempts on errors
MAX_RETRIES = 3

# Element wait timeout (ms)
DEFAULT_TIMEOUT = 15_000
DOWNLOAD_TIMEOUT = 60_000
LOGIN_TIMEOUT = 30_000

# Delay between requests to reduce server load (sec)
POLITE_DELAY = 1.5

console = Console()


# ─── Authentication ───────────────────────────────────────────────────────────


async def login_via_esia(page: Page, username: str, password: str) -> bool:
    """
    Logs into EMIAS via ESIA (Gosuslugi).

    Algorithm:
    1. Open lk.emias.mos.ru — it auto-redirects to ESIA.
    2. If redirect didn't happen — find the "Login via Gosuslugi" button.
    3. On the ESIA page, enter login (phone/SNILS) and password.
    4. If 2FA is required — prompt the user for the code.
    5. Verify successful authentication.

    Args:
        page:     Playwright Page.
        username: Phone number or SNILS (format: +7XXXXXXXXXX or XXX-XXX-XXX XX).
        password: ESIA (Gosuslugi) password.

    Returns:
        True on successful authentication.
    """
    logger.info(f"Opening EMIAS personal account: {EMIAS_LOGIN_URL}")
    try:
        await page.goto(
            EMIAS_LOGIN_URL, timeout=LOGIN_TIMEOUT, wait_until="domcontentloaded"
        )
    except Exception as e:
        logger.error(f"Failed to open EMIAS page: {e}")
        return False

    await asyncio.sleep(2)
    logger.info(f"Current URL after navigation: {page.url}")

    # lk.emias.mos.ru usually redirects to ESIA immediately.
    # If not — look for the "Login via Gosuslugi" button.
    on_esia = (
        ESIA_URL in page.url or GOSUSLUGI_URL in page.url or "esia" in page.url.lower()
    )

    if not on_esia:
        logger.info(
            "ESIA redirect did not happen automatically. Looking for login button..."
        )
        esia_button_selectors = [
            "text=Войти через Госуслуги",
            "text=Госуслуги",
            "text=Войти",
            "a[href*='esia']",
            "a[href*='gosuslugi']",
            "button[class*='esia']",
            "[data-testid='esia-login-btn']",
            "a[class*='login']",
        ]
        clicked = False
        for selector in esia_button_selectors:
            if await safe_click(page, selector, timeout=5_000):
                clicked = True
                logger.info(f"Clicked login button: '{selector}'")
                await asyncio.sleep(2)
                break

        if not clicked:
            logger.warning(
                "ESIA button not found. Trying direct login at emias.info..."
            )
            # Fallback: emias.info/login/
            try:
                await page.goto(
                    EMIAS_INFO_LOGIN_URL,
                    timeout=LOGIN_TIMEOUT,
                    wait_until="domcontentloaded",
                )
                await asyncio.sleep(2)
            except Exception as e:
                logger.error(f"Failed to open emias.info/login/: {e}")
                return False

    # Wait for the ESIA login form to appear
    logger.info(f"URL after navigation: {page.url}")
    try:
        await page.wait_for_load_state("networkidle", timeout=LOGIN_TIMEOUT)
    except PlaywrightTimeoutError:
        await page.wait_for_load_state("domcontentloaded")

    # Fill ESIA login (phone / SNILS / email)
    login_selectors = [
        "#login",
        "input[name='login']",
        "input[id='login']",
        "input[type='tel']",
        "input[autocomplete='username']",
        "input[placeholder*='телефон']",
        "input[placeholder*='СНИЛС']",
        "input[placeholder*='Телефон']",
        "input[placeholder*='почта']",
    ]

    filled_login = False
    for selector in login_selectors:
        if await safe_fill(page, selector, username, timeout=5_000):
            logger.info(f"ESIA login entered (selector: {selector})")
            filled_login = True
            break

    if not filled_login:
        logger.error("ESIA login field not found. The page structure may have changed.")
        return False

    await page.keyboard.press("Tab")
    await asyncio.sleep(0.5)

    # Gosuslugi may show only the login field first, then the password field
    # Click "Next" if the password field is not yet visible
    password_visible = False
    for sel in ["input[type='password']", "#password"]:
        try:
            el = await page.query_selector(sel)
            if el and await el.is_visible():
                password_visible = True
                break
        except Exception:
            pass

    if not password_visible:
        for sel in ["text=Далее", "button[type='submit']", "text=Продолжить"]:
            if await safe_click(page, sel, timeout=5_000):
                await asyncio.sleep(2)
                break

    # Enter password
    password_selectors = [
        "#password",
        "input[name='password']",
        "input[type='password']",
        "input[autocomplete='current-password']",
    ]
    for selector in password_selectors:
        if await safe_fill(page, selector, password, timeout=8_000):
            logger.info("ESIA password entered")
            break

    # Click "Login"
    submit_selectors = [
        "button[type='submit']",
        "input[type='submit']",
        "text=Войти",
        "text=Вход",
        "[data-testid='login-submit']",
    ]
    for selector in submit_selectors:
        if await safe_click(page, selector, timeout=5_000):
            logger.info("Clicked ESIA login button")
            break

    # Handle 2FA and verify success
    return await handle_2fa_and_verify(page)


async def login_direct(page: Page, username: str, password: str) -> bool:
    """
    Direct login to EMIAS (without ESIA) — fallback option.

    Args:
        page:     Playwright Page.
        username: Login.
        password: Password.

    Returns:
        True on successful authentication.
    """
    logger.info("Trying direct login to EMIAS...")

    await safe_fill(
        page, "input[name='username'], #username, input[type='tel']", username
    )
    await safe_fill(
        page, "input[name='password'], #password, input[type='password']", password
    )
    await safe_click(page, "button[type='submit'], text=Войти")

    return await handle_2fa_and_verify(page)


async def handle_2fa_and_verify(page: Page) -> bool:
    """
    Handles two-factor authentication and verifies successful login.

    Waits up to 30 seconds: if a 2FA code field appears — prompts the user.
    Then verifies that we ended up in the personal account.

    Returns:
        True if login was successful.
    """
    await asyncio.sleep(2)

    # Check for 2FA code field
    twofa_selectors = [
        "input[name='otp']",
        "input[placeholder*='код']",
        "input[placeholder*='SMS']",
        "input[id*='otp']",
        "input[id*='sms']",
        "[data-testid='otp-input']",
    ]

    for selector in twofa_selectors:
        try:
            await page.wait_for_selector(selector, timeout=5_000)
            logger.info("Two-factor authentication detected")
            console.print(
                "\n[bold yellow]⚠ Two-factor authentication required[/bold yellow]"
            )
            code = await request_2fa_code(
                "Enter code from SMS or Gosuslugi push notification"
            )
            await safe_fill(page, selector, code)
            await safe_click(
                page,
                "button[type='submit'], text=Подтвердить, text=Войти",
                timeout=5_000,
            )
            await asyncio.sleep(2)
            break
        except PlaywrightTimeoutError:
            continue

    # Verify login success:
    # after ESIA auth, browser returns to lk.emias.mos.ru or emias.info
    await asyncio.sleep(3)
    current_url = page.url
    logger.info(f"URL after authentication: {current_url}")

    success_domains = ["lk.emias.mos.ru", "emias.mos.ru", "emias.info"]
    is_success = any(domain in current_url for domain in success_domains)
    still_on_auth = any(
        x in current_url for x in ["esia", "gosuslugi", "login", "error", "auth"]
    )

    if is_success and not still_on_auth:
        logger.info(f"Authentication successful. Current URL: {current_url}")
        return True

    # Additional check: look for signs of authenticated state on the page
    auth_indicators = [
        "[class*='profile']",
        "[class*='user-name']",
        "[class*='cabinet']",
        "text=Выйти",
        "text=Выход",
        "text=Личный кабинет",
    ]
    for selector in auth_indicators:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                logger.info(f"Authentication successful (found element: {selector})")
                return True
        except Exception:
            pass

    logger.error(f"Authentication failed. Current URL: {current_url}")
    return False


# ─── Data export ──────────────────────────────────────────────────────────────


async def _wait_for_main_page_ready(page: Page, timeout: int = 30_000) -> bool:
    """
    Waits until the lk.emias.mos.ru main page has fully loaded the React app.

    Readiness indicator: presence of the "my inspections" card:
    data-testid='inspections_card_container'. This guarantees the SPA
    is fully mounted and all data-testid buttons are interactive.

    Returns:
        True if page is loaded, False on timeout.
    """
    try:
        await page.wait_for_selector(
            "[data-testid='inspections_card_container']",
            timeout=timeout,
        )
        logger.debug("EMIAS main page is ready")
        return True
    except PlaywrightTimeoutError:
        logger.warning("EMIAS main page did not load within the allotted time")
        return False


async def _go_to_main_page(page: Page) -> bool:
    """
    Navigates the browser to the EMIAS personal account main page
    and waits for the React app to fully load.

    Called before each section export to ensure all navigation buttons
    (data-testid='*_open_button') are present in the DOM.

    Returns:
        True if the main page is ready, False on error.
    """
    logger.debug(f"Navigating to main page: {EMIAS_LK_URL}")
    try:
        await page.goto(
            EMIAS_LK_URL,
            timeout=LOGIN_TIMEOUT,
            wait_until="domcontentloaded",
        )
    except Exception as e:
        logger.warning(f"Failed to navigate to main page: {e}")
        return False
    return await _wait_for_main_page_ready(page)


async def _select_period_filter(
    page: Page,
    filter_prefix: str,
    period_days: int,
) -> None:
    """
    Clicks the period filter button in an EMIAS section card.

    lk.emias.mos.ru uses data-testid like "{prefix}_6m", "{prefix}_1y",
    "{prefix}_all" to filter by 6 months / 1 year / all time.

    Args:
        page:          Playwright Page.
        filter_prefix: Button prefix, e.g. "inspections_card".
        period_days:   Requested period in days.
    """
    if period_days <= 180:
        testid = f"{filter_prefix}_6m"
    elif period_days <= 365:
        testid = f"{filter_prefix}_1y"
    else:
        testid = f"{filter_prefix}_all"

    selector = f"[data-testid='{testid}']"
    if await safe_click(page, selector, timeout=5_000):
        logger.debug(f"Period filter applied: {testid}")
        await asyncio.sleep(1)
    else:
        logger.debug(f"Period filter not found: {testid}")


async def _find_items_by_testid_prefix(page: Page, prefix: str) -> list:
    """
    Returns root card elements by data-testid prefix.

    lk.emias.mos.ru names cards as "{prefix}<UUID>", and child
    elements as "{prefix}<UUID>_date", "{prefix}<UUID>_docName", etc.
    Returns only root elements whose data-testid after the prefix
    contains exactly a UUID (format 8-4-4-4-12).

    If no results for the given prefix (prefix is a guess,
    section pages may have different structure), performs a broad
    search for any "item_*_<UUID>" elements on the page.

    Args:
        page:   Playwright Page.
        prefix: E.g. "item_inspection_".

    Returns:
        List of Playwright element handles.
    """
    import re as _re

    UUID_RE = _re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )
    UUID_SUFFIX_RE = _re.compile(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    )

    def _is_root_item(testid: str, pfx: str) -> bool:
        suffix = testid[len(pfx) :]
        return bool(UUID_RE.match(suffix))

    # ── 1. Search by given prefix ────────────────────────────────────────────
    all_els = await page.query_selector_all(f"[data-testid^='{prefix}']")
    roots = [
        el
        for el in all_els
        if _is_root_item(await el.get_attribute("data-testid") or "", prefix)
    ]

    if roots:
        logger.debug(f"Found {len(roots)} elements for prefix '{prefix}'")
        return roots

    # ── 2. Generic fallback: any item_*_<UUID> on the page ──────────────────
    logger.debug(
        f"Prefix '{prefix}' yielded no results — searching for any item_*_<UUID>"
    )
    all_item_els = await page.query_selector_all("[data-testid^='item_']")
    for el in all_item_els:
        testid = await el.get_attribute("data-testid") or ""
        m = UUID_SUFFIX_RE.search(testid)
        # Root element: UUID is at the very end of testid
        if m and m.end() == len(testid):
            roots.append(el)

    if roots:
        # Log found prefixes for future debugging
        found_prefixes = set()
        for el in roots[:5]:
            testid = await el.get_attribute("data-testid") or ""
            m = UUID_SUFFIX_RE.search(testid)
            if m:
                found_prefixes.add(testid[: m.start()])
        logger.info(
            f"Generic item discovery: found {len(roots)} elements. "
            f"Prefixes on page: {found_prefixes}. "
            f"Update item_testid_prefix in code for precise search."
        )

    return roots


async def _close_modal(page: Page) -> None:
    """
    Closes an open ReactModal on lk.emias.mos.ru.

    Strategy (in descending priority):
    1. Click the close button inside the modal.
    2. Click the overlay (background area outside content) — standard way
       to close ReactModal with shouldCloseOnOverlayClick enabled.
    3. JS dispatch of KeyboardEvent Escape — more reliable than page.keyboard.press,
       since React listens to DOM-level events.
    4. Force-remove the portal via JS (nuclear option).
    """
    OVERLAY = ".ReactModal__Overlay--after-open"

    # 1. Close button inside the modal
    close_selectors = [
        ".ReactModal__Content button[aria-label*='lose']",
        ".ReactModal__Content button[aria-label*='акрыть']",
        ".ReactModal__Content [class*='close']",
        ".ReactModal__Content [class*='Close']",
    ]
    for sel in close_selectors:
        el = await page.query_selector(sel)
        if el:
            try:
                await el.click(timeout=2_000)
                await asyncio.sleep(0.5)
                break
            except Exception:
                pass

    # Check if already closed
    if not await page.query_selector(OVERLAY):
        return

    # 2. Click the overlay background (top-left corner — outside content)
    overlay_el = await page.query_selector(OVERLAY)
    if overlay_el:
        bbox = await overlay_el.bounding_box()
        if bbox:
            try:
                await page.mouse.click(bbox["x"] + 5, bbox["y"] + 5)
                await asyncio.sleep(0.5)
            except Exception:
                pass

    if not await page.query_selector(OVERLAY):
        return

    # 3. JS dispatch of Escape (React listens to document-level keydown)
    await page.evaluate("""() => {
        document.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Escape', keyCode: 27, which: 27,
            bubbles: true, cancelable: true
        }));
    }""")
    await asyncio.sleep(0.5)

    if not await page.query_selector(OVERLAY):
        return

    # 4. Force-remove from DOM (nuclear option)
    logger.debug("Force-closing ReactModal via JS")
    await page.evaluate("""() => {
        const portal = document.querySelector('.ReactModalPortal');
        if (portal) portal.innerHTML = '';
        document.body.classList.remove('ReactModal__Body--open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
    }""")
    await asyncio.sleep(0.3)

    # Final check
    try:
        await page.wait_for_selector(OVERLAY, state="hidden", timeout=2_000)
    except Exception:
        logger.warning("ReactModal could not be closed — continuing")


async def _download_via_modal(
    page: Page,
    view_btn,
    extra_btn_selectors: list[str],
) -> object | None:
    """
    Downloads a document from EMIAS via React Modal.

    Algorithm:
    1. Click the "_view" button — ReactModal opens.
    2. Find the download button INSIDE the modal.
    3. Click the button → wait for download event.
    4. Close the modal (Escape / × button).

    Args:
        page:                Playwright Page.
        view_btn:            Element handle of the view button (_view).
        extra_btn_selectors: Additional download button selectors.

    Returns:
        Playwright Download object or None.
    """
    MODAL_OVERLAY = ".ReactModal__Overlay--after-open"
    MODAL_CONTENT = ".ReactModal__Content"

    # Download buttons inside the modal (in priority order)
    MODAL_DL_SELECTORS = [
        f"{MODAL_CONTENT} [data-testid*='download']",
        f"{MODAL_CONTENT} [data-testid*='print']",
        f"{MODAL_CONTENT} button:has-text('Скачать')",
        f"{MODAL_CONTENT} button:has-text('Распечатать')",
        f"{MODAL_CONTENT} a[download]",
        f"{MODAL_CONTENT} a[href*='.pdf']",
        f"{MODAL_CONTENT} [class*='download']",
        f"{MODAL_CONTENT} [class*='Download']",
        f"{MODAL_CONTENT} [class*='print']",
        # Fallbacks — without modal restriction
        *extra_btn_selectors,
    ]

    # 1. Open the modal
    try:
        await view_btn.click()
    except Exception as e:
        logger.debug(f"Failed to click _view: {e}")
        return None

    # 2. Wait for modal to appear (up to 5s)
    modal_appeared = False
    try:
        await page.wait_for_selector(MODAL_OVERLAY, timeout=5_000)
        modal_appeared = True
        logger.debug("ReactModal opened")
    except PlaywrightTimeoutError:
        logger.debug("ReactModal did not appear — trying direct download")

    if not modal_appeared:
        # Modal did not open — return None, caller will try another path
        return None

    # 3. Find and click the download button inside the modal
    download_result = None
    for sel in MODAL_DL_SELECTORS:
        dl_btn = await page.query_selector(sel)
        if not dl_btn:
            continue
        try:

            async def _click_dl(b=dl_btn):
                await b.click()

            download_result = await wait_for_download(
                page, _click_dl, timeout=DOWNLOAD_TIMEOUT
            )
            if download_result:
                logger.debug(f"Скачивание из модала запущено через: {sel}")
                break
        except Exception:
            continue

    # 4. Close the modal regardless
    await _close_modal(page)

    return download_result


async def download_section(
    page: Page,
    section_name: str,
    nav_selectors: list[str],
    item_selectors: list[str],
    download_btn_selectors: list[str],
    target_dir: Path,
    period_days: int,
    results: dict,
    # EMIAS lk.emias.mos.ru specifics
    item_testid_prefix: str | None = None,
    period_filter_testid: str | None = None,
) -> int:
    """
    Universal function for downloading documents from an EMIAS section.

    Args:
        page:                   Playwright Page.
        section_name:           Section name for logging.
        nav_selectors:          List of selectors for navigating into the section.
                                Primary — data-testid, fallback — text/CSS.
        item_selectors:         CSS selectors for cards (fallback if
                                item_testid_prefix is not set).
        download_btn_selectors: Download button selectors (fallback
                                after attempting [data-testid$='_view']).
        target_dir:             Folder to save files.
        period_days:            Export period in days.
        results:                Dict for accumulating results.
        item_testid_prefix:     data-testid prefix for root card elements
                                (e.g. "item_inspection_").
        period_filter_testid:   Period filter button prefix
                                (e.g. "inspections_card").

    Returns:
        Number of successfully downloaded files.
    """
    logger.info(f"Navigating to section: {section_name}")
    logger.debug(f"Current URL: {page.url}")
    downloaded = 0

    # ── 1. Navigate to section ───────────────────────────────────────────────
    navigated = False
    for selector in nav_selectors:
        try:
            # Wait for element, scroll to it, click
            await page.wait_for_selector(selector, timeout=8_000)
            el = await page.query_selector(selector)
            if el:
                await el.scroll_into_view_if_needed()
                await el.click()
                navigated = True
                try:
                    await page.wait_for_load_state("networkidle", timeout=10_000)
                except PlaywrightTimeoutError:
                    await page.wait_for_load_state("domcontentloaded")
                logger.debug(f"Navigated to '{section_name}' via: {selector}")
                break
        except Exception:
            continue

    if not navigated:
        logger.warning(
            f"Failed to navigate to section '{section_name}'. URL: {page.url}"
        )
        return 0

    await asyncio.sleep(POLITE_DELAY)

    # ── 2. Period filter (lk.emias.mos.ru) ───────────────────────────────────
    if period_filter_testid:
        await _select_period_filter(page, period_filter_testid, period_days)

    # ── 3. Find cards ────────────────────────────────────────────────────────
    cutoff_date = datetime.today() - timedelta(days=period_days)
    logger.info(f"Exporting documents from {cutoff_date.strftime('%d.%m.%Y')} to today")

    items: list = []

    # Priority: data-testid prefix (EMIAS lk)
    if item_testid_prefix:
        items = await _find_items_by_testid_prefix(page, item_testid_prefix)

    # Fallback: CSS selectors
    if not items:
        for selector in item_selectors:
            items = await page.query_selector_all(selector)
            if items:
                break

    if not items:
        logger.info(f"No documents found in section '{section_name}'")
        return 0

    logger.info(f"Found records: {len(items)}")

    # ── 4. Iterate cards and download ────────────────────────────────────────
    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]{section_name}[/cyan]"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("", total=len(items))

        for item in items:
            progress.advance(task)

            # Guard: close modal if left open from previous iteration
            if await page.query_selector(".ReactModal__Overlay--after-open"):
                logger.debug("Modal is open before new card — closing")
                await _close_modal(page)

            doc_date = await extract_date_from_item(item)
            if doc_date and doc_date < cutoff_date:
                logger.debug(f"Skipping document from {doc_date} — outside period")
                continue

            description = await extract_text_from_item(item)

            # Button: first try data-testid$="_view" (EMIAS lk), then fallbacks
            btn_el = await item.query_selector("[data-testid$='_view']")
            if not btn_el:
                for btn_selector in download_btn_selectors:
                    btn_el = await item.query_selector(btn_selector)
                    if btn_el:
                        break

            if not btn_el:
                logger.debug(f"Download button not found: {description[:50]}")
                continue

            # Pre-check duplicate by expected filename (date + description).
            # Exact name is known only after download, so check by description name:
            # if such a file already exists — skip.
            expected_name = build_target_filename(
                re.sub(
                    r"[^\w.\-]", "_", (description.split("|")[0].strip() or "document")
                )
                + ".pdf",
                doc_date,
            )
            if is_duplicate(expected_name, target_dir):
                logger.debug(f"Skipping (already downloaded): {expected_name}")
                continue

            # The _view button opens ReactModal — download through it.
            # If modal did not appear — try direct download as fallback.
            download = await _download_via_modal(page, btn_el, download_btn_selectors)

            if download is None:
                # Modal did not open: try direct path
                async def _click_direct(el=btn_el):
                    await el.click()

                download = await wait_for_download(page, _click_direct, timeout=10_000)

            if download:
                # Final duplicate check by actual filename
                real_name = build_target_filename(download.suggested_filename, doc_date)
                if is_duplicate(real_name, target_dir):
                    logger.debug(f"Skipping duplicate (exact name): {real_name}")
                    continue

                with tempfile.TemporaryDirectory() as tmp_dir:
                    tmp_path = Path(tmp_dir) / download.suggested_filename
                    await download.save_as(str(tmp_path))
                    content = tmp_path.read_bytes()

                saved_path = save_file(
                    content=content,
                    original_name=download.suggested_filename,
                    doc_date=doc_date,
                    description=description,
                    target_dir=target_dir,
                )
                results.setdefault(section_name, []).append(saved_path)
                downloaded += 1
                logger.info(f"Сохранён: {saved_path.name}")
            else:
                logger.debug(f"Скачивание не запустилось: {description[:50]}")

            await asyncio.sleep(POLITE_DELAY)

    logger.info(f"Раздел '{section_name}': скачано {downloaded} файлов")
    return downloaded


async def extract_date_from_item(item) -> datetime | None:
    """
    Extracts the date from an EMIAS document card.

    Priority: data-testid*="_date" (EMIAS LK) → CSS classes → full text.

    Returns:
        datetime or None if the date is not found.
    """
    import re

    def _parse_date(text: str) -> datetime | None:
        # DD.MM.YYYY
        m = re.search(r"(\d{2})\.(\d{2})\.(\d{4})", text)
        if m:
            try:
                return datetime(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            except ValueError:
                pass
        # YYYY-MM-DD
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
        if m:
            try:
                return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            except ValueError:
                pass
        return None

    # 1. EMIAS lk.emias.mos.ru: data-testid ends with _date
    el = await item.query_selector("[data-testid$='_date']")
    if el:
        text = await el.inner_text()
        dt = _parse_date(text)
        if dt:
            return dt

    # 2. Standard CSS selectors (fallback)
    for selector in (
        ".date",
        "[class*='date']",
        "[class*='Date']",
        "time",
        "[datetime]",
    ):
        el = await item.query_selector(selector)
        if el:
            text = await el.inner_text()
            dt = _parse_date(text)
            if dt:
                return dt

    # 3. Last resort — search for a date in any text on the card
    full_text = await item.inner_text()
    return _parse_date(full_text)


async def extract_text_from_item(item) -> str:
    """
    Extracts the text description from an EMIAS document card.

    For lk.emias.mos.ru, uses data-testid attributes:
    _docName, _docSpecialization, _organization.

    Returns:
        A string with the description or an empty string.
    """
    # EMIAS lk.emias.mos.ru: structured sub-elements
    parts = []
    for suffix in ("_docName", "_docSpecialization", "_organization"):
        el = await item.query_selector(f"[data-testid$='{suffix}']")
        if el:
            text = (await el.inner_text()).strip()
            if text:
                parts.append(text)
    if parts:
        return " | ".join(parts)

    # Fallback CSS selectors
    for selector in (".title", ".name", "h3", "h4", "[class*='title']"):
        el = await item.query_selector(selector)
        if el:
            return (await el.inner_text()).strip()

    return (await item.inner_text())[:120].strip()


# ─── Main export sections ─────────────────────────────────────────────────


async def download_inspections(page: Page, period_days: int, results: dict) -> int:
    """
    Exports inspection and consultation records ("my inspections").

    lk.emias.mos.ru: open button — data-testid="inspections_card_open_button",
    cards — data-testid="item_inspection_<UUID>", period — "inspections_card".
    PDF contains: date, institution, doctor's specialization, full name, diagnosis.
    """
    return await download_section(
        page=page,
        section_name="Inspections and consultations",
        nav_selectors=[
            # lk.emias.mos.ru (data-testid, stable)
            "[data-testid='inspections_card_open_button']",
            # Fallback text selectors
            "text=мои приемы",
            "text=Мои приёмы",
            "text=Приёмы",
        ],
        item_selectors=[
            "[class*='visit']",
            "[class*='appointment']",
            "[class*='reception']",
        ],
        download_btn_selectors=[
            "text=Скачать",
            "text=PDF",
            "text=Распечатать",
            "button[title*='Скачать']",
            "a[download]",
            "a[href*='.pdf']",
        ],
        target_dir=EMIAS_INSPECTIONS_DIR,
        period_days=period_days,
        results=results,
        item_testid_prefix="item_inspection_",
        period_filter_testid="inspections_card",
    )


async def download_analyzes(page: Page, period_days: int, results: dict) -> int:
    """
    Exports laboratory analysis results ("my analyzes").

    lk.emias.mos.ru: button — data-testid="analyzes_card_open_button",
    cards presumably — "item_analyze_<UUID>".
    PDF contains: date, indicators, reference values.
    """
    return await download_section(
        page=page,
        section_name="Laboratory analyzes",
        nav_selectors=[
            # lk.emias.mos.ru
            "[data-testid='analyzes_card_open_button']",
            # Fallbacks
            "text=мои анализы",
            "text=Мои анализы",
            "text=Анализы",
        ],
        item_selectors=[
            "[class*='analysis']",
            "[class*='lab-result']",
            "[class*='laboratory']",
        ],
        download_btn_selectors=[
            "text=Скачать",
            "text=Скачать результат",
            "text=PDF",
            "button[title*='Скачать']",
            "a[download]",
            "a[href*='.pdf']",
        ],
        target_dir=EMIAS_ANALYZES_DIR,
        period_days=period_days,
        results=results,
        item_testid_prefix="item_analyze_",
        period_filter_testid="analyzes_card",
    )


async def download_medical_researches(
    page: Page, period_days: int, results: dict
) -> int:
    """
    Exports instrumental research results ("my researches").

    lk.emias.mos.ru: button — data-testid="research_card_open_button",
    cards presumably — "item_research_<UUID>".
    PDF contains: type (MRI/CT/Ultrasound/ECG), date, ERIS research number,
    description and conclusion.
    """
    return await download_section(
        page=page,
        section_name="Instrumental researches",
        nav_selectors=[
            # lk.emias.mos.ru
            "[data-testid='research_card_open_button']",
            # Fallbacks
            "text=мои исследования",
            "text=Мои исследования",
            "text=Исследования",
        ],
        item_selectors=[
            "[class*='research']",
            "[class*='diagnostic']",
            "[class*='instrumental']",
        ],
        download_btn_selectors=[
            "text=Скачать",
            "text=Открыть PDF",
            "text=PDF",
            "button[title*='Скачать']",
            "a[download]",
            "a[href*='.pdf']",
        ],
        target_dir=EMIAS_RESEARCHES_DIR,
        period_days=period_days,
        results=results,
        item_testid_prefix="item_research_",
        period_filter_testid="research_card",
    )


async def download_epicrisis(page: Page, period_days: int, results: dict) -> int:
    """
    Exports hospital discharge summaries ("my hospital discharges").

    lk.emias.mos.ru: button — data-testid="epicrisis_card_open_button",
    cards presumably — "item_epicrisis_<UUID>".
    PDF contains: hospitalization epicrisis, discharge diagnosis.
    Documents are saved in documents/inspections/ (medical records).
    """
    return await download_section(
        page=page,
        section_name="Hospital discharge summaries",
        nav_selectors=[
            # lk.emias.mos.ru
            "[data-testid='epicrisis_card_open_button']",
            # Fallbacks
            "text=мои выписки из стационара",
            "text=Выписки",
            "text=Эпикризы",
        ],
        item_selectors=[
            "[class*='epicrisis']",
            "[class*='discharge']",
            "[class*='hospital']",
        ],
        download_btn_selectors=[
            "text=Скачать",
            "text=PDF",
            "button[title*='Скачать']",
            "a[download]",
            "a[href*='.pdf']",
        ],
        target_dir=EMIAS_INSPECTIONS_DIR,
        period_days=period_days,
        results=results,
        item_testid_prefix="item_epicrisis_",
        period_filter_testid="epicrisis_card",
    )


# ─── Main function ──────────────────────────────────────────────────────────


async def run_emias_export(
    username: str,
    password: str,
    period_days: int = 180,
    headless: bool = False,
    sections: list[str] | None = None,
) -> dict:
    """
    Main function for exporting data from EMIAS.

    Args:
        username:    Login (phone or SNILS).
        password:    ESIA password.
        period_days: Download period in days.
        headless:    Run browser in background mode.
        sections:    List of sections to export (None = all).

    Returns:
        Dictionary {section: [list of file paths]}.
    """
    results: dict[str, list[Path]] = {}

    console.print(
        f"\n[bold cyan]═══ ЕМИАС: Экспорт данных за последние {period_days} дней ═══[/bold cyan]\n"
    )
    console.print(
        "[yellow]⚠  Все данные сохраняются локально на вашем компьютере.[/yellow]\n"
    )

    async with async_playwright() as playwright:
        # Launch Chromium
        browser: Browser = await playwright.chromium.launch(
            headless=headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )

        context: BrowserContext = await browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            accept_downloads=True,
        )

        page: Page = await context.new_page()
        page.set_default_timeout(DEFAULT_TIMEOUT)

        try:
            # Authentication
            logger.info("Начинаем авторизацию в ЕМИАС...")
            if not await login_via_esia(page, username, password):
                logger.error("Авторизация не удалась. Завершаем работу.")
                return results

            console.print("[green]✓ Авторизация выполнена успешно[/green]\n")

            # After redirecting back to lk.emias.mos.ru, wait for React to fully
            # mount — otherwise data-testid buttons won't be in the DOM yet.
            logger.info("Ожидаем готовности главной страницы ЕМИАС...")
            if not await _wait_for_main_page_ready(page, timeout=45_000):
                logger.error("Главная страница не готова. Завершаем работу.")
                return results
            console.print("[green]✓ Главная страница ЕМИАС загружена[/green]\n")

            # Determine sections for export
            all_sections = {
                "inspections": download_inspections,
                "analyzes": download_analyzes,
                "researches": download_medical_researches,
                "epicrisis": download_epicrisis,
            }
            active_sections = sections or list(all_sections.keys())

            # Run export by sections
            for section_key in active_sections:
                if section_key not in all_sections:
                    continue

                # Before each section, return to the main page
                # so that all navigation buttons (*_open_button) are in the DOM.
                logger.info(f"Переход на главную перед разделом '{section_key}'...")
                if not await _go_to_main_page(page):
                    logger.warning(
                        f"Не удалось вернуться на главную. "
                        f"Раздел '{section_key}' будет пропущен."
                    )
                    continue

                for attempt in range(MAX_RETRIES):
                    try:
                        await all_sections[section_key](page, period_days, results)
                        break
                    except Exception as e:
                        logger.warning(
                            f"Попытка {attempt + 1}/{MAX_RETRIES}: "
                            f"ошибка в разделе — {e}"
                        )
                        if attempt == MAX_RETRIES - 1:
                            logger.error(f"Раздел пропущен после {MAX_RETRIES} попыток")
                        await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"Критическая ошибка во время выгрузки: {e}")
        finally:
            await context.close()
            await browser.close()

    return results


def parse_args() -> argparse.Namespace:
    """Parses command line arguments."""
    parser = argparse.ArgumentParser(
        description="Export medical data from EMIAS to AMDA project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  python emias-export.py
  python emias-export.py --period 90 --headless
  python emias-export.py --section inspections analyzes
  python emias-export.py --username +79001234567
        """,
    )
    parser.add_argument(
        "--username",
        "-u",
        help="ESIA Login (phone or SNILS). Default — from .env",
    )
    parser.add_argument(
        "--period",
        "-p",
        type=int,
        default=int(os.getenv("IMPORT_PERIOD_DAYS", 180)),
        help="Download period in days (default: 180)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.getenv("HEADLESS", "false").lower() == "true",
        help="Run browser in background mode",
    )
    parser.add_argument(
        "--section",
        nargs="+",
        choices=["inspections", "analyzes", "researches", "epicrisis"],
        help="Export only specified sections (default: all)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Detailed logging output",
    )
    return parser.parse_args()


async def main() -> None:
    # Load variables from .env
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    args = parse_args()
    setup_logging(verbose=args.verbose)

    # Get credentials
    username = args.username or os.getenv("EMIAS_USERNAME", "")
    password = os.getenv("EMIAS_PASSWORD", "")

    if not username:
        username = input("Введите логин ЕСИА (телефон или СНИЛС): ").strip()
    if not password:
        import getpass

        password = getpass.getpass("Введите пароль ЕСИА: ")

    if not username or not password:
        logger.error("Логин и пароль обязательны")
        sys.exit(1)

    # Start export
    results = await run_emias_export(
        username=username,
        password=password,
        period_days=args.period,
        headless=args.headless,
        sections=args.section,
    )

    # Print final summary
    console.print()
    print_import_summary(results)

    total = sum(len(v) for v in results.values())
    if total > 0:
        console.print(f"\n[green]✓ Импортировано файлов: {total}[/green]")
        console.print(
            "\n[bold cyan]Следующий шаг:[/bold cyan] Запустите AMDA и выполните команду:\n"
            "[italic]«Проанализировать новые документы в папке documents/»[/italic]"
        )
    else:
        console.print("\n[yellow]Новых файлов не найдено.[/yellow]")


if __name__ == "__main__":
    asyncio.run(main())
