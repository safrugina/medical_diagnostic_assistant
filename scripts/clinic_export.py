"""
clinic-export.py — Universal script for exporting data from personal accounts
                   of private clinics and laboratories.

Supported sources (presets):
  - invitro   → invitro.ru/lk/
  - helix     → helix.ru/lk
  - gemotest  → gemotest.ru
  - medsi     → medsi.ru/personal/
  - sberhealth→ sberzdorovye.ru
  - generic   → any website (manual configuration via arguments)

Usage:
    python clinic-export.py --source invitro
    python clinic-export.py --source helix --period 90 --headless
    python clinic-export.py --source generic --url https://clinic.example.ru/lk

Configuration via .env:
    INVITRO_USERNAME=+7XXXXXXXXXX
    INVITRO_PASSWORD=your_password
    (similarly for other clinics)
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Optional

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
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    INSPECTIONS_DIR,
    RESEARCHES_DIR,
    ANALYZES_DIR,
    RAW_DIR,
    print_import_summary,
    request_2fa_code,
    safe_click,
    safe_fill,
    save_file,
    setup_logging,
    wait_for_download,
)

# Clinic configurations


@dataclass
class ClinicConfig:
    """
    Configuration for a clinic/laboratory personal account.

    Fields:
        name:               Display name.
        base_url:           Base URL of the personal account.
        login_url:          Login page URL (if different from base_url).
        username_env:       Environment variable name for the login.
        password_env:       Environment variable name for the password.
        username_selectors: CSS selectors for the login field.
        password_selectors: CSS selectors for the password field.
        submit_selectors:   CSS selectors for the login button.
        results_nav:        Selectors for navigating to results.
        result_items:       Selectors for result cards.
        download_buttons:   Selectors for download buttons.
        otp_selectors:      Selectors for the 2FA code field.
        default_category:   Default category for files from this clinic.
    """

    name: str
    base_url: str
    login_url: str
    username_env: str
    password_env: str
    username_selectors: list[str] = field(default_factory=list)
    password_selectors: list[str] = field(default_factory=list)
    submit_selectors: list[str] = field(default_factory=list)
    results_nav: list[str] = field(default_factory=list)
    result_items: list[str] = field(default_factory=list)
    download_buttons: list[str] = field(default_factory=list)
    otp_selectors: list[str] = field(default_factory=list)
    default_category: Path = ANALYZES_DIR


# Presets for supported clinics and laboratories
CLINIC_PRESETS: dict[str, ClinicConfig] = {
    "invitro": ClinicConfig(
        name="Инвитро",
        base_url="https://www.invitro.ru",
        login_url="https://www.invitro.ru/lk/",
        username_env="INVITRO_USERNAME",
        password_env="INVITRO_PASSWORD",
        username_selectors=[
            "input[name='phone']",
            "input[type='tel']",
            "input[placeholder*='телефон']",
            "#login-phone",
        ],
        password_selectors=[
            "input[name='password']",
            "input[type='password']",
            "#login-password",
        ],
        submit_selectors=[
            "button[type='submit']",
            "text=Войти",
            ".login-btn",
        ],
        results_nav=[
            "text=Мои анализы",
            "text=Результаты",
            "a[href*='/lk/analysis']",
            "a[href*='/lk/results']",
            "[class*='results-nav']",
        ],
        result_items=[
            ".order-card",
            ".analysis-item",
            "[class*='order-item']",
            "[class*='result-card']",
            "li[class*='analysis']",
        ],
        download_buttons=[
            "button[title*='PDF']",
            "text=Скачать PDF",
            "text=PDF",
            "a[href*='.pdf']",
            "[class*='download-pdf']",
        ],
        otp_selectors=[
            "input[name='sms_code']",
            "input[placeholder*='код']",
            "input[id*='sms']",
        ],
        default_category=ANALYZES_DIR,
    ),
    "helix": ClinicConfig(
        name="Хеликс",
        base_url="https://helix.ru",
        login_url="https://helix.ru/lk",
        username_env="HELIX_USERNAME",
        password_env="HELIX_PASSWORD",
        username_selectors=[
            "input[name='phone']",
            "input[type='tel']",
            "input[placeholder*='Телефон']",
            "#auth-phone",
        ],
        password_selectors=[
            "input[name='password']",
            "input[type='password']",
        ],
        submit_selectors=[
            "button[type='submit']",
            "text=Войти",
            ".auth-submit",
        ],
        results_nav=[
            "text=Результаты",
            "text=Мои заказы",
            "a[href*='/lk/orders']",
            "a[href*='/lk/results']",
            "[class*='my-results']",
        ],
        result_items=[
            ".order-card",
            "[class*='order-row']",
            "[class*='result-item']",
            "table tbody tr",
        ],
        download_buttons=[
            "text=Скачать",
            "text=PDF",
            "button[class*='pdf']",
            "a[download]",
            "[class*='download']",
        ],
        otp_selectors=[
            "input[name='code']",
            "input[placeholder*='код']",
            "input[id*='code']",
        ],
        default_category=ANALYZES_DIR,
    ),
    "gemotest": ClinicConfig(
        name="Гемотест",
        base_url="https://gemotest.ru",
        login_url="https://gemotest.ru/lk/",
        username_env="GEMOTEST_USERNAME",
        password_env="GEMOTEST_PASSWORD",
        username_selectors=[
            "input[name='phone']",
            "input[type='tel']",
            "input[placeholder*='телефон']",
        ],
        password_selectors=[
            "input[name='password']",
            "input[type='password']",
        ],
        submit_selectors=[
            "button[type='submit']",
            "text=Войти",
            ".btn-login",
        ],
        results_nav=[
            "text=Мои анализы",
            "text=Результаты анализов",
            "a[href*='/lk/results']",
            "a[href*='/lk/orders']",
        ],
        result_items=[
            ".result-card",
            "[class*='result-item']",
            "[class*='order-card']",
        ],
        download_buttons=[
            "text=Скачать",
            "text=PDF",
            "a[href*='.pdf']",
            "[class*='pdf-btn']",
        ],
        otp_selectors=[
            "input[name='code']",
            "input[placeholder*='код из SMS']",
        ],
        default_category=ANALYZES_DIR,
    ),
    "medsi": ClinicConfig(
        name="Медси",
        base_url="https://medsi.ru",
        login_url="https://medsi.ru/personal/",
        username_env="MEDSI_USERNAME",
        password_env="MEDSI_PASSWORD",
        username_selectors=[
            "input[name='login']",
            "input[type='email']",
            "input[type='tel']",
            "input[placeholder*='логин']",
        ],
        password_selectors=[
            "input[name='password']",
            "input[type='password']",
        ],
        submit_selectors=[
            "button[type='submit']",
            "text=Войти",
            ".sign-in-btn",
        ],
        results_nav=[
            "text=Мои результаты",
            "text=Анализы",
            "text=Исследования",
            "a[href*='/personal/results']",
            "a[href*='/personal/orders']",
        ],
        result_items=[
            ".visit-result",
            "[class*='analysis-result']",
            "[class*='result-row']",
        ],
        download_buttons=[
            "text=Скачать",
            "text=PDF",
            "button[class*='download']",
            "a[download]",
        ],
        otp_selectors=[
            "input[placeholder*='код']",
            "input[name='otp']",
        ],
        default_category=ANALYZES_DIR,
    ),
    "sberhealth": ClinicConfig(
        name="СберЗдоровье",
        base_url="https://sberzdorovye.ru",
        login_url="https://sberzdorovye.ru/lk/",
        username_env="SBERHEALTH_USERNAME",
        password_env="SBERHEALTH_PASSWORD",
        username_selectors=[
            "input[name='phone']",
            "input[type='tel']",
            "input[placeholder*='телефон']",
        ],
        password_selectors=[
            "input[type='password']",
        ],
        submit_selectors=[
            "button[type='submit']",
            "text=Войти",
        ],
        results_nav=[
            "text=Мои анализы",
            "text=Результаты",
            "a[href*='/lk/results']",
        ],
        result_items=[
            "[class*='result-card']",
            "[class*='order-item']",
        ],
        download_buttons=[
            "text=Скачать PDF",
            "text=PDF",
            "a[download]",
        ],
        otp_selectors=[
            "input[name='code']",
            "input[placeholder*='код']",
        ],
        default_category=ANALYZES_DIR,
    ),
}

# ─── Constants ───────────────────────────────────────────────────────────────

MAX_RETRIES = 3
DEFAULT_TIMEOUT = 15_000
DOWNLOAD_TIMEOUT = 60_000
LOGIN_TIMEOUT = 30_000
POLITE_DELAY = 1.5

console = Console()


# ─── Authentication ─────────────────────────────────────────────────────────────


async def login(page: Page, config: ClinicConfig, username: str, password: str) -> bool:
    """
    Logs into the clinic's personal account.

    Algorithm:
    1. Open the login page.
    2. Fill in login and password fields (or just phone + OTP).
    3. If a 2FA code is required, prompt the user.
    4. Verify success.

    Args:
        page:     Playwright Page.
        config:   Clinic configuration.
        username: Login (phone or email).
        password: Password.

    Returns:
        True upon successful authentication.
    """
    logger.info(f"[{config.name}] Открываем страницу входа: {config.login_url}")
    try:
        await page.goto(
            config.login_url, timeout=LOGIN_TIMEOUT, wait_until="domcontentloaded"
        )
    except Exception as e:
        logger.error(f"[{config.name}] Не удалось открыть страницу: {e}")
        return False

    await asyncio.sleep(1)

    # Enter login
    for selector in config.username_selectors:
        if await safe_fill(page, selector, username, timeout=5_000):
            logger.info(f"[{config.name}] Логин введён")
            break

    await asyncio.sleep(0.5)

    # Some sites ask for phone first, then password
    # Try clicking "Continue" or "Next" if the password is not yet visible
    continue_selectors = [
        "text=Продолжить",
        "text=Далее",
        "text=Next",
        "button[type='submit']",
    ]
    password_visible = False
    for selector in config.password_selectors:
        try:
            el = await page.query_selector(selector)
            if el and await el.is_visible():
                password_visible = True
                break
        except Exception:
            pass

    if not password_visible:
        for sel in continue_selectors:
            if await safe_click(page, sel, timeout=3_000):
                await asyncio.sleep(1.5)
                break

    # Enter password (if field is visible)
    for selector in config.password_selectors:
        if await safe_fill(page, selector, password, timeout=5_000):
            logger.info(f"[{config.name}] Пароль введён")
            break

    await asyncio.sleep(0.5)

    # Click "Login"
    for selector in config.submit_selectors:
        if await safe_click(page, selector, timeout=5_000):
            logger.info(f"[{config.name}] Нажата кнопка входа")
            break

    await asyncio.sleep(2)

    # Handle 2FA
    for selector in config.otp_selectors:
        try:
            await page.wait_for_selector(selector, timeout=5_000)
            logger.info(f"[{config.name}] Обнаружена 2FA")
            console.print(
                f"\n[bold yellow]⚠  [{config.name}] Требуется код из SMS[/bold yellow]"
            )
            code = await request_2fa_code(f"[{config.name}] Введите код из SMS")
            await safe_fill(page, selector, code)
            for sel in config.submit_selectors:
                if await safe_click(page, sel, timeout=5_000):
                    break
            await asyncio.sleep(2)
            break
        except PlaywrightTimeoutError:
            continue

    # Verify success
    current_url = page.url
    if "login" in current_url.lower() or "auth" in current_url.lower():
        # Check for error message
        error_selectors = [".error", ".alert-danger", "[class*='error-msg']"]
        for sel in error_selectors:
            el = await page.query_selector(sel)
            if el:
                error_text = await el.inner_text()
                logger.error(f"[{config.name}] Ошибка входа: {error_text}")
                return False
        logger.warning(f"[{config.name}] Возможно вход не выполнен. URL: {current_url}")
        return False

    logger.info(f"[{config.name}] Авторизация успешна")
    return True


# ─── Download results ─────────────────────────────────────────────────────


async def download_results(
    page: Page,
    config: ClinicConfig,
    period_days: int,
    results: dict,
) -> int:
    """
    Downloads results from the clinic's personal account.

    Args:
        page:        Playwright Page.
        config:      Clinic configuration.
        period_days: Download period in days.
        results:     Dictionary to accumulate results.

    Returns:
        Number of downloaded files.
    """
    downloaded = 0
    cutoff_date = datetime.today() - timedelta(days=period_days)
    logger.info(
        f"[{config.name}] Выгружаем данные с {cutoff_date.strftime('%d.%m.%Y')}"
    )

    # Navigate to results
    navigated = False
    for selector in config.results_nav:
        if await safe_click(page, selector, timeout=8_000):
            await page.wait_for_load_state("networkidle", timeout=10_000)
            navigated = True
            logger.info(f"[{config.name}] Перешли в раздел результатов")
            break

    if not navigated:
        logger.warning(f"[{config.name}] Не удалось перейти к результатам")
        return 0

    await asyncio.sleep(POLITE_DELAY)

    # Get list of cards
    items = []
    for selector in config.result_items:
        items = await page.query_selector_all(selector)
        if items:
            logger.info(f"[{config.name}] Найдено записей: {len(items)}")
            break

    if not items:
        logger.info(f"[{config.name}] Записей не найдено")
        return 0

    # Scroll list to load all records (infinite scroll)
    await scroll_to_load_all(page)

    # Update list after scrolling
    for selector in config.result_items:
        items = await page.query_selector_all(selector)
        if items:
            logger.info(f"[{config.name}] Найдено записей: {len(items)}")
            break

    if not items:
        logger.info(f"[{config.name}] Записей не найдено")
        return 0

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]{config.name}[/cyan]"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("", total=len(items))

        for item in items:
            progress.advance(task)

            # Determine document date
            doc_date = await extract_date(item)
            if doc_date and doc_date < cutoff_date:
                logger.debug(f"[{config.name}] Пропускаем документ от {doc_date}")
                continue

            # Get description
            description = await extract_description(item)

            # Download
            for btn_selector in config.download_buttons:
                btn = await item.query_selector(btn_selector)
                if not btn:
                    continue

                download = await wait_for_download(
                    page,
                    lambda b=btn: b.click(),
                    timeout=DOWNLOAD_TIMEOUT,
                )

                if download:
                    with tempfile.TemporaryDirectory() as tmp_dir:
                        tmp_path = Path(tmp_dir) / download.suggested_filename
                        await download.save_as(str(tmp_path))
                        content = tmp_path.read_bytes()

                    saved = save_file(
                        content=content,
                        original_name=download.suggested_filename,
                        doc_date=doc_date,
                        description=f"{config.name} {description}",
                        target_dir=config.default_category,
                    )
                    results.setdefault(config.name, []).append(saved)
                    downloaded += 1
                    break

            await asyncio.sleep(POLITE_DELAY)

    logger.info(f"[{config.name}] Скачано файлов: {downloaded}")
    return downloaded


async def scroll_to_load_all(page: Page, max_scrolls: int = 20) -> None:
    """
    Scrolls the page down to load all elements (infinite scroll).

    Args:
        page:        Playwright Page.
        max_scrolls: Maximum number of scrolls.
    """
    prev_height = 0
    for _ in range(max_scrolls):
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1.5)
        curr_height = await page.evaluate("document.body.scrollHeight")
        if curr_height == prev_height:
            break
        prev_height = curr_height


async def extract_date(item) -> datetime | None:
    """Extracts date from the result card."""
    import re

    date_selectors = [
        ".date",
        "[class*='date']",
        "[class*='Date']",
        "time",
        "[datetime]",
        ".order-date",
        "[class*='order-date']",
    ]

    for selector in date_selectors:
        el = await item.query_selector(selector)
        if not el:
            continue
        text = await el.inner_text()

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


async def extract_description(item) -> str:
    """Extracts text description from the card."""
    for selector in [".title", ".name", ".order-name", "h3", "h4", "[class*='title']"]:
        el = await item.query_selector(selector)
        if el:
            return (await el.inner_text()).strip()
    return (await item.inner_text())[:100].strip()


# ─── Main function ──────────────────────────────────────────────────────────


async def run_clinic_export(
    source: str,
    username: str,
    password: str,
    period_days: int = 180,
    headless: bool = False,
    custom_url: Optional[str] = None,
) -> dict:
    """
    Main function for exporting data from a clinic.

    Args:
        source:      Clinic identifier (key from CLINIC_PRESETS) or 'generic'.
        username:    Login.
        password:    Password.
        period_days: Download period.
        headless:    Browser background mode.
        custom_url:  URL for 'generic' mode.

    Returns:
        Dictionary {clinic: [list of Path to files]}.
    """
    results: dict[str, list[Path]] = {}

    if source not in CLINIC_PRESETS:
        logger.error(
            f"Неизвестный источник: '{source}'. "
            f"Доступные: {', '.join(CLINIC_PRESETS.keys())}"
        )
        return results

    config = CLINIC_PRESETS[source]

    if custom_url:
        config.login_url = custom_url
        config.base_url = custom_url

    console.print(
        f"\n[bold cyan]═══ {config.name}: Экспорт данных за {period_days} дней ═══[/bold cyan]\n"
    )
    console.print(
        "[yellow]⚠  Данные сохраняются локально на вашем компьютере.[/yellow]\n"
    )

    async with async_playwright() as playwright:
        browser: Browser = await playwright.chromium.launch(
            headless=headless,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
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
            if not await login(page, config, username, password):
                logger.error(f"[{config.name}] Авторизация не удалась")
                return results

            console.print(f"[green]✓ [{config.name}] Авторизация успешна[/green]\n")

            for attempt in range(MAX_RETRIES):
                try:
                    await download_results(page, config, period_days, results)
                    break
                except Exception as e:
                    logger.warning(
                        f"[{config.name}] Попытка {attempt + 1}/{MAX_RETRIES}: {e}"
                    )
                    if attempt == MAX_RETRIES - 1:
                        logger.error(
                            f"[{config.name}] Выгрузка не удалась после {MAX_RETRIES} попыток"
                        )
                    await asyncio.sleep(3)

        except Exception as e:
            logger.error(f"[{config.name}] Критическая ошибка: {e}")
        finally:
            await context.close()
            await browser.close()

    return results


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export data from clinic/laboratory personal account to AMDA project",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available sources: {", ".join(CLINIC_PRESETS.keys())}

Examples:
  python clinic-export.py --source invitro
  python clinic-export.py --source helix --period 90 --headless
  python clinic-export.py --source medsi --username +79001234567
        """,
    )
    parser.add_argument(
        "--source",
        "-s",
        required=True,
        choices=list(CLINIC_PRESETS.keys()),
        help="Data source (clinic/laboratory)",
    )
    parser.add_argument(
        "--username",
        "-u",
        help="Login (phone or e-mail). Default — from .env",
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
        "--url",
        help="Custom URL for generic mode",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Detailed logging output",
    )
    return parser.parse_args()


async def main() -> None:
    env_path = Path(__file__).parent / ".env"
    load_dotenv(env_path)

    args = parse_args()
    setup_logging(verbose=args.verbose)

    config = CLINIC_PRESETS[args.source]

    # Get credentials
    username = args.username or os.getenv(config.username_env, "")
    password = os.getenv(config.password_env, "")

    if not username:
        username = input(f"[{config.name}] Введите логин (телефон/e-mail): ").strip()
    if not password:
        import getpass

        password = getpass.getpass(f"[{config.name}] Введите пароль: ")

    if not username or not password:
        logger.error("Логин и пароль обязательны")
        sys.exit(1)

    results = await run_clinic_export(
        source=args.source,
        username=username,
        password=password,
        period_days=args.period,
        headless=args.headless,
        custom_url=args.url,
    )

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
