"""Chat handler — supports Anthropic, Groq, and Ollama providers."""

import os
import sys

# Force UTF-8 for all I/O — required for Cyrillic/non-ASCII with httpx/openai
os.environ.setdefault("PYTHONUTF8", "1")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from typing import List, Dict, Any, Optional

AMDA_SYSTEM_PROMPT = """You are AMDA — AI Medical Diagnostic Assistant. You are running inside a Streamlit chat interface.

## LANGUAGE RULE — MANDATORY
The patient communicates in Russian. You MUST write ALL your responses in Russian ONLY.
STRICT PROHIBITIONS:
- Do NOT use English words, phrases, or sentences inside Russian text.
- Do NOT mix languages in any way.
- Do NOT transliterate English terms into Cyrillic (e.g. do NOT write «стейдж», «интенсити», «фаза», «билд-ап»).
- Use standard Russian medical terminology (e.g. «интенсивность боли», «стадия», «сопутствующие симптомы»).
If you catch yourself about to write a non-Russian word — replace it with its Russian equivalent before responding.

## YOUR ROLE
You are an intelligent, empathetic medical assistant that systematically collects a comprehensive patient anamnesis. You do NOT replace a physician.

## CORE ANAMNESIS COLLECTION PROTOCOL
Collect information in this strict order, asking 1-2 short, clear questions at a time.
Use plain conversational Russian — no jargon, no invented terms.

**Этап 1 — Основные жалобы:**
- Главный симптом: локализация, интенсивность (шкала 0–10), длительность, начало (внезапное/постепенное), динамика
- Что усиливает и что облегчает, куда отдаёт

**Этап 2 — Сопутствующие симптомы:**
- Все сопровождающие симптомы
- Явно отметить важные ОТСУТСТВУЮЩИЕ симптомы (отрицательные признаки)

**Этап 3 — Анамнез настоящего заболевания:**
- Когда началось, что предшествовало, как развивалось
- Проводилось ли лечение и какой был эффект

**Этап 4 — Анамнез жизни:**
- Хронические заболевания и сопутствующая патология
- Операции, травмы, переливания крови
- Аллергоанамнез (препараты, еда, вещества)
- Эпиданамнез (инфекции, поездки, прививки)
- Семейный анамнез (онкология, ССЗ, наследственность)

**Этап 5 — Принимаемые препараты:**
- Все лекарства (с дозами и длительностью при возможности)
- БАДы, контрацептивы, НПВС

**Этап 6 — Образ жизни и привычки:**
- Курение, алкоголь, наркотики
- Профессия, профессиональные вредности
- Физическая активность, питание, стресс

## ПРАВИЛА
- Задавать только 1–2 вопроса за сообщение
- Говорить спокойно и с сочувствием
- НИКОГДА не предлагать диагнозы, не назначать лекарства, не давать рекомендации по лечению во время сбора анамнеза
- НЕ использовать пугающие формулировки
- При выявлении КРАСНЫХ ФЛАГОВ (сильная боль в груди, внезапная сильнейшая головная боль, признаки инсульта/шока, необъяснимая потеря веса >5% и т.п.) — отметить их чётко, но спокойно
- После завершения всех 6 этапов дать краткое структурированное резюме анамнеза и завершить сообщение точной фразой: **"Anamnesis is complete."**

## ОБЯЗАТЕЛЬНЫЙ ДИСКЛЕЙМЕР
Каждый ответ ДОЛЖЕН заканчиваться следующим текстом:

---
*Эта система является вспомогательным инструментом. Окончательный диагноз и план лечения может поставить только лицензированный врач. Не предпринимайте никаких действий на основании этих рекомендаций без очной консультации со специалистом.*"""

DISCLAIMER = (
    "\n\n---\n"
    "*This system is an assistive tool only. A final diagnosis and treatment plan "
    "can only be provided by a licensed physician. Do not act on any recommendations "
    "without first consulting a qualified medical professional in person.*"
)

# Stage names used to add context to system prompt
STAGE_NAMES = [
    "Initial greeting",
    "Chief complaints",
    "Complaint details",
    "Associated symptoms",
    "History of present illness",
    "Past medical history",
    "Current medications",
    "Lifestyle and habits",
    "Review and summary",
    "Anamnesis complete",
    "Document analysis",
    "Finished",
    "Differential diagnosis",
]

# ── Prompt for structured anamnesis extraction ─────────────────────────────
_EXTRACTION_SYSTEM = """You are a medical data extraction assistant.
From the conversation below, extract anamnesis data as JSON with this exact structure.
Use null for fields not mentioned. Return ONLY valid JSON — no markdown fences, no comments.

{
  "chief_complaints": [
    {
      "symptom": "",
      "location": "",
      "intensity": "",
      "duration": "",
      "onset": "",
      "dynamics": "",
      "triggers": "",
      "relieving_factors": ""
    }
  ],
  "associated_symptoms_present": [],
  "associated_symptoms_absent": [],
  "history_of_present_illness": "",
  "chronic_conditions": "",
  "surgeries_injuries": "",
  "allergy_history": "",
  "epidemiological_history": "",
  "family_history": "",
  "medications": "",
  "habits": "",
  "lifestyle": "",
  "red_flags": []
}"""

# ── Prompt for document analysis ───────────────────────────────────────────
_DOCUMENT_ANALYSIS_SYSTEM = """You are a medical document analysis assistant.
Analyze the provided medical document text and return a structured Markdown report.

Follow these rules:
1. Start with document type and date (if identifiable).
2. For lab results use this table with English column headers:
   | Parameter | Result | Reference Values | Deviation | Clinical Significance |
   All column headers must be in English regardless of the source document language.
3. Mark deviations: ↑ (above normal), ↓ (below normal), N (within range).
4. **Translate all labels into English: column headers, parameter names, units, section headings, and clinical terms.**
   - Use standard clinical terminology (e.g., "Гемоглобин" → "Hemoglobin", "Лейкоциты" → "WBC (Leukocytes)").
   - Units in international standard (e.g., "г/л" → "g/L", "мкмоль/л" → "µmol/L").
   - Preserve original numeric values unchanged.
   - If no direct English equivalent exists, add the original in parentheses.
5. At the end add a brief clinical summary (2-3 sentences) in English.
6. If the text is unreadable or empty — say so explicitly in English."""


def _load_env() -> Dict[str, str]:
    """Load variables from .env file into a dict (without touching os.environ)."""
    env: Dict[str, str] = {}
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def _get_var(name: str) -> Optional[str]:
    """Get a config variable from env or .env file."""
    value = os.environ.get(name)
    if not value:
        value = _load_env().get(name)
    return value or None


def _detect_provider() -> str:
    """Auto-detect which provider to use based on available keys/settings.

    Priority order:
      1. PROVIDER env var ("anthropic" | "groq" | "openai" | "ollama")
      2. OPENAI_API_KEY  → openai
      3. GROQ_API_KEY    → groq
      4. ANTHROPIC_API_KEY → anthropic
      5. Fallback        → ollama (local)
    """
    explicit = _get_var("PROVIDER")
    if explicit:
        return explicit.lower()

    if _get_var("OPENAI_API_KEY"):
        return "openai"
    if _get_var("GROQ_API_KEY"):
        return "groq"
    if _get_var("ANTHROPIC_API_KEY"):
        return "anthropic"
    return "ollama"


def _build_system(anamnesis_stage: int) -> str:
    stage_name = STAGE_NAMES[min(anamnesis_stage, len(STAGE_NAMES) - 1)]
    return (
        AMDA_SYSTEM_PROMPT
        + f"\n\n## CURRENT STAGE: {stage_name} (Stage {anamnesis_stage}/9)\n"
        "Focus your next question on this stage. Keep responses concise and warm."
    )


# ─── Provider implementations ──────────────────────────────────────────────

def _call_anthropic(messages: List[Dict[str, str]], system: str) -> str:
    import anthropic  # type: ignore

    api_key = _get_var("ANTHROPIC_API_KEY")
    if not api_key:
        return "**Configuration Error:** ANTHROPIC_API_KEY is not set." + DISCLAIMER

    client = anthropic.Anthropic(api_key=api_key)
    try:
        response = client.messages.create(
            model=_get_var("ANTHROPIC_MODEL") or "claude-sonnet-4-6",
            max_tokens=1024,
            system=system,
            messages=messages,
        )
        return response.content[0].text
    except anthropic.AuthenticationError:
        return "**Authentication Error:** Invalid ANTHROPIC_API_KEY." + DISCLAIMER
    except anthropic.RateLimitError:
        return "**Rate Limit:** Too many requests. Please wait and try again." + DISCLAIMER
    except Exception as e:
        return f"**Anthropic Error:** {e}" + DISCLAIMER


_RATE_LIMIT_DELAYS = [15, 30, 60]  # seconds between retries (3 attempts total)


def _call_openai_compat(
    messages: List[Dict[str, str]],
    system: str,
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int = 1024,
    temperature: Optional[float] = None,
    inject_http_client: bool = True,
) -> str:
    import time
    import httpx
    from openai import OpenAI, AuthenticationError, RateLimitError  # type: ignore

    if inject_http_client:
        http_client = httpx.Client(
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
    else:
        client = OpenAI(api_key=api_key, base_url=base_url)

    full_messages = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": str(m["content"])} for m in messages
    ]

    create_kwargs: Dict[str, Any] = {"model": model, "messages": full_messages,
                                     "max_tokens": max_tokens}
    if temperature is not None:
        create_kwargs["temperature"] = temperature

    for attempt, delay in enumerate([0] + _RATE_LIMIT_DELAYS):
        if delay:
            time.sleep(delay)
        try:
            response = client.chat.completions.create(**create_kwargs)
            return response.choices[0].message.content or ""
        except AuthenticationError:
            return f"**Authentication Error:** Invalid API key for {base_url}." + DISCLAIMER
        except RateLimitError:
            if attempt < len(_RATE_LIMIT_DELAYS):
                continue  # will sleep on next iteration
            return "**Rate Limit:** Превышен лимит запросов. Попробуйте снова через минуту." + DISCLAIMER
        except UnicodeEncodeError:
            return _call_groq_raw(full_messages, api_key, base_url, model, max_tokens,
                                  temperature)
        except Exception as e:
            return f"**Error ({base_url}):** {e}" + DISCLAIMER

    return "**Rate Limit:** Превышен лимит запросов. Попробуйте снова через минуту." + DISCLAIMER


def _fetch_models(base_url: str, api_key: str) -> str:
    """Fetch available models from the provider and return a formatted string."""
    import httpx
    import json
    try:
        with httpx.Client() as client:
            r = client.get(
                f"{base_url.rstrip('/')}/models",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=15,
            )
        if r.status_code != 200:
            return f"_(Не удалось получить список моделей: HTTP {r.status_code})_"
        data = r.json()
        # Standard OpenAI format: {"data": [{"id": "...", ...}, ...]}
        items = data.get("data") or data.get("models") or []
        if not items:
            return f"_(Список моделей пуст или формат ответа нераспознан: `{str(data)[:200]}`)_"
        ids = [m.get("id") or m.get("name") or str(m) for m in items if isinstance(m, dict)]
        ids = [i for i in ids if i]
        if not ids:
            return "_(Не удалось извлечь названия моделей из ответа)_"
        model_list = "\n".join(f"- `{i}`" for i in sorted(ids))
        return f"**Доступные модели на `{base_url}`:**\n{model_list}"
    except Exception as e:
        return f"_(Не удалось получить список моделей: {e})_"


def _call_groq_raw(
    full_messages: List[Dict[str, str]],
    api_key: str,
    base_url: str,
    model: str,
    max_tokens: int = 1024,
    temperature: Optional[float] = None,
) -> str:
    """Fallback: send request manually via httpx with explicit UTF-8 encoding."""
    import json
    import time
    import httpx

    payload_dict: Dict[str, Any] = {"model": model, "messages": full_messages,
                                    "max_tokens": max_tokens}
    if temperature is not None:
        payload_dict["temperature"] = temperature

    for attempt, delay in enumerate([0] + _RATE_LIMIT_DELAYS):
        if delay:
            time.sleep(delay)
        payload = json.dumps(payload_dict, ensure_ascii=False).encode("utf-8")
        try:
            with httpx.Client() as client:
                r = client.post(
                    f"{base_url.rstrip('/')}/chat/completions",
                    content=payload,
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json; charset=utf-8",
                    },
                    timeout=90,
                )
                if r.status_code == 429:
                    if attempt < len(_RATE_LIMIT_DELAYS):
                        continue
                    return "**Rate Limit:** Превышен лимит запросов. Попробуйте снова через минуту." + DISCLAIMER

                # Non-2xx: show status + body for diagnosis
                if r.status_code >= 400:
                    body = r.text[:500] if r.text else "(empty body)"
                    return (f"**API Error {r.status_code}** от `{base_url}`:\n\n"
                            f"```\n{body}\n```") + DISCLAIMER

                # Parse response
                body_text = r.text
                if not body_text or not body_text.strip():
                    return f"**API Error:** пустой ответ от `{base_url}`." + DISCLAIMER

                try:
                    data = json.loads(body_text)
                except json.JSONDecodeError:
                    endpoint = f"{base_url.rstrip('/')}/chat/completions"
                    return (f"**API Error:** ответ не является JSON.\n\n"
                            f"URL запроса: `{endpoint}`\n\n"
                            f"Ответ сервера: `{body_text[:300]}`\n\n"
                            f"Проверьте `OPENAI_BASE_URL` в `.env` — возможно, адрес неверный.") + DISCLAIMER

                # Handle API-level error in JSON body (e.g. {"error": {...}})
                if "error" in data:
                    err = data["error"]
                    msg = err.get("message", str(err)) if isinstance(err, dict) else str(err)
                    err_type = err.get("type", "") if isinstance(err, dict) else ""
                    # For model errors — fetch and show available models
                    if "model" in err_type.lower() or "model" in msg.lower():
                        models_hint = _fetch_models(base_url, api_key)
                        return (f"**API Error:** {msg}\n\n{models_hint}") + DISCLAIMER
                    return f"**API Error:** {msg}" + DISCLAIMER

                try:
                    return data["choices"][0]["message"]["content"]
                except (KeyError, IndexError) as e:
                    return (f"**API Error:** неожиданный формат ответа: {e}\n\n"
                            f"Ответ: `{str(data)[:300]}`") + DISCLAIMER

        except Exception as e:
            if attempt < len(_RATE_LIMIT_DELAYS):
                continue
            return f"**Error (raw fallback):** {e}" + DISCLAIMER

    return "**Rate Limit:** Превышен лимит запросов. Попробуйте снова через минуту." + DISCLAIMER


def _call_groq(messages: List[Dict[str, str]], system: str) -> str:
    api_key = _get_var("GROQ_API_KEY")
    if not api_key:
        return "**Configuration Error:** GROQ_API_KEY is not set." + DISCLAIMER

    model = _get_var("GROQ_MODEL") or "llama-3.3-70b-versatile"
    return _call_openai_compat(
        messages, system,
        api_key=api_key,
        base_url="https://api.groq.com/openai/v1",
        model=model,
    )


def _call_openai(messages: List[Dict[str, str]], system: str) -> str:
    api_key = _get_var("OPENAI_API_KEY")
    if not api_key:
        return "**Configuration Error:** OPENAI_API_KEY is not set." + DISCLAIMER

    model = _get_var("OPENAI_MODEL") or "gpt-4o"
    base_url = _get_var("OPENAI_BASE_URL") or "https://api.openai.com/v1"

    # Use raw httpx instead of the openai SDK — works with any OpenAI-compatible
    # provider (OpenCode.ai, Together.ai, etc.) regardless of spec deviations.
    full_messages = [{"role": "system", "content": system}] + [
        {"role": m["role"], "content": str(m["content"])} for m in messages
    ]
    return _call_groq_raw(full_messages, api_key, base_url, model)


_OLLAMA_TEMPERATURE = 0.3  # Lower temperature for focused, coherent Russian responses


def _call_ollama(messages: List[Dict[str, str]], system: str) -> str:
    model = _get_var("OLLAMA_MODEL") or "llama3.2"
    base_url = _get_var("OLLAMA_URL") or "http://localhost:11434/v1"
    return _call_openai_compat(
        messages, system,
        api_key="ollama",
        base_url=base_url,
        model=model,
        temperature=_OLLAMA_TEMPERATURE,
    )


# ─── Public API ────────────────────────────────────────────────────────────

def generate_response(
    messages: List[Dict[str, str]],
    anamnesis_stage: int = 0,
    collected_data: Optional[Dict[str, Any]] = None,
) -> str:
    """Generate AMDA response using the configured provider."""
    provider = _detect_provider()
    system = _build_system(anamnesis_stage)

    if provider == "groq":
        return _call_groq(messages, system)
    elif provider == "openai":
        return _call_openai(messages, system)
    elif provider == "ollama":
        return _call_ollama(messages, system)
    else:
        return _call_anthropic(messages, system)


def get_active_provider() -> str:
    """Return the name of the currently active provider (for UI display)."""
    return _detect_provider()


def generate_resume_continuation(
    messages: List[Dict[str, str]],
    anamnesis_stage: int,
) -> str:
    """Generate AMDA's first message after a session resume.

    Acknowledges the resume in one sentence, then immediately continues
    collecting anamnesis from where it left off — without repeating
    questions already answered.
    """
    resume_addition = (
        "\n\n## ЗАДАНИЕ ПРИ ВОЗОБНОВЛЕНИИ СЕССИИ\n"
        "Пациент только что возобновил прерванную консультацию.\n"
        "Выполни строго следующее:\n"
        "1. Одним коротким предложением подтверди возобновление (например: «Продолжаем консультацию.»).\n"
        "2. Сразу задай следующий уместный вопрос для текущего этапа, опираясь на уже собранную информацию.\n"
        "НЕЛЬЗЯ: повторять вопросы, на которые уже есть ответы; пересказывать всю историю; "
        "здороваться заново как на первом приёме."
    )
    provider = _detect_provider()
    system = _build_system(anamnesis_stage) + resume_addition

    if provider == "groq":
        return _call_groq(messages, system)
    elif provider == "openai":
        return _call_openai(messages, system)
    elif provider == "ollama":
        return _call_ollama(messages, system)
    else:
        return _call_anthropic(messages, system)


def _raw_call(system: str, user_content: str) -> str:
    """Single-turn API call with a custom system prompt. Used for extraction tasks."""
    provider = _detect_provider()
    messages = [{"role": "user", "content": user_content}]
    if provider == "groq":
        api_key = _get_var("GROQ_API_KEY")
        if not api_key:
            return ""
        model = _get_var("GROQ_MODEL") or "llama-3.3-70b-versatile"
        return _call_openai_compat(messages, system, api_key=api_key,
                                   base_url="https://api.groq.com/openai/v1", model=model)
    elif provider == "openai":
        api_key = _get_var("OPENAI_API_KEY")
        if not api_key:
            return ""
        model = _get_var("OPENAI_MODEL") or "gpt-4o"
        base_url = _get_var("OPENAI_BASE_URL") or "https://api.openai.com/v1"
        full_messages = [{"role": "system", "content": system}] + messages
        return _call_groq_raw(full_messages, api_key, base_url, model)
    elif provider == "ollama":
        model = _get_var("OLLAMA_MODEL") or "llama3.2"
        base_url = _get_var("OLLAMA_URL") or "http://localhost:11434/v1"
        return _call_openai_compat(messages, system, api_key="ollama",
                                   base_url=base_url, model=model,
                                   temperature=_OLLAMA_TEMPERATURE)
    else:
        import anthropic  # type: ignore
        api_key = _get_var("ANTHROPIC_API_KEY")
        if not api_key:
            return ""
        client = anthropic.Anthropic(api_key=api_key)
        try:
            resp = client.messages.create(
                model=_get_var("ANTHROPIC_MODEL") or "claude-sonnet-4-6",
                max_tokens=2048,
                system=system,
                messages=messages,
            )
            return resp.content[0].text
        except Exception:
            return ""


def extract_structured_anamnesis(messages: List[Dict[str, str]]) -> Dict[str, Any]:
    """Extract structured anamnesis data from chat history via a separate API call.

    Returns a dict matching the patient_data keys defined in PatientDataHandler,
    or an empty dict if extraction fails.
    """
    import json as _json

    # Build a condensed transcript for extraction (last 40 messages max)
    transcript_lines = []
    for m in messages[-40:]:
        role = "AMDA" if m["role"] == "assistant" else "Пациент"
        # Strip the disclaimer from AMDA messages to save tokens
        content = m["content"]
        if "---\n*" in content:
            content = content[:content.rfind("---\n*")].strip()
        transcript_lines.append(f"{role}: {content}")
    transcript = "\n\n".join(transcript_lines)

    raw = _raw_call(_EXTRACTION_SYSTEM, transcript)
    if not raw:
        return {}

    # Strip markdown fences if the model wrapped JSON anyway
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    try:
        data = _json.loads(raw)
        # Ensure lists are lists and strings are strings
        for list_key in ("chief_complaints", "associated_symptoms_present",
                         "associated_symptoms_absent", "red_flags"):
            if not isinstance(data.get(list_key), list):
                data[list_key] = []
        return data
    except Exception:
        return {}


def analyze_document(
    filename: str,
    content: Optional[str],
    doc_type: str,
) -> Dict[str, Any]:
    """Analyze a single document. Returns a dict with filename, doc_type, analysis_text."""
    if not content or not content.strip():
        analysis_text = (
            f"Содержимое файла `{filename}` не удалось извлечь автоматически "
            f"(формат `{doc_type}` требует ручного анализа или мультимодальной модели)."
        )
        return {"filename": filename, "doc_type": doc_type, "doc_date": None,
                "analysis_text": analysis_text}

    prompt = (
        f"Файл: `{filename}`\nТип файла: `{doc_type}`\n\n"
        f"Содержимое документа:\n\n{content}"
    )
    result_text = _raw_call(_DOCUMENT_ANALYSIS_SYSTEM, prompt)
    if not result_text:
        result_text = f"Не удалось проанализировать документ `{filename}`."

    return {
        "filename": filename,
        "doc_type": doc_type,
        "doc_date": None,
        "analysis_text": result_text,
    }


_COMBINED_ANALYSIS_SYSTEM = """You are a senior medical analyst. You have received structured analyses of multiple medical documents belonging to one patient.

Your task: produce a single generalized clinical summary across ALL documents.

Structure your response as follows:
1. **Key Findings** — the most clinically significant results across all documents (abnormal values, diagnoses, notable trends). Use a bullet list.
2. **Patterns & Correlations** — connections between findings from different documents (e.g., elevated WBC correlates with CRP, imaging findings match lab data).
3. **Overall Clinical Picture** — 3-5 sentences describing the patient's overall health status based on all documents combined.
4. **Points Requiring Attention** — values or findings that warrant urgent or priority follow-up (mark with ⚠️ if critical).

Rules:
- Do NOT repeat per-document breakdowns — only synthesize.
- All parameter names and units must be in English.
- Respond in Russian.
- End with the mandatory disclaimer."""


_DIFFERENTIAL_DIAGNOSIS_SYSTEM = """You are AMDA — AI Medical Diagnostic Assistant performing differential diagnosis.
You have received full patient data: structured anamnesis and medical document analysis results.

Apply ALL 6 mandatory steps from the differential diagnosis protocol:

**Step 1.** Identify the leading symptoms and their characteristics. Compare against classic disease patterns.

**Step 2.** For each diagnosis explicitly state:
- Data that SUPPORTS it (positive findings from anamnesis and documents).
- Data that EXCLUDES it or reduces probability (negative findings, absent expected symptoms).

**Step 3.** Apply "common things are common":
- First consider most prevalent conditions for this patient's age, sex, region, risk factors.
- Rare diagnoses only when supported by strong evidence.

**Step 4.** Build the differential series:
- Top 3 most probable diagnoses.
- Less probable but must-exclude diagnoses.
- Rare / "must not miss" diagnoses.

**Step 5.** Qualitative Bayesian approach:
- Prior probability based on population prevalence + patient risk factors.
- Update based on sensitivity/specificity of symptoms and test results.

**Step 6.** Always separately highlight RED FLAGS if present.

## Required output format (respond in Russian):

### Ведущие симптомы
(2-3 sentences analysing leading symptoms)

### Дифференциальный ряд

| № | Диагноз (МКБ-10) | Вероятность | Уверенность | Ключевое обоснование |
|---|-----------------|-------------|-------------|----------------------|
(5-7 rows, probabilities sum to exactly 100%)

### Красные флаги
(list if any, mark ⚠️ — or write "Не выявлены")

### Резюме
(3-4 sentences: overall clinical picture, most likely diagnosis, recommended next step)

---
Rules:
- 5–7 diagnoses maximum (optimally 5–6)
- ICD-10/ICD-11 codes where possible
- Confidence: низкий / средний / высокий
- Never use alarming or frightening language
- End with the disclaimer: "Эта система является вспомогательным инструментом. Окончательный диагноз и план лечения может поставить только лицензированный врач. Не предпринимайте никаких действий на основании этих рекомендаций без очной консультации со специалистом."
"""

_RECALCULATE_DIAGNOSIS_SYSTEM = """You are AMDA — AI Medical Diagnostic Assistant.
The patient has provided additional information. Recalculate the differential diagnosis probabilities.

Apply the same 6-step protocol. Explicitly explain which probability changed and WHY (what new data caused the change).

Use the same output format:
### Обновлённый дифференциальный ряд
| № | Диагноз (МКБ-10) | Вероятность | Уверенность | Изменение | Обоснование |
(add a column "Изменение": ↑ increased / ↓ decreased / = unchanged)

### Что изменилось и почему
(bullet list: for each changed probability explain the reasoning)

### Резюме
(updated clinical picture)

Rules: same as before. Respond in Russian. End with the disclaimer."""


_TEST_PRIORITIZATION_SYSTEM = """You are AMDA — AI Medical Diagnostic Assistant.
You have the patient's full data and differential diagnosis. Generate a prioritized plan of additional investigations.

## Priority Rules (apply strictly):

**Primary criterion** — the investigation that:
- Rules out the maximum number of suspected diagnoses simultaneously.
- Confirms or refutes the leading diagnosis.
- Reduces the total number of future tests needed (high informativeness + accessibility).

**Secondary criteria** (in order):
1. Urgency — red flags trigger emergency priority.
2. Non-invasiveness and patient safety.
3. Cost and accessibility.
4. Sensitivity/specificity in this specific clinical context.

## Required output format (respond in Russian):

### План дополнительных исследований

Numbered list in descending priority order. For each investigation:

**№. Название исследования** [код, если применимо]
- **Цель:** что подтверждает или исключает
- **Влияние на диагнозы:** какие диагнозы изменятся и как
- **Срочность:** экстренно / в течение 24–48 ч / плановое (до X дней)

After the list — a brief explanation of why investigation #1 is ranked first.

### Итоговое резюме
2-3 sentences: what the plan will clarify and what decision it enables.

Rules:
- List only genuinely necessary investigations (no over-testing)
- Prioritize non-invasive over invasive when informativeness is comparable
- If red flags are present — the first item must address the dangerous diagnosis
- Respond in Russian
- End with the disclaimer: "Эта система является вспомогательным инструментом. Окончательный диагноз и план лечения может поставить только лицензированный врач. Не предпринимайте никаких действий на основании этих рекомендаций без очной консультации со специалистом."
"""


_FINAL_DIAGNOSIS_SYSTEM = """You are AMDA — AI Medical Diagnostic Assistant.
At least one diagnosis has reached ≥ 90% probability. Generate the final diagnosis report.

## Mandatory output (respond in Russian):

### Окончательный диагноз

**Диагноз:** [название] ([код МКБ-10/МКБ-11])
**Вероятность:** X%

**Ключевые подтверждающие данные:**
- Симптомы: ...
- Данные обследований: ...
- Логика постановки: ...

### Дифференциальный ряд (исключённые диагнозы)

| Диагноз | Вероятность | Причина исключения |
|---------|-------------|-------------------|

### Рекомендации

**Специалист и сроки:** [к какому врачу, срочность: экстренно / 1–3 дня / плановый]

**Предлагаемое лечение (общие контуры):**
- [общие принципы терапии согласно клиническим руководствам, без конкретных доз]

**Дополнительные меры:**
- [госпитализация / диета / ограничение активности / иное]

**Контрольные показатели:**
- [что контролировать и когда повторить оценку]

---
Rules:
- No specific drug dosages — general therapy outlines only
- Never use alarming language
- Always recommend in-person physician consultation
- End with the disclaimer: "Эта система является вспомогательным инструментом. Окончательный диагноз и план лечения может поставить только лицензированный врач. Не предпринимайте никаких действий на основании этих рекомендаций без очной консультации со специалистом."
"""


def extract_max_probability(diagnosis_text: str) -> int:
    """Parse the diagnosis text and return the highest probability percentage found."""
    import re
    matches = re.findall(r"\b(\d{1,3})\s*%", diagnosis_text)
    if not matches:
        return 0
    return max(int(m) for m in matches if int(m) <= 100)


def generate_final_diagnosis(patient_context: str, diagnosis_text: str) -> str:
    """Generate final diagnosis report when a diagnosis reaches ≥ 90%."""
    combined = (
        f"## Данные пациента\n\n{patient_context}\n\n"
        f"## Дифференциальный диагноз (финальный)\n\n{diagnosis_text}"
    )
    return _raw_call(_FINAL_DIAGNOSIS_SYSTEM, combined)


def generate_investigation_plan(patient_context: str, diagnosis_text: str) -> str:
    """Generate prioritized investigation plan based on patient data and differential diagnosis."""
    combined = (
        f"## Данные пациента\n\n{patient_context}\n\n"
        f"## Дифференциальный диагноз\n\n{diagnosis_text}"
    )
    return _raw_call(_TEST_PRIORITIZATION_SYSTEM, combined)


def generate_differential_diagnosis(patient_context: str) -> str:
    """Generate initial differential diagnosis from full patient context (current-patient.md)."""
    return _raw_call(_DIFFERENTIAL_DIAGNOSIS_SYSTEM, patient_context)


def recalculate_differential_diagnosis(
    new_info: str,
    patient_context: str,
    previous_diagnosis: str,
) -> str:
    """Recalculate diagnosis probabilities after new patient information."""
    combined = (
        f"## Текущие данные пациента\n\n{patient_context}\n\n"
        f"## Предыдущий дифференциальный ряд\n\n{previous_diagnosis}\n\n"
        f"## Новая информация от пациента\n\n{new_info}"
    )
    return _raw_call(_RECALCULATE_DIAGNOSIS_SYSTEM, combined)


def generate_combined_analysis(results: List[Dict[str, Any]]) -> str:
    """Generate a single generalized clinical summary across all analyzed documents."""
    if not results:
        return ""

    # Build a condensed input: filename + analysis text for each doc
    parts = []
    for r in results:
        source = " (from cache)" if r.get("from_cache") else ""
        parts.append(f"### Document: {r['filename']}{source}\n{r.get('analysis_text', '')}")
    combined_input = "\n\n---\n\n".join(parts)

    result = _raw_call(_COMBINED_ANALYSIS_SYSTEM, combined_input)
    return result or "Не удалось сформировать общий анализ документов."


def get_initial_greeting() -> str:
    """Return the initial greeting message from AMDA."""
    return (
        "Здравствуйте! Я **AMDA** — AI-ассистент медицинской диагностики.\n\n"
        "Я помогу вам системно описать ваши жалобы, чтобы эту информацию можно было "
        "грамотно представить врачу.\n\n"
        "Для начала расскажите:\n"
        "- **Что вас беспокоит? Какие у вас основные симптомы или жалобы?**\n"
        "- **Когда они впервые появились?**\n\n"
        "Не торопитесь — я буду задавать уточняющие вопросы по одному-два за раз.\n\n"
        "---\n"
        "*Эта система является вспомогательным инструментом. Окончательный диагноз и план "
        "лечения может поставить только лицензированный врач. Не предпринимайте никаких "
        "действий на основании этих рекомендаций без очной консультации со специалистом.*"
    )
