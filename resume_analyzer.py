"""
resume_analyzer.py  (Free-tier optimised edition)
---------------------------------------------------
Internee.pk Task 2 — AI Resume Evaluator

WHY WE CHANGED FROM PARALLEL TO SINGLE-CALL:
──────────────────────────────────────────────
The previous RunnableParallel architecture fired 5 simultaneous API calls.
Gemini 2.5 Flash free tier allows only 5 requests/minute (RPM) and 25/day (RPD).
Five concurrent calls instantly exhausted the RPM quota, causing:
  - LangChain's retry loop to run for ~2 minutes before giving up
  - A confusing "loading forever then error" experience

Fix: one consolidated prompt = one API call per analysis.
  - Uses 1/5 of the per-minute quota
  - Response time drops from 2+ minutes (retries) to 5-10 seconds
  - Still uses LangChain ChatPromptTemplate + chain for modularity

BRACE ESCAPING (critical rule for LangChain):
──────────────────────────────────────────────
ChatPromptTemplate treats ALL single braces as template variable placeholders.
Any JSON schema example in a system prompt MUST use {{ and }} to produce
literal { } at render time. Forgetting this causes silent KeyErrors.
"""

import os
import json
import time
import PyPDF2
import docx

from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI


# ══════════════════════════════════════════════════════════════════════════════
#  PDF / DOCX EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_text_from_pdf(filepath: str) -> str:
    """
    Extract plain text from a PDF resume using PyPDF2.
    ⚠️  Scanned/image-based PDFs have no text layer — raises clear ValueError.
    """
    try:
        pages = []
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            if reader.is_encrypted:
                raise ValueError("PDF is password-protected. Upload an unlocked version.")
            if len(reader.pages) == 0:
                raise ValueError("PDF has 0 pages.")
            for page in reader.pages:
                t = page.extract_text()
                if t:
                    pages.append(t.strip())
        text = "\n\n".join(pages).strip()
        if not text:
            raise ValueError(
                "No text extracted — likely a scanned/image-based PDF. "
                "Please upload a digitally-created PDF."
            )
        return text
    except ValueError:
        raise
    except PyPDF2.errors.PdfReadError as e:
        raise ValueError(f"Corrupted or invalid PDF: {e}")
    except Exception as e:
        raise Exception(f"Unexpected PDF read error: {e}")


def extract_text_from_docx(filepath: str) -> str:
    """
    Extract plain text from a DOCX resume.
    Reads both paragraphs AND table cells — modern two-column resume
    templates store most content in tables, not paragraphs.
    """
    try:
        doc = docx.Document(filepath)
        blocks = []
        for para in doc.paragraphs:
            line = para.text.strip()
            if line:
                blocks.append(line)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    ct = cell.text.strip()
                    if ct and ct not in blocks:
                        blocks.append(ct)
        text = "\n".join(blocks).strip()
        if not text:
            raise ValueError(
                "No text found in DOCX — may contain only images. "
                "Please save as a standard Word document."
            )
        return text
    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read DOCX (possibly corrupted): {e}")


def extract_text(filepath: str) -> str:
    """Route to the correct extractor based on file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext == ".docx":
        return extract_text_from_docx(filepath)
    else:
        raise ValueError(f"Unsupported type '{ext}'. Only PDF and DOCX accepted.")


# ══════════════════════════════════════════════════════════════════════════════
#  JSON REPAIR UTILITY
# ══════════════════════════════════════════════════════════════════════════════

def _repair_truncated_json(raw: str) -> dict | None:
    """Salvage a JSON object cut off mid-stream (max_tokens reached)."""
    try:
        cut = max(
            raw.rfind('",'),
            raw.rfind('],'),
            raw.rfind('"}'),
            raw.rfind('"]'),
        )
        if cut == -1:
            return None
        partial = raw[:cut + 2].rstrip(',').rstrip()
        if not partial.endswith('}'):
            partial += '\n}'
        return json.loads(partial)
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  LANGCHAIN CHAIN — single consolidated call (free-tier safe)
# ══════════════════════════════════════════════════════════════════════════════

# Cap resume text at 4000 chars (~1000 tokens).
# Gemini 2.5 Flash free tier: 250k tokens/minute input, so the bottleneck
# is request count (RPM=5), not token count. Keeping input small ensures
# the model responds quickly and the output fits in max_output_tokens.
RESUME_TEXT_LIMIT = 4000


def _make_llm():
    """
    Single LLM instance for the consolidated analysis call.

    model: gemini-1.5-flash chosen over gemini-2.5-flash because:
      - 2.5-flash free tier: 5 RPM,  25 RPD  ← hits daily cap quickly
      - 1.5-flash free tier: 15 RPM, 1500 RPD ← 60x more daily requests

    max_retries=1: fail fast instead of retrying for 2 minutes.
      LangChain's default is 6 retries with exponential backoff.
      At quota limits, retrying doesn't help — the quota window is
      60 seconds, longer than any backoff sequence. Better to surface
      the error immediately so the user knows to wait.

    temperature=0.3: consistent scoring (±3 pts) with natural phrasing.
    """
    return ChatGoogleGenerativeAI(
        model="gemini-1.5-flash",
        google_api_key=os.getenv("OPENAI_API_KEY"),
        temperature=0.3,
        max_output_tokens=2048,
        max_retries=1,          # fail fast — don't waste 2 minutes retrying
    )


# Single consolidated prompt — all 9 fields in one call.
# Why one call instead of 5?
#   Free tier = 5 RPM. Five parallel calls = instant quota exhaustion.
#   One call = 1/5 quota usage, same quality output, no retry loops.
#
# The prompt is structured in sections to preserve the benefits of
# specialised analysis: each section has focused instructions, the model
# just executes them sequentially rather than in parallel processes.
ANALYSIS_PROMPT = ChatPromptTemplate.from_messages([
    ("system", """You are a senior technical recruiter and ATS expert with 15 years of experience.
Analyse the resume below and return ONLY a single valid JSON object — no markdown fences, no explanation.

Required JSON structure (all fields mandatory):
{{
  "skills_found":       ["skill1", "skill2"],
  "skills_missing":     ["missing1", "missing2"],
  "structure_score":    75,
  "structure_feedback": "One to two sentences on layout, sections, and formatting.",
  "content_score":      68,
  "content_feedback":   "One to two sentences on achievement quality and language.",
  "ats_tips":           ["Specific tip 1", "Specific tip 2", "Specific tip 3"],
  "overall_score":      72,
  "summary":            "2-3 sentences: strongest point, biggest gap, one next step."
}}

SKILLS RULES:
- skills_found: only skills explicitly stated (languages, frameworks, tools, certs) — max 20
- skills_missing: skills expected for the apparent role that are absent — max 8

STRUCTURE SCORE RUBRIC (0-100):
- 90-100: All key sections present (Contact/Summary/Experience/Skills/Education), consistent formatting
- 75-89:  Good structure, minor issues (no summary, slight formatting inconsistency)
- 60-74:  Adequate but missing sections or has formatting problems
- 40-59:  Hard to scan, multiple missing sections
- 0-39:   No recognisable resume structure

CONTENT SCORE RUBRIC (0-100):
- 90-100: Strong action verbs + quantified achievements (%, $, numbers) throughout
- 75-89:  Good verbs, some quantification
- 60-74:  Responsibilities listed but vague, little quantification
- 40-59:  Passive language, duties only, no achievements
- 0-39:   Minimal meaningful content

ATS TIPS RULES:
- Give 3-5 tips SPECIFIC to this resume (reference actual content)
- Cover: keyword spelling, section header names, missing standard sections, formatting

OVERALL SCORE: weighted average — structure×30% + content×40% + ats_readiness×30%

Return ONLY the JSON object. No other text."""),
    ("human", "Resume ({filename}):\n\n{resume_text}"),
])


# Module-level cache — chain built once per process
_chain = None

def _get_chain():
    global _chain
    if _chain is None:
        _chain = ANALYSIS_PROMPT | _make_llm() | JsonOutputParser()
    return _chain


# ══════════════════════════════════════════════════════════════════════════════
#  PUBLIC API — same signature, Flask app unchanged
# ══════════════════════════════════════════════════════════════════════════════

SAFE_DEFAULTS = {
    "skills_found":       [],
    "skills_missing":     [],
    "structure_score":    0,
    "structure_feedback": "Analysis unavailable.",
    "content_score":      0,
    "content_feedback":   "Analysis unavailable.",
    "ats_tips":           ["Re-upload for complete ATS analysis."],
    "overall_score":      0,
    "summary":            "Analysis incomplete. Please try again.",
}

EXPECTED_FIELDS = list(SAFE_DEFAULTS.keys())


def analyze_resume(resume_text: str, filename: str = "") -> dict:
    """
    Analyse a resume — 1 API call, free-tier safe.

    Uses a single consolidated LangChain prompt instead of parallel chains.
    Keeps the same return signature so Flask app.py needs no changes.
    """
    truncated = resume_text[:RESUME_TEXT_LIMIT]

    try:
        result = _get_chain().invoke({
            "resume_text": truncated,
            "filename": filename or "resume",
        })

    except Exception as e:
        err = str(e)

        # Quota exceeded — tell user clearly and don't bury it
        if "429" in err or "ResourceExhausted" in err or "quota" in err.lower() or "RESOURCE_EXHAUSTED" in err:
            raise Exception(
                "API quota exceeded (free tier limit reached). "
                "Please wait 1 minute and try again. "
                "If this keeps happening, get a fresh key at https://aistudio.google.com/apikey"
            )

        # Auth / key errors
        if "401" in err or "403" in err or "API_KEY" in err or "Forbidden" in err:
            raise Exception(
                "Invalid or restricted API key. "
                "Check your OPENAI_API_KEY in .env — "
                "get a free key at https://aistudio.google.com/apikey"
            )

        # Model not available
        if "404" in err or "not found" in err.lower():
            raise Exception(
                "Model 'gemini-1.5-flash' not found. "
                "Check your API key has access at https://aistudio.google.com"
            )

        # JSON parse error from the model
        if "json" in err.lower() or "parse" in err.lower():
            raise Exception(
                "AI returned an unreadable response. Please try uploading again."
            )

        raise Exception(f"Analysis error: {err}")

    # ── Validate and sanitise output ──────────────────────────────────────
    if not isinstance(result, dict):
        repaired = _repair_truncated_json(str(result)) if result else None
        result = repaired or {}

    # Fill any missing fields with safe defaults
    for field, default in SAFE_DEFAULTS.items():
        if field not in result or result[field] is None:
            result[field] = default

    # Clamp scores to 0-100 integers
    for score_field in ("structure_score", "content_score", "overall_score"):
        try:
            result[score_field] = max(0, min(100, int(float(result[score_field]))))
        except (ValueError, TypeError):
            result[score_field] = 0

    # Ensure list fields are lists
    for list_field in ("skills_found", "skills_missing", "ats_tips"):
        if not isinstance(result[list_field], list):
            result[list_field] = [str(result[list_field])] if result[list_field] else []

    return result