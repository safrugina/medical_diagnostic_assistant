"""
utils.py — Common utilities for AMDA data import scripts.

Contains:
- Logging setup
- File categorization into folders
- Adding date prefix to file names
- Helper functions for Playwright
"""

from __future__ import annotations

import asyncio
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger

# ─── Project paths ───────────────────────────────────────────────────────────

# Project root — two levels above scripts/
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

DOCS_DIR = PROJECT_ROOT / "documents"
INSPECTIONS_DIR = DOCS_DIR / "inspections"
ANALYZES_DIR = DOCS_DIR / "analyzes"
RESEARCHES_DIR = DOCS_DIR / "researches"
RAW_DIR = DOCS_DIR / "raw"
LOGS_DIR = PROJECT_ROOT / "logs"
LOG_FILE = LOGS_DIR / "import-log.txt"

# Source-specific subdirectories
EMIAS_INSPECTIONS_DIR = INSPECTIONS_DIR / "emias"
EMIAS_ANALYZES_DIR = ANALYZES_DIR / "emias"
EMIAS_RESEARCHES_DIR = RESEARCHES_DIR / "emias"

# ─── Keywords for categorization ─────────────────────────────────────────────

# Keywords in file names/titles used to determine the category
INSPECTIONS_KEYWORDS = [
    "прием", "приём", "консультация", "выписка", "эпикриз",
    "протокол", "справка", "направление", "назначение",
    "appointment", "consultation", "discharge", "referral",
    "visit", "визит", "осмотр",
]

ANALYZES_KEYWORDS = [
    "анализ", "лаборатор", "кровь", "моча", "биохим",
    "гемограмма", "коагулограмма", "гормон", "иммунология",
    "серология", "бактериология", "посев", "микробиология",
    "invitro", "helix", "гемотест", "kdl", "lab",
    "test", "result", "анализы",
]

RESEARCHES_KEYWORDS = [
    "узи", "кт", "мрт", "рентген", "флюорография", "экг", "эхо",
    "эндоскоп", "гастроскоп", "колоноскоп", "бронхоскоп",
    "спирометр", "маммограф", "денситометр",
    "mri", "ct", "xray", "ultrasound", "ecg", "echo",
    "исследование", "research", "study",
]


# ─── Logging setup ───────────────────────────────────────────────────────────

def setup_logging(verbose: bool = False) -> None:
    """
    Configures logging to console and to logs/import-log.txt.

    Args:
        verbose: if True — output DEBUG messages.
    """
    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # Remove the default loguru handler
    logger.remove()

    log_level = "DEBUG" if verbose else "INFO"

    # Console output with colors
    logger.add(
        sys.stderr,
        level=log_level,
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{message}</cyan>"
        ),
    )

    # File output without colors
    logger.add(
        str(LOG_FILE),
        level="DEBUG",
        rotation="10 MB",
        retention="30 days",
        encoding="utf-8",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )

    logger.info(f"Logging configured. Log file: {LOG_FILE}")


# ─── File categorization ──────────────────────────────────────────────────────

def categorize_file(filename: str, description: str = "") -> Path:
    """
    Determines the target folder for a file based on its name and description.

    Args:
        filename:    File name (e.g. "krov_obsh.pdf").
        description: Additional description from the source interface.

    Returns:
        Path to the target folder (documents/inspections, analyzes, etc.).
    """
    text = (filename + " " + description).lower()

    # Count matches for each category
    inspections_score = sum(kw in text for kw in INSPECTIONS_KEYWORDS)
    analyzes_score = sum(kw in text for kw in ANALYZES_KEYWORDS)
    researches_score = sum(kw in text for kw in RESEARCHES_KEYWORDS)

    max_score = max(inspections_score, analyzes_score, researches_score)

    if max_score == 0:
        logger.debug(f"Category not determined for '{filename}' → raw/")
        return RAW_DIR
    elif analyzes_score == max_score:
        logger.debug(f"Category: analyzes ← '{filename}'")
        return ANALYZES_DIR
    elif researches_score == max_score:
        logger.debug(f"Category: researches ← '{filename}'")
        return RESEARCHES_DIR
    else:
        logger.debug(f"Category: inspections ← '{filename}'")
        return INSPECTIONS_DIR


def build_target_filename(original_name: str, doc_date: Optional[datetime] = None) -> str:
    """
    Builds a file name with a date prefix.

    Format: YYYY-MM-DD_original-name.ext
    If the name already starts with a date — prefix is not added again.

    Args:
        original_name: Original file name.
        doc_date:      Document date. If None — today's date is used.

    Returns:
        Final file name.
    """
    # Check if the name already starts with a date (YYYY-MM-DD)
    date_prefix_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}[_\-]")
    if date_prefix_pattern.match(original_name):
        return original_name

    date_str = (doc_date or datetime.today()).strftime("%Y-%m-%d")

    # Sanitize the name from problematic characters
    safe_name = re.sub(r'[^\w.\-]', '_', original_name)
    safe_name = re.sub(r'_+', '_', safe_name)

    return f"{date_str}_{safe_name}"


def save_file(
    content: bytes,
    original_name: str,
    doc_date: Optional[datetime] = None,
    description: str = "",
    target_dir: Optional[Path] = None,
) -> Path:
    """
    Saves a downloaded file to the appropriate folder with the correct name.

    Args:
        content:      File content as bytes.
        original_name: Original file name.
        doc_date:     Document date.
        description:  Document description (for categorization).
        target_dir:   Explicit target folder (if None — determined automatically).

    Returns:
        Path to the saved file.
    """
    if target_dir is None:
        target_dir = categorize_file(original_name, description)

    target_dir.mkdir(parents=True, exist_ok=True)
    filename = build_target_filename(original_name, doc_date)
    file_path = target_dir / filename

    # If the file already exists — add a numeric suffix
    counter = 1
    while file_path.exists():
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        file_path = target_dir / f"{stem}_{counter}{suffix}"
        counter += 1

    file_path.write_bytes(content)
    logger.info(f"File saved: {file_path.relative_to(PROJECT_ROOT)}")
    return file_path


def is_duplicate(filename: str, target_dir: Path) -> bool:
    """
    Checks whether a file with this name already exists in the target folder.

    Comparison is done by file name ignoring numeric suffixes (_1, _2, etc.),
    which are added on collisions in save_file. This prevents re-downloading
    the same document on subsequent script runs.

    Args:
        filename:   Final file name (already with date prefix), without path.
        target_dir: Target folder.

    Returns:
        True if the file (or a version with a suffix) already exists.
    """
    if not target_dir.exists():
        return False

    target_stem = Path(filename).stem
    target_suffix = Path(filename).suffix

    for existing in target_dir.iterdir():
        if not existing.is_file():
            continue
        if existing.suffix.lower() != target_suffix.lower():
            continue
        # Exact match
        if existing.name == filename:
            return True
        # Match with counter: stem_1.ext, stem_2.ext ...
        existing_stem = existing.stem
        if re.match(rf"^{re.escape(target_stem)}_\d+$", existing_stem):
            return True

    return False


# ─── Playwright helper functions ──────────────────────────────────────────────

async def safe_click(page, selector: str, timeout: int = 10_000) -> bool:
    """
    Safe click with element visibility wait.

    Args:
        page:     Playwright Page.
        selector: CSS/XPath selector.
        timeout:  Timeout in milliseconds.

    Returns:
        True if click succeeded, False if element not found.
    """
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.click(selector)
        return True
    except Exception as e:
        logger.debug(f"safe_click: failed to click '{selector}': {e}")
        return False


async def safe_fill(page, selector: str, value: str, timeout: int = 10_000) -> bool:
    """
    Safe input field fill.

    Args:
        page:     Playwright Page.
        selector: CSS selector of the field.
        value:    Value to enter.
        timeout:  Timeout in milliseconds.

    Returns:
        True if fill succeeded.
    """
    try:
        await page.wait_for_selector(selector, timeout=timeout)
        await page.fill(selector, value)
        return True
    except Exception as e:
        logger.debug(f"safe_fill: failed to fill '{selector}': {e}")
        return False


async def wait_for_download(page, trigger_action, timeout: int = 60_000):
    """
    Waits for a file download after executing an action.

    Args:
        page:           Playwright Page.
        trigger_action: Async function that initiates the download.
        timeout:        Wait timeout in milliseconds.

    Returns:
        Playwright Download object or None on error.
    """
    try:
        async with page.expect_download(timeout=timeout) as download_info:
            await trigger_action()
        return await download_info.value
    except Exception as e:
        logger.warning(f"Download wait error: {e}")
        return None


async def request_2fa_code(prompt: str = "Enter SMS/Push code") -> str:
    """
    Prompts the user for a two-factor authentication code.

    Args:
        prompt: Prompt text.

    Returns:
        Entered code.
    """
    # Run input() in a thread pool for asyncio compatibility
    loop = asyncio.get_event_loop()
    code = await loop.run_in_executor(None, lambda: input(f"\n{prompt}: "))
    return code.strip()


# ─── Import summary ───────────────────────────────────────────────────────────

def print_import_summary(results: dict[str, list[Path]]) -> None:
    """
    Prints a summary of imported files.

    Args:
        results: Dictionary {category: [list of Path]}.
    """
    from rich.console import Console
    from rich.table import Table

    console = Console()
    table = Table(title="Import Results", show_header=True, header_style="bold cyan")
    table.add_column("Category", style="cyan")
    table.add_column("Files", justify="right", style="green")

    total = 0
    for category, files in results.items():
        table.add_row(category, str(len(files)))
        total += len(files)

    table.add_row("[bold]TOTAL[/bold]", f"[bold]{total}[/bold]")
    console.print(table)
