"""AMDA — AI Medical Diagnostic Assistant
Streamlit chat interface for patient anamnesis collection and document analysis.
"""

import os
import sys

# Force UTF-8 encoding globally
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from datetime import datetime
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

# ─── Configurable diagnosis threshold ────────────────────────────────────────
try:
    DIAGNOSIS_THRESHOLD = int(os.getenv("DIAGNOSIS_THRESHOLD", "90"))
except ValueError:
    DIAGNOSIS_THRESHOLD = 90

from ui.chat_handler import (
    generate_response,
    generate_resume_continuation,
    get_initial_greeting,
    get_active_provider,
    extract_structured_anamnesis,
    analyze_document,
    generate_combined_analysis,
    generate_differential_diagnosis,
    recalculate_differential_diagnosis,
    generate_investigation_plan,
    generate_final_diagnosis,
    extract_max_probability,
)
from ui.anamnesis_manager import AnamnesisManager, AnamnesisStage
from ui.patient_data_handler import PatientDataHandler, is_error_analysis


# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="AMDA — AI Medical Diagnostic Assistant",
    page_icon="🏥",
    layout="centered",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
html, body, [class*="css"] { font-family: 'Inter', 'Segoe UI', sans-serif; }
.disclaimer-banner {
    background-color: #FFF3CD; border: 1px solid #FFCC02; border-radius: 8px;
    padding: 12px 16px; margin-bottom: 16px; font-size: 0.85rem; color: #5A4A00;
}
.stage-label {
    font-size: 0.8rem; color: #6B7280; margin-bottom: 4px;
    font-weight: 500; letter-spacing: 0.03em; text-transform: uppercase;
}
h1 { color: #1E3A5F; }
.stChatMessage { animation: fadeIn 0.3s ease-in; }
@keyframes fadeIn { from { opacity:0; transform:translateY(6px);} to { opacity:1; transform:translateY(0);} }
</style>
""", unsafe_allow_html=True)


# ─── Session state ───────────────────────────────────────────────────────────
def init_session():
    if "messages" not in st.session_state:
        st.session_state.messages = []
    if "anamnesis_manager" not in st.session_state:
        st.session_state.anamnesis_manager = AnamnesisManager()
    if "patient_handler" not in st.session_state:
        st.session_state.patient_handler = PatientDataHandler(str(PROJECT_ROOT))
    if "patient_data" not in st.session_state:
        st.session_state.patient_data = st.session_state.patient_handler.create_or_load_patient()
    if "session_started" not in st.session_state:
        st.session_state.session_started = False
    if "structured_anamnesis" not in st.session_state:
        st.session_state.structured_anamnesis = {}
    if "doc_offer_shown" not in st.session_state:
        st.session_state.doc_offer_shown = False
    if "docs_analysis_done" not in st.session_state:
        st.session_state.docs_analysis_done = False
    if "diff_diagnosis_generated" not in st.session_state:
        st.session_state.diff_diagnosis_generated = False
    if "last_diagnosis_text" not in st.session_state:
        st.session_state.last_diagnosis_text = ""
    if "investigation_plan_generated" not in st.session_state:
        st.session_state.investigation_plan_generated = False
    if "final_diagnosis_generated" not in st.session_state:
        st.session_state.final_diagnosis_generated = False
    if "iteration_count" not in st.session_state:
        st.session_state.iteration_count = 0
    if "resume_offered" not in st.session_state:
        st.session_state.resume_offered = False
    if "needs_resume_continuation" not in st.session_state:
        st.session_state.needs_resume_continuation = False


def reset_session():
    st.session_state.messages = []
    st.session_state.anamnesis_manager = AnamnesisManager()
    st.session_state.patient_data = st.session_state.patient_handler.create_or_load_patient()
    st.session_state.session_started = False
    st.session_state.structured_anamnesis = {}
    st.session_state.doc_offer_shown = False
    st.session_state.docs_analysis_done = False
    st.session_state.diff_diagnosis_generated = False
    st.session_state.last_diagnosis_text = ""
    st.session_state.investigation_plan_generated = False
    st.session_state.final_diagnosis_generated = False
    st.session_state.iteration_count = 0
    st.session_state.resume_offered = False
    st.session_state.needs_resume_continuation = False


def resume_session():
    handler: PatientDataHandler = st.session_state.patient_handler
    saved = handler.load_latest_session()
    if not saved:
        return

    st.session_state.messages = saved.get("messages", [])
    st.session_state.patient_data = saved.get("patient_data",
        handler.create_or_load_patient())
    st.session_state.structured_anamnesis = saved.get("structured_anamnesis", {})

    manager: AnamnesisManager = st.session_state.anamnesis_manager
    stage_num = saved.get("stage_number", 1)
    try:
        # Fix: cap at FINAL_DIAGNOSIS (15), not FINISHED (11)
        manager.current_stage = AnamnesisStage(
            min(stage_num, AnamnesisStage.FINAL_DIAGNOSIS.value)
        )
    except ValueError:
        manager.current_stage = AnamnesisStage.CHIEF_COMPLAINTS

    st.session_state.session_started = True
    st.session_state.doc_offer_shown = (stage_num >= AnamnesisStage.COMPLETE.value)
    st.session_state.docs_analysis_done = (stage_num >= AnamnesisStage.FINISHED.value)
    st.session_state.diff_diagnosis_generated = (
        stage_num >= AnamnesisStage.DIFFERENTIAL_DIAGNOSIS.value
    )
    st.session_state.last_diagnosis_text = saved.get("last_diagnosis_text", "")
    st.session_state.investigation_plan_generated = (
        stage_num >= AnamnesisStage.TEST_PRIORITIZATION.value
    )
    st.session_state.final_diagnosis_generated = (
        stage_num >= AnamnesisStage.FINAL_DIAGNOSIS.value
    )
    st.session_state.iteration_count = saved.get("iteration_count", 0)

    # For anamnesis stages: AMDA will auto-send a continuation message
    if AnamnesisStage.CHIEF_COMPLAINTS.value <= stage_num < AnamnesisStage.COMPLETE.value:
        st.session_state.needs_resume_continuation = True


# ─── Save helper ─────────────────────────────────────────────────────────────
def save_current_data():
    handler: PatientDataHandler = st.session_state.patient_handler
    data = st.session_state.patient_data
    manager: AnamnesisManager = st.session_state.anamnesis_manager

    data["last_updated"] = datetime.now().strftime("%d.%m.%Y %H:%M")
    data["diagnostic_status"] = f"В процессе — {manager.get_stage_description()}"

    handler.save_patient_data(data, st.session_state.structured_anamnesis)
    handler.update_diagnostic_log(data["patient_id"], manager.get_stage_description())
    handler.save_session(
        patient_id=data["patient_id"],
        stage_number=manager.get_stage_number(),
        messages=st.session_state.messages,
        patient_data=data,
        structured_anamnesis=st.session_state.structured_anamnesis,
        documents_analyzed=data.get("documents_analyzed", []),
        extra={
            "last_diagnosis_text": st.session_state.get("last_diagnosis_text", ""),
            "iteration_count": st.session_state.get("iteration_count", 0),
        },
    )


# ─── Header ──────────────────────────────────────────────────────────────────
def _handle_new_session_request():
    """Archive current patient (if any) and reset to a fresh session."""
    handler: PatientDataHandler = st.session_state.patient_handler
    if st.session_state.get("session_started"):
        patient_id = st.session_state.patient_data.get("patient_id")
        if patient_id:
            save_current_data()
            handler.archive_patient(patient_id)
    reset_session()
    # Skip the resume-offer screen; jump straight to a new consultation
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    st.session_state.messages.append(
        {"role": "assistant", "content": get_initial_greeting()}
    )
    st.session_state.session_started = True
    st.session_state.resume_offered = True  # suppress offer on this fresh start
    manager.advance_stage()  # START → CHIEF_COMPLAINTS
    save_current_data()
    st.rerun()


def render_header():
    from ui.chat_handler import _get_var as _chat_get_var
    _openai_base = _chat_get_var("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    _openai_label = "OpenAI" if "openai.com" in _openai_base else f"OpenAI-compat ({_openai_base.split('/')[2]})"
    provider_labels = {"groq": "Groq (free)", "ollama": "Ollama (local)",
                       "anthropic": "Anthropic", "openai": _openai_label}
    provider_label = provider_labels.get(get_active_provider(), get_active_provider())

    col_title, col_btn1, col_btn2 = st.columns([4, 3, 3])
    with col_title:
        st.title("🏥 AMDA")
        st.caption(f"AI Medical Diagnostic Assistant · Model: **{provider_label}**")
    with col_btn1:
        st.write("")  # vertical align
        if st.button("🆕 Новая сессия", use_container_width=True,
                     key="hdr_btn_new",
                     help="Завершить текущую сессию, архивировать карту и начать новую консультацию"):
            _handle_new_session_request()
    with col_btn2:
        st.write("")
        if st.button("🚪Выйти из системы", use_container_width=True,
                     key="hdr_btn_exit",
                     help="Выйти из системы (остановить AMDA, сессия сохраняется)"):
            os._exit(0)

    st.markdown("""<div class="disclaimer-banner">
    ⚠️ <strong>Важно:</strong> Эта система является вспомогательным инструментом.
    Окончательный диагноз и план лечения может поставить только лицензированный врач.
    </div>""", unsafe_allow_html=True)


# ─── Progress ────────────────────────────────────────────────────────────────
def render_progress():
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    st.markdown(
        f'<div class="stage-label">Этап: {manager.get_stage_description()}</div>',
        unsafe_allow_html=True,
    )
    st.progress(min(manager.get_progress() / 100.0, 1.0))
    st.write("")


# ─── Chat display ────────────────────────────────────────────────────────────
def _scroll_to_bottom():
    """Inject JS to scroll the Streamlit main container to the bottom."""
    import streamlit.components.v1 as components
    components.html(
        """<script>
        (function() {
            var selectors = [
                'section[data-testid="stMain"]',
                'section.main',
                '.main .block-container',
                '[data-testid="stAppViewContainer"]'
            ];
            for (var i = 0; i < selectors.length; i++) {
                var el = window.parent.document.querySelector(selectors[i]);
                if (el) { el.scrollTop = el.scrollHeight; break; }
            }
        })();
        </script>""",
        height=0,
    )


def render_chat():
    for msg in st.session_state.messages:
        avatar = "🏥" if msg["role"] == "assistant" else "👤"
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
    _scroll_to_bottom()


# ─── Stage advance heuristic ─────────────────────────────────────────────────
_COMPLETION_KEYWORDS = (
    "анамнез завершён", "анамнез собран", "сбор анамнеза завершён",
    "сбор анамнеза закончен", "информация собрана", "данные собраны",
    "anamnesis complete", "anamnesis is complete", "collection complete",
    "all stages complete", "ready to proceed",
)


def should_advance_stage(user_message: str, current_stage: AnamnesisStage) -> bool:
    if current_stage.value >= AnamnesisStage.COMPLETE.value:
        return False
    msg = user_message.strip()
    if not msg:
        return False
    # At REVIEW stage any non-empty response finishes the anamnesis
    if current_stage == AnamnesisStage.REVIEW:
        return True
    if current_stage == AnamnesisStage.START:
        return True
    return len(msg) > 15


def response_signals_completion(response: str) -> bool:
    """Return True if AMDA's response explicitly signals anamnesis is complete."""
    lower = response.lower()
    return any(kw in lower for kw in _COMPLETION_KEYWORDS)


# ─── Document offer & analysis ───────────────────────────────────────────────
def handle_complete_stage():
    """Called once when anamnesis reaches COMPLETE. Extracts structure + shows doc offer."""
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    handler: PatientDataHandler = st.session_state.patient_handler

    if not st.session_state.doc_offer_shown:
        # Extract structured anamnesis from conversation
        with st.spinner("Структурирую анамнез..."):
            structured = extract_structured_anamnesis(st.session_state.messages)
            if structured:
                st.session_state.structured_anamnesis = structured
                # Merge red_flags into patient_data for display
                if structured.get("red_flags"):
                    st.session_state.patient_data["red_flags"] = structured["red_flags"]

        # Build document offer message
        docs, skipped_docs = handler.scan_documents_filtered()
        n = len(docs)
        if n > 0:
            doc_list = "\n".join(f"  - `{d.name}`" for d in docs[:10])
            extra = f"\n  - _(и ещё {n - 10} файлов)_" if n > 10 else ""
            offer_msg = (
                "**Анамнез успешно собран!** ✅\n\n"
                f"В каталоге `documents/` найдено **{n} актуальных медицинских документов**:\n"
                f"{doc_list}{extra}\n\n"
            )
        else:
            offer_msg = (
                "**Анамнез успешно собран!** ✅\n\n"
                "Каталог `documents/` не содержит актуальных поддерживаемых файлов.\n\n"
            )
        if skipped_docs:
            skipped_list = "\n".join(
                f"  - `{s['filename']}` — дата: {s['doc_date']}, возраст: {s['age_days']} дн. "
                f"(лимит для категории «{s['category']}»: {s['max_days']} дн.)"
                for s in skipped_docs
            )
            offer_msg += (
                f"⚠️ **Исключено как устаревшее ({len(skipped_docs)} файлов):**\n"
                f"{skipped_list}\n\n"
            )
        if n > 0:
            offer_msg += "Подключить актуальные документы к анализу?"
        else:
            offer_msg += "Хотите всё равно продолжить или пропустить этот шаг?"

        offer_msg += DISCLAIMER_SUFFIX
        st.session_state.messages.append({"role": "assistant", "content": offer_msg})
        st.session_state.doc_offer_shown = True
        save_current_data()
        st.rerun()

    # Render Yes/No buttons
    render_chat()
    _, c1, c2, _ = st.columns([3, 2, 2, 3])
    with c1:
        if st.button("✅ Да, добавить документы", use_container_width=True, key="btn_yes"):
            st.session_state.messages.append(
                {"role": "user", "content": "Да, подключить документы"}
            )
            manager.advance_stage()  # → DOCUMENT_ANALYSIS
            save_current_data()
            st.rerun()
    with c2:
        if st.button("❌ Нет, пропустить", use_container_width=True, key="btn_no"):
            st.session_state.messages.append(
                {"role": "user", "content": "Нет, продолжить без документов"}
            )
            manager.advance_stage()  # COMPLETE → DOCUMENT_ANALYSIS
            manager.advance_stage()  # DOCUMENT_ANALYSIS → FINISHED
            # FINISHED is a transient state — main() will immediately advance to
            # DIFFERENTIAL_DIAGNOSIS, so the message should reflect that.
            skip_msg = (
                "Хорошо, продолжим без анализа документов. "
                "Перехожу к формированию дифференциального диагноза на основе собранного анамнеза."
                + DISCLAIMER_SUFFIX
            )
            st.session_state.messages.append({"role": "assistant", "content": skip_msg})
            st.session_state.docs_analysis_done = True  # nothing to analyse
            save_current_data()
            st.rerun()


def handle_document_analysis():
    """Called once when stage is DOCUMENT_ANALYSIS."""
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    handler: PatientDataHandler = st.session_state.patient_handler

    if not st.session_state.docs_analysis_done:
        render_chat()
        docs, skipped_docs = handler.scan_documents_filtered()
        if not docs:
            skipped_note = ""
            if skipped_docs:
                skipped_list = "\n".join(
                    f"  - `{s['filename']}` (дата: {s['doc_date']}, возраст: {s['age_days']} дн., "
                    f"лимит: {s['max_days']} дн.)"
                    for s in skipped_docs
                )
                skipped_note = (
                    f"\n\n⚠️ **Исключено как устаревшее ({len(skipped_docs)} файлов):**\n"
                    f"{skipped_list}"
                )
            msg = (
                "Актуальные документы не найдены в каталоге `documents/`."
                + skipped_note
                + DISCLAIMER_SUFFIX
            )
            st.session_state.messages.append({"role": "assistant", "content": msg})
            manager.advance_stage()  # → FINISHED
            st.session_state.docs_analysis_done = True
            save_current_data()
            st.rerun()

        results = []
        cached_count = 0
        retry_count = 0
        progress_bar = st.progress(0, text="Анализирую документы...")
        for i, doc_path in enumerate(docs):
            # Check cache first
            cached = handler.get_cached_document(doc_path.name, doc_path)
            if cached and not is_error_analysis(cached.get("analysis_text")):
                cached_count += 1
                cached["from_cache"] = True
                results.append(cached)
                progress_bar.progress(
                    int((i + 1) / len(docs) * 100),
                    text=f"Из кэша: {doc_path.name} ({i+1}/{len(docs)})",
                )
            else:
                is_retry = cached is not None  # was cached but with an error
                if is_retry:
                    retry_count += 1
                    status_text = f"Повторная обработка (ошибка в кэше): {doc_path.name} ({i+1}/{len(docs)})..."
                else:
                    status_text = f"Анализирую {doc_path.name} ({i+1}/{len(docs)})..."
                progress_bar.progress(int((i + 1) / len(docs) * 100), text=status_text)
                content = handler.read_document_content(doc_path)
                result = analyze_document(doc_path.name, content, doc_path.suffix.lower())
                result["from_cache"] = False
                handler.save_to_document_cache(doc_path.name, result, doc_path)
                results.append(result)
        progress_bar.empty()
        notes = []
        if cached_count:
            notes.append(f"{cached_count} из кэша")
        if retry_count:
            notes.append(f"{retry_count} повторно обработано (ошибки в кэше)")
        if notes:
            st.caption(f"ℹ️ {'; '.join(notes)}.")

        # Save to handler
        handler.save_document_analysis(
            patient_id=st.session_state.patient_data["patient_id"],
            documents=results,
        )
        st.session_state.patient_data["documents_analyzed"] = results

        # Generate one combined analysis for the chat (individual analyses saved to current-patient.md)
        with st.spinner("Формирую общий анализ документов..."):
            combined = generate_combined_analysis(results)

        cached_note = f" ({cached_count} из кэша)" if cached_count else ""
        header = f"**Анализ медицинских документов завершён** — {len(results)} файлов{cached_note}\n"
        summary = header + "\n" + combined + DISCLAIMER_SUFFIX

        st.session_state.messages.append({"role": "assistant", "content": summary})
        st.session_state.docs_analysis_done = True
        manager.advance_stage()  # → FINISHED
        save_current_data()
        st.rerun()


def _build_patient_context() -> str:
    """Read current-patient.md and return its content as context for the LLM."""
    handler: PatientDataHandler = st.session_state.patient_handler
    if handler.current_patient_file.exists():
        try:
            return handler.current_patient_file.read_text(encoding="utf-8")
        except Exception:
            pass
    # Fallback: use structured anamnesis from session state
    import json
    return json.dumps(st.session_state.patient_data, ensure_ascii=False, indent=2)


def handle_differential_diagnosis():
    """Interactive differential diagnosis stage."""
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    handler: PatientDataHandler = st.session_state.patient_handler

    # First entry: auto-generate differential diagnosis
    if not st.session_state.diff_diagnosis_generated:
        render_chat()
        with st.spinner("Формирую дифференциальный диагноз..."):
            patient_context = _build_patient_context()
            diagnosis_text = generate_differential_diagnosis(patient_context)

        st.session_state.last_diagnosis_text = diagnosis_text
        st.session_state.diff_diagnosis_generated = True

        msg = "## Дифференциальный диагноз\n\n" + diagnosis_text
        st.session_state.messages.append({"role": "assistant", "content": msg})

        # Update diagnosis list in patient_data for current-patient.md
        st.session_state.patient_data["diagnostic_status"] = "Дифференциальный диагноз сформирован"
        save_current_data()
        st.rerun()

    # Subsequent renders: show chat + controls
    render_chat()

    col_info, col_btn = st.columns([3, 1])
    with col_info:
        st.info(
            "💬 Вы можете уточнить информацию или задать вопрос. "
            "Система пересчитает вероятности с учётом новых данных."
        )
    with col_btn:
        if st.button("📋 План исследований →",
                     help="Перейти к составлению плана дополнительных исследований",
                     use_container_width=True,
                     key="btn_go_to_plan"):
            manager.advance_stage()  # → TEST_PRIORITIZATION
            save_current_data()
            st.rerun()

    user_input = st.chat_input("Добавьте информацию или задайте вопрос о диагнозе...")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🏥"):
            with st.spinner("Пересчитываю вероятности..."):
                patient_context = _build_patient_context()
                updated = recalculate_differential_diagnosis(
                    new_info=user_input,
                    patient_context=patient_context,
                    previous_diagnosis=st.session_state.last_diagnosis_text,
                )

            st.markdown(updated)

        st.session_state.last_diagnosis_text = updated
        st.session_state.messages.append({"role": "assistant", "content": updated})

        st.session_state.patient_data["diagnostic_status"] = (
            "Дифференциальный диагноз обновлён"
        )
        save_current_data()
        st.rerun()


def _retry_diagnostics():
    """Reset diagnostic flags and return to DOCUMENT_ANALYSIS for a new iteration."""
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    st.session_state.iteration_count = st.session_state.get("iteration_count", 0) + 1
    # Reset only diagnostic-phase flags; keep anamnesis and doc offer flags
    st.session_state.docs_analysis_done = False
    st.session_state.diff_diagnosis_generated = False
    st.session_state.investigation_plan_generated = False
    st.session_state.last_diagnosis_text = ""
    manager.set_stage(AnamnesisStage.DOCUMENT_ANALYSIS)


def handle_awaiting_results():
    """Waiting state: no diagnosis reached the threshold. Show retry button."""
    render_chat()
    iteration = st.session_state.get("iteration_count", 0)
    st.warning(
        f"**Ни один диагноз не достиг порога {DIAGNOSIS_THRESHOLD}%.** (Итерация {iteration})\n\n"
        "Пройдите рекомендованные исследования и загрузите результаты "
        "в каталог `documents/`, затем нажмите кнопку ниже."
    )
    if st.button("🔄 Повторить диагностику",
                 help="Система проанализирует новые документы и пересчитает диагнозы",
                 key="btn_retry_diagnostics"):
        _retry_diagnostics()
        save_current_data()
        st.rerun()


def handle_final_diagnosis():
    """Generate final diagnosis when threshold reached, then archive the case."""
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    handler: PatientDataHandler = st.session_state.patient_handler

    if not st.session_state.get("final_diagnosis_generated"):
        render_chat()
        with st.spinner("Формирую окончательный диагноз..."):
            patient_context = _build_patient_context()
            final_text = generate_final_diagnosis(
                patient_context=patient_context,
                diagnosis_text=st.session_state.get("last_diagnosis_text", ""),
            )

        st.session_state.final_diagnosis_generated = True
        msg = "## Окончательный диагноз\n\n" + final_text
        st.session_state.messages.append({"role": "assistant", "content": msg})

        # Update patient data and archive per patient-data-management.md
        patient_id = st.session_state.patient_data["patient_id"]
        st.session_state.patient_data["diagnostic_status"] = "Окончательный диагноз поставлен"
        save_current_data()

        archived_path = handler.archive_patient(patient_id)
        st.session_state["archived_path"] = str(archived_path)
        st.rerun()

    render_chat()
    archived = st.session_state.get("archived_path", "")
    st.success(
        f"✅ **Диагностика завершена.** Карта пациента сохранена в архив.\n\n"
        f"Файл: `{Path(archived).name if archived else 'archive/'}`"
    )
    if st.button("👤 Начать новую консультацию",
                 key="btn_new_patient"):
        reset_session()
        st.rerun()


def handle_test_prioritization():
    """Generate and display prioritized investigation plan, then branch on diagnosis threshold."""
    manager: AnamnesisManager = st.session_state.anamnesis_manager

    if not st.session_state.get("investigation_plan_generated"):
        render_chat()
        with st.spinner("Составляю план дополнительных исследований..."):
            patient_context = _build_patient_context()
            plan_text = generate_investigation_plan(
                patient_context=patient_context,
                diagnosis_text=st.session_state.get("last_diagnosis_text", ""),
            )

        st.session_state.investigation_plan_generated = True
        msg = "## План дополнительных исследований\n\n" + plan_text
        st.session_state.messages.append({"role": "assistant", "content": msg})
        st.session_state.patient_data["diagnostic_status"] = "План исследований сформирован"

        # Check if any diagnosis has reached the configured threshold
        max_prob = extract_max_probability(
            st.session_state.get("last_diagnosis_text", "")
        )
        if max_prob >= DIAGNOSIS_THRESHOLD:
            manager.set_stage(AnamnesisStage.FINAL_DIAGNOSIS)
        else:
            manager.set_stage(AnamnesisStage.AWAITING_RESULTS)

        save_current_data()
        st.rerun()

    # Already generated — just show chat for the current branch
    render_chat()


def handle_resume_offer():
    """Show a resume-or-start-fresh choice in the chat before the session begins."""
    handler: PatientDataHandler = st.session_state.patient_handler
    saved = handler.load_latest_session()

    if not st.session_state.resume_offered:
        if saved:
            ts = saved.get("updated_at", "")[:16].replace("T", " ")
            stage_num = saved.get("stage_number", 1)
            try:
                stage_label = AnamnesisStage(stage_num).name.replace("_", " ").capitalize()
            except ValueError:
                stage_label = f"Этап {stage_num}"
            patient_id = saved.get("patient_id", "—")
            msg_count = len(saved.get("messages", []))
            offer_text = (
                "Здравствуйте! Я **AMDA** — AI-ассистент медицинской диагностики.\n\n"
                f"Обнаружена сохранённая сессия:\n"
                f"- **Пациент:** `{patient_id}`\n"
                f"- **Последнее обновление:** {ts}\n"
                f"- **Текущий этап:** {stage_label}\n"
                f"- **Сообщений в истории:** {msg_count}\n\n"
                "Хотите продолжить с того места, где остановились?"
            )
            st.session_state.messages.append({"role": "assistant", "content": offer_text})
        st.session_state.resume_offered = True
        st.rerun()
        return

    # Offer already shown — render chat and buttons
    render_chat()
    if saved:
        _, c1, c2, _ = st.columns([2, 3, 3, 2])
        with c1:
            if st.button("▶ Продолжить сессию", use_container_width=True,
                         key="chat_btn_resume"):
                resume_session()
                st.rerun()
        with c2:
            if st.button("🆕 Начать заново", use_container_width=True,
                         key="chat_btn_new"):
                st.session_state.messages.append(
                    {"role": "user", "content": "Начать новую консультацию"}
                )
                _start_fresh_session()
    else:
        # No saved session — start fresh immediately
        _start_fresh_session()


def _start_fresh_session():
    """Show the greeting and move to CHIEF_COMPLAINTS."""
    manager: AnamnesisManager = st.session_state.anamnesis_manager
    st.session_state.messages.append(
        {"role": "assistant", "content": get_initial_greeting()}
    )
    st.session_state.session_started = True
    manager.advance_stage()  # START → CHIEF_COMPLAINTS
    save_current_data()
    st.rerun()


DISCLAIMER_SUFFIX = (
    "\n\n---\n"
    "*Эта система является вспомогательным инструментом. "
    "Окончательный диагноз и план лечения может поставить только "
    "лицензированный врач. Не предпринимайте никаких действий на основании "
    "этих рекомендаций без очной консультации со специалистом.*"
)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    init_session()
    render_header()
    render_progress()

    manager: AnamnesisManager = st.session_state.anamnesis_manager

    # First load — offer to resume or start fresh
    if not st.session_state.session_started:
        handle_resume_offer()
        return

    # ── Special stage handlers ──────────────────────────────────────────────
    if manager.current_stage == AnamnesisStage.COMPLETE:
        handle_complete_stage()
        return  # buttons rendered inside, no chat_input needed

    if manager.current_stage == AnamnesisStage.DOCUMENT_ANALYSIS:
        handle_document_analysis()
        return

    # FINISHED is a transient state: immediately advance to differential diagnosis
    if manager.current_stage == AnamnesisStage.FINISHED:
        manager.advance_stage()  # → DIFFERENTIAL_DIAGNOSIS
        save_current_data()
        st.rerun()
        return

    if manager.current_stage == AnamnesisStage.DIFFERENTIAL_DIAGNOSIS:
        handle_differential_diagnosis()
        return

    if manager.current_stage == AnamnesisStage.TEST_PRIORITIZATION:
        handle_test_prioritization()
        return

    if manager.current_stage == AnamnesisStage.AWAITING_RESULTS:
        handle_awaiting_results()
        return

    if manager.current_stage == AnamnesisStage.FINAL_DIAGNOSIS:
        handle_final_diagnosis()
        return

    # ── Normal chat flow ────────────────────────────────────────────────────
    render_chat()

    # Auto-continue after resume: AMDA sends the next question without waiting for input
    if st.session_state.get("needs_resume_continuation"):
        st.session_state.needs_resume_continuation = False
        with st.spinner("AMDA продолжает консультацию..."):
            api_messages = [
                {"role": m["role"], "content": m["content"]}
                for m in st.session_state.messages[-20:]
            ]
            resume_response = generate_resume_continuation(
                api_messages, manager.get_stage_number()
            )
        st.session_state.messages.append({"role": "assistant", "content": resume_response})
        if (manager.current_stage.value < AnamnesisStage.COMPLETE.value
                and response_signals_completion(resume_response)):
            manager.current_stage = AnamnesisStage.COMPLETE
        save_current_data()
        st.rerun()

    # "Complete anamnesis" button — visible from REVIEW stage onwards
    if manager.current_stage.value >= AnamnesisStage.REVIEW.value:
        if st.button("✅ Завершить сбор анамнеза",
                     help="Перейти к анализу документов",
                     use_container_width=False,
                     key="btn_finish_anamnesis"):
            manager.current_stage = AnamnesisStage.COMPLETE
            save_current_data()
            st.rerun()

    user_input = st.chat_input("Опишите симптомы или ответьте на вопрос выше...")

    if user_input:
        st.session_state.messages.append({"role": "user", "content": user_input})
        with st.chat_message("user", avatar="👤"):
            st.markdown(user_input)

        if should_advance_stage(user_input, manager.get_current_stage()):
            manager.advance_stage()

        with st.chat_message("assistant", avatar="🏥"):
            with st.spinner("AMDA думает..."):
                api_messages = [
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages[-20:]
                ]
                response = generate_response(
                    messages=api_messages,
                    anamnesis_stage=manager.get_stage_number(),
                )
            st.markdown(response)

        st.session_state.messages.append({"role": "assistant", "content": response})

        # If AMDA signals completion in its response — force transition to COMPLETE
        if (manager.current_stage.value < AnamnesisStage.COMPLETE.value
                and response_signals_completion(response)):
            manager.current_stage = AnamnesisStage.COMPLETE

        save_current_data()
        st.rerun()


if __name__ == "__main__":
    main()
