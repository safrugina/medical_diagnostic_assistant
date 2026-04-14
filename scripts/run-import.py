"""
run-import.py — Main launcher script for importing medical data into AMDA.

Provides an interactive menu to select the data source and import parameters.

Usage:
    python run-import.py                          # Interactive menu
    python run-import.py --source emias           # Quick launch EMIAS
    python run-import.py --source invitro         # Quick launch Invitro
    python run-import.py --source all --headless  # All sources in background
    python run-import.py --list                   # Show available sources
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, IntPrompt, Prompt
from rich.table import Table
from rich.text import Text

# Load .env before importing modules
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

sys.path.insert(0, str(Path(__file__).parent))
from utils import (
    INSPECTIONS_DIR,
    DOCS_DIR,
    RESEARCHES_DIR,
    ANALYZES_DIR,
    RAW_DIR,
    print_import_summary,
    setup_logging,
)

# Import main export functions (files renamed: dash → underscore)
from emias_export import run_emias_export
from clinic_export import CLINIC_PRESETS, run_clinic_export

# ─── Constants ───────────────────────────────────────────────────────────────

console = Console()

# All available sources: key → display name
ALL_SOURCES: dict[str, str] = {
    "emias": "ЕМИАС (Москва)",
    **{key: config.name for key, config in CLINIC_PRESETS.items()},
}

BANNER = """
╔══════════════════════════════════════════════════════════╗
║      AI Medical Diagnostic Assistant (AMDA)              ║
║           Импорт медицинских данных v1.2                 ║
╚══════════════════════════════════════════════════════════╝
"""


# ─── Menu display ─────────────────────────────────────────────────────────


def show_banner() -> None:
    """Displays the program header."""
    console.print(Panel(BANNER, style="bold cyan", border_style="cyan"))
    console.print(
        "[yellow]⚠  Все данные сохраняются локально. "
        "Не передавайте папки documents/ и patient-data/ третьим лицам.[/yellow]\n"
    )


def show_sources_table() -> None:
    """Prints the table of available data sources."""
    table = Table(
        title="Доступные источники данных",
        show_header=True,
        header_style="bold cyan",
        border_style="cyan",
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Источник", style="cyan")
    table.add_column("Описание", style="white")
    table.add_column(".env переменные", style="dim")

    source_info = {
        "emias": ("ЕМИАС (Москва)", "EMIAS_USERNAME, EMIAS_PASSWORD"),
        "invitro": ("Инвитро — Лаборатория", "INVITRO_USERNAME, INVITRO_PASSWORD"),
        "helix": ("Хеликс — Лаборатория", "HELIX_USERNAME, HELIX_PASSWORD"),
        "gemotest": ("Гемотест — Лаборатория", "GEMOTEST_USERNAME, GEMOTEST_PASSWORD"),
        "medsi": ("Медси — Клиника", "MEDSI_USERNAME, MEDSI_PASSWORD"),
        "sberhealth": ("СберЗдоровье", "SBERHEALTH_USERNAME, SBERHEALTH_PASSWORD"),
    }

    for idx, (key, (desc, env_vars)) in enumerate(source_info.items(), start=1):
        table.add_row(str(idx), key, desc, env_vars)

    table.add_row(
        str(len(source_info) + 1),
        "[bold]all[/bold]",
        "[bold]Все источники подряд[/bold]",
        "—",
    )

    console.print(table)


def show_current_documents() -> None:
    """Shows the current state of document folders."""
    table = Table(
        title="Текущее состояние папок documents/",
        show_header=True,
        header_style="bold green",
    )
    table.add_column("Папка", style="cyan")
    table.add_column("Файлов", justify="right", style="green")

    folders = {
        "inspections/": INSPECTIONS_DIR,
        "medical_tests/": ANALYZES_DIR,
        "medical_researches/": RESEARCHES_DIR,
        "raw/": RAW_DIR,
    }

    total = 0
    for name, path in folders.items():
        if path.exists():
            count = len(
                [f for f in path.iterdir() if f.is_file() and f.name != ".gitkeep"]
            )
        else:
            count = 0
        table.add_row(f"documents/{name}", str(count))
        total += count

    table.add_row("[bold]ИТОГО[/bold]", f"[bold]{total}[/bold]")
    console.print(table)
    console.print()


# ─── Credentials input ──────────────────────────────────────────────────────

def get_credentials(source: str) -> tuple[str, str]:
    """
    Retrieves credentials from .env or prompts the user.

    Args:
        source: Source identifier ('emias', 'invitro', etc.)

    Returns:
        Tuple (username, password).
    """
    if source == "emias":
        username_env = "EMIAS_USERNAME"
        password_env = "EMIAS_PASSWORD"
        source_label = "ЕСИА (Госуслуги)"
    elif source in CLINIC_PRESETS:
        config = CLINIC_PRESETS[source]
        username_env = config.username_env
        password_env = config.password_env
        source_label = config.name
    else:
        username_env = f"{source.upper()}_USERNAME"
        password_env = f"{source.upper()}_PASSWORD"
        source_label = source

    username = os.getenv(username_env, "")
    password = os.getenv(password_env, "")

    if not username:
        username = Prompt.ask(
            f"[cyan][{source_label}][/cyan] Логин (телефон/СНИЛС/e-mail)"
        )
    else:
        console.print(f"[dim]Логин для {source_label} загружен из .env[/dim]")

    if not password:
        password = getpass.getpass(f"[{source_label}] Пароль: ")
    else:
        console.print(f"[dim]Пароль для {source_label} загружен из .env[/dim]")

    return username.strip(), password


# ─── Import execution ───────────────────────────────────────────────────────────

async def run_single_source(
    source: str,
    period_days: int,
    headless: bool,
) -> dict:
    """
    Runs import from a single source.

    Args:
        source:      Source identifier.
        period_days: Period in days.
        headless:    Background mode.

    Returns:
        Dictionary of results.
    """
    username, password = get_credentials(source)

    if not username or not password:
        console.print(
            f"[red]✗ Учётные данные для {source} не указаны. Пропускаем.[/red]"
        )
        return {}

    if source == "emias":
        return await run_emias_export(
            username=username,
            password=password,
            period_days=period_days,
            headless=headless,
        )
    elif source in CLINIC_PRESETS:
        return await run_clinic_export(
            source=source,
            username=username,
            password=password,
            period_days=period_days,
            headless=headless,
        )
    else:
        console.print(f"[red]Неизвестный источник: {source}[/red]")
        return {}


async def run_all_sources(period_days: int, headless: bool) -> dict:
    """
    Sequentially runs import from all configured sources.

    Skips sources for which credentials are not found in .env.

    Args:
        period_days: Period in days.
        headless:    Background mode.

    Returns:
        Combined dictionary of results.
    """
    all_results: dict = {}
    configured_sources = []

    # Check which sources are configured in .env
    if os.getenv("EMIAS_USERNAME"):
        configured_sources.append("emias")
    for key, config in CLINIC_PRESETS.items():
        if os.getenv(config.username_env):
            configured_sources.append(key)

    if not configured_sources:
        console.print(
            "[yellow]Не найдено настроенных источников в .env.\n"
            "Заполните файл scripts/.env на основе scripts/.env.example[/yellow]"
        )
        return {}

    console.print(
        f"[cyan]Настроены источники: {', '.join(configured_sources)}[/cyan]\n"
    )

    for source in configured_sources:
        console.rule(f"[bold cyan]{ALL_SOURCES.get(source, source)}[/bold cyan]")
        results = await run_single_source(source, period_days, headless)
        all_results.update(results)
        console.print()

    return all_results


# ─── Interactive menu ───────────────────────────────────────────────────────

async def interactive_menu() -> None:
    """
    Launches an interactive menu to select the source and import parameters.
    """
    show_banner()
    show_current_documents()
    show_sources_table()

    console.print()

    # Source selection
    source_choice = Prompt.ask(
        "\n[bold]Выберите источник[/bold] (введите ключ, например [cyan]emias[/cyan] или [cyan]all[/cyan])",
        choices=list(ALL_SOURCES.keys()) + ["all"],
        default="emias",
    )

    # Period
    period_days = IntPrompt.ask(
        "Период выгрузки (дней)",
        default=int(os.getenv("IMPORT_PERIOD_DAYS", 180)),
    )

    # Browser mode
    headless_default = os.getenv("HEADLESS", "false").lower() == "true"
    headless = Confirm.ask(
        "Запустить браузер в фоновом режиме (headless)?",
        default=headless_default,
    )

    console.print()
    console.rule("[bold cyan]Запуск импорта[/bold cyan]")

    # Execute
    if source_choice == "all":
        results = await run_all_sources(period_days, headless)
    else:
        results = await run_single_source(source_choice, period_days, headless)

    # Final summary
    console.print()
    console.rule("[bold green]Результаты[/bold green]")
    print_import_summary(results)

    total = sum(len(v) for v in results.values())

    if total > 0:
        console.print(f"\n[bold green]✓ Импортировано файлов: {total}[/bold green]")
        show_next_steps()
    else:
        console.print("\n[yellow]Файлы не были импортированы.[/yellow]")
        console.print(
            "[dim]Проверьте логи в logs/import-log.txt для диагностики.[/dim]"
        )


def show_next_steps() -> None:
    """Displays instructions for the next steps after import."""
    steps = Panel(
        Text.from_markup(
            "[bold]Следующие шаги:[/bold]\n\n"
            "1. Запустите AMDA:\n"
            "   [cyan]claude[/cyan]\n\n"
            "2. Скажите AMDA:\n"
            "   [italic]«Проанализировать все новые документы в папке documents/»[/italic]\n\n"
            "3. AMDA выполнит OCR и анализ, затем обновит current-patient.md\n\n"
            "[dim]Документы сохранены в:[/dim]\n"
            f"[dim]  📁 {INSPECTIONS_DIR.relative_to(DOCS_DIR.parent)}[/dim]\n"
            f"[dim]  📁 {ANALYZES_DIR.relative_to(DOCS_DIR.parent)}[/dim]\n"
            f"[dim]  📁 {RESEARCHES_DIR.relative_to(DOCS_DIR.parent)}[/dim]",
        ),
        title="[bold cyan]Что дальше?[/bold cyan]",
        border_style="cyan",
        padding=(1, 2),
    )
    console.print(steps)


# ─── CLI ──────────────────────────────────────────────────────────────────────


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Главный скрипт импорта медицинских данных в AMDA",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run-import.py                        # Interactive menu
  python run-import.py --source emias         # EMIAS only
  python run-import.py --source all           # All configured sources
  python run-import.py --source invitro --period 90 --headless
  python run-import.py --list                 # Show sources
        """,
    )
    parser.add_argument(
        "--source",
        "-s",
        choices=list(ALL_SOURCES.keys()) + ["all"],
        help="Источник данных (по умолчанию: интерактивное меню)",
    )
    parser.add_argument(
        "--period",
        "-p",
        type=int,
        default=int(os.getenv("IMPORT_PERIOD_DAYS", 180)),
        help="Период выгрузки в днях (по умолчанию: 180)",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=os.getenv("HEADLESS", "false").lower() == "true",
        help="Браузер в фоновом режиме",
    )
    parser.add_argument(
        "--list",
        "-l",
        action="store_true",
        help="Показать доступные источники и выйти",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Подробный вывод логов",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    setup_logging(verbose=args.verbose)

    if args.list:
        show_banner()
        show_sources_table()
        return

    if args.source:
        # Mode without interactive menu
        show_banner()
        if args.source == "all":
            results = await run_all_sources(args.period, args.headless)
        else:
            results = await run_single_source(args.source, args.period, args.headless)

        console.print()
        print_import_summary(results)
        total = sum(len(v) for v in results.values())
        if total > 0:
            console.print(f"\n[green]✓ Импортировано файлов: {total}[/green]")
            show_next_steps()
    else:
        # Interactive menu
        await interactive_menu()


if __name__ == "__main__":
    asyncio.run(main())
