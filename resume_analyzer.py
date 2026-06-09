"""
resume_analyzer.py
------------------
Handles two responsibilities:
  1. Text extraction from PDF and DOCX files
  2. AI analysis via Gemini (OpenAI-compatible endpoint) → returns structured JSON

Keeping extraction and analysis in one module keeps imports clean in app.py,
while the functions themselves stay single-responsibility.
"""

import os
import json
import PyPDF2
import docx
from openai import OpenAI


# ─── AI Client (lazy init) ─────────────────────────────────────────────────────

_client = None

def _get_client() -> OpenAI:
    """
    Lazy-initialize the Gemini client using OpenAI SDK compatibility layer.
    Created once and reused — avoids re-authenticating on every request.
    """
    global _client
    if _client is None:
        _client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            # Gemini's OpenAI-compatible endpoint — drop-in replacement,
            # no other code changes needed
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
        )
    return _client


# ─── PDF Extraction ────────────────────────────────────────────────────────────

def extract_text_from_pdf(filepath: str) -> str:
    """
    Extract plain text from a PDF resume using PyPDF2.

    How it works:
    - PyPDF2 reads the PDF's internal text layer (vector text objects).
    - It iterates each page and calls extract_text(), returning raw strings.
    - Pages are joined with double newlines to preserve visual section breaks.

    ⚠️  Scanned / image-based PDFs:
    - Scanned PDFs contain images, NOT a text layer. PyPDF2 returns "" for
      those pages. We detect this and raise a clear ValueError — the user
      needs to upload a digitally-created PDF, not a scan.
    """
    try:
        text_pages = []
        with open(filepath, "rb") as f:
            reader = PyPDF2.PdfReader(f)

            if reader.is_encrypted:
                raise ValueError("PDF is password-protected. Upload an unlocked version.")
            if len(reader.pages) == 0:
                raise ValueError("The PDF has 0 pages.")

            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_pages.append(page_text.strip())

        full_text = "\n\n".join(text_pages).strip()
        if not full_text:
            raise ValueError(
                "No text found in PDF. It may be a scanned/image-based document. "
                "Please upload a PDF created digitally (not a scan)."
            )
        return full_text

    except ValueError:
        raise
    except PyPDF2.errors.PdfReadError as e:
        raise ValueError(f"PDF appears corrupted or invalid: {e}")
    except Exception as e:
        raise Exception(f"Unexpected error reading PDF: {e}")


# ─── DOCX Extraction ───────────────────────────────────────────────────────────

def extract_text_from_docx(filepath: str) -> str:
    """
    Extract plain text from a DOCX resume using python-docx.

    How it works:
    - python-docx models a Word document as: Document → Paragraphs → Runs
    - We collect paragraph text AND table cell text separately.
    - Tables matter: modern resume templates (e.g. two-column layouts) store
      most content in tables, not paragraphs. Skipping them loses half the resume.

    ⚠️  Scanned / image-based DOCX:
    - Some DOCX files contain only an embedded image of a resume. python-docx
      returns empty paragraphs in that case. We detect and raise a clear error.
    """
    try:
        doc = docx.Document(filepath)
        text_blocks = []

        # Regular paragraphs: headings, body text, bullet points
        for para in doc.paragraphs:
            line = para.text.strip()
            if line:
                text_blocks.append(line)

        # Tables: two-column resume layouts live here
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    cell_text = cell.text.strip()
                    if cell_text and cell_text not in text_blocks:
                        text_blocks.append(cell_text)

        full_text = "\n".join(text_blocks).strip()
        if not full_text:
            raise ValueError(
                "No text found in DOCX. It may contain only images. "
                "Please save as a standard Word document."
            )
        return full_text

    except ValueError:
        raise
    except Exception as e:
        raise ValueError(f"Could not read DOCX (possibly corrupted): {e}")


# ─── Unified Extraction Entry Point ────────────────────────────────────────────

def extract_text(filepath: str) -> str:
    """Route to the right extractor based on file extension."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(filepath)
    elif ext == ".docx":
        return extract_text_from_docx(filepath)
    else:
        raise ValueError(f"Unsupported file type '{ext}'. Only PDF and DOCX accepted.")


# ─── AI Analysis ───────────────────────────────────────────────────────────────

# The JSON schema we want back — documented here so the prompt and
# the frontend renderer stay in sync. If you add a field, update both.
EXPECTED_FIELDS = [
    "skills_found",       # list[str]  — skills detected in the resume
    "skills_missing",     # list[str]  — important skills absent for the role
    "structure_score",    # int 0-100  — layout, sections, readability
    "structure_feedback", # str        — explanation of the structure score
    "content_score",      # int 0-100  — quality of experience descriptions
    "content_feedback",   # str        — explanation of the content score
    "ats_tips",           # list[str]  — 3-5 Applicant Tracking System tips
    "overall_score",      # int 0-100  — holistic resume quality
    "summary",            # str        — 2-3 sentence executive summary
]

# ── Why temperature 0.3? ──────────────────────────────────────────────────────
# Temperature controls randomness in the model's output:
#   0.0 = fully deterministic (same input → same output every time)
#   1.0 = creative/varied (good for stories, bad for scoring)
#
# For resume scoring we want:
#   ✅ Consistent scores (0.3 gives <5 point variance across runs)
#   ✅ Factual skill detection (not "creative" invention of skills)
#   ✅ Reliable JSON structure (low temp = less likely to go off-script)
#   ❌ NOT creative writing — we want analysis, not flair
#
# 0.3 is the sweet spot: consistent enough for scoring, flexible enough
# to phrase feedback naturally rather than robotically.
# ─────────────────────────────────────────────────────────────────────────────

# ── Token limit consideration ─────────────────────────────────────────────────
# gemini-2.5-flash has a large context window, but:
#   - We only need the first ~8000 chars for a complete resume analysis
#   - Sending the full text of a 10-page portfolio doc wastes tokens & money
#   - 8000 chars ≈ 2000 tokens input, well under any free-tier limit
#   - The most important resume info (contact, skills, top roles) is always first
# ─────────────────────────────────────────────────────────────────────────────

RESUME_TEXT_LIMIT = 8000  # characters sent to the API

def _repair_truncated_json(raw: str) -> dict | None:
    """
    Attempt to recover a truncated JSON object from the AI.

    When max_tokens cuts the response mid-string, the JSON is invalid.
    We find the last successfully completed key-value pair and close
    the object, filling any missing required fields with safe defaults.
    This is better than crashing — the user still gets partial results.
    """
    try:
        # Remove any trailing partial field — find last complete value
        # A complete value ends with: " (string), ] (array), or a digit
        cut = max(
            raw.rfind('",'),   # end of a string value followed by comma
            raw.rfind('],'),   # end of an array followed by comma
            raw.rfind('"}'),   # end of string, closing object
            raw.rfind('"]'),   # end of string inside array
        )
        if cut == -1:
            return None

        # Slice to last safe point and close the JSON object
        partial = raw[:cut + 2].rstrip(',').rstrip()
        if not partial.endswith('}'):
            partial += '\n}'

        result = json.loads(partial)

        # Fill in any fields that got cut off with safe defaults
        defaults = {
            "skills_found":        [],
            "skills_missing":      [],
            "structure_score":     0,
            "structure_feedback":  "Analysis was cut off — please re-upload.",
            "content_score":       0,
            "content_feedback":    "Analysis was cut off — please re-upload.",
            "ats_tips":            ["Re-upload your resume for complete ATS tips."],
            "overall_score":       0,
            "summary":             "Analysis was incomplete due to response length. Please try again.",
        }
        for key, default in defaults.items():
            if key not in result:
                result[key] = default

        return result

    except Exception:
        return None


def analyze_resume(resume_text: str, filename: str = "") -> dict:
    """
    Send extracted resume text to Gemini and return structured analysis as a dict.

    Prompt engineering strategy:
    ─────────────────────────────
    1. ROLE PRIMING: "You are an expert ATS system and senior technical recruiter..."
       → Anchors the model's perspective. Models perform better when given a clear role.

    2. STRICT OUTPUT CONTRACT: We tell the model EXACTLY what JSON to return,
       with field names, types, and value ranges. This replaces vague instructions
       like "give me feedback" with a machine-readable specification.

    3. JSON-ONLY instruction + response_format enforcement: Double-lock.
       The system prompt says "output ONLY valid JSON", and we pass
       response_format={"type": "json_object"} to the API. Either alone can fail;
       together they make malformed output extremely rare.

    4. CONCRETE SCORING RUBRIC: We define what 0-100 means for each score
       instead of letting the model interpret it. This prevents grade inflation
       (everyone gets 90+) and makes scores meaningful.

    5. EXAMPLES IN SCHEMA: The prompt shows sample values for each field,
       so the model knows "skills_found" should be ["Python", "React"] not
       a paragraph of text.

    Args:
        resume_text: Raw extracted text from the resume file.
        filename:    Original filename (used for context in the prompt).

    Returns:
        dict with all EXPECTED_FIELDS populated.

    Raises:
        ValueError: If API returns invalid/incomplete JSON.
        Exception:  For API-level errors (quota, network, auth).
    """

    # Truncate to limit — most critical resume info is at the top
    truncated_text = resume_text[:RESUME_TEXT_LIMIT]
    truncation_note = (
        f"\n[Note: Resume truncated to first {RESUME_TEXT_LIMIT} chars for analysis]"
        if len(resume_text) > RESUME_TEXT_LIMIT else ""
    )

    system_prompt = """You are an expert ATS (Applicant Tracking System) analyzer and senior technical recruiter with 15+ years of experience evaluating resumes for software engineering, data science, and tech roles.

Your task is to analyze the resume provided and return ONLY a valid JSON object — no preamble, no explanation, no markdown code fences. Just raw JSON.

Return this exact JSON structure:

{
  "skills_found": ["list", "of", "skills", "detected", "in", "resume"],
  "skills_missing": ["important", "skills", "absent", "for", "typical", "tech", "roles"],
  "structure_score": 75,
  "structure_feedback": "One to two sentences explaining the structure score.",
  "content_score": 68,
  "content_feedback": "One to two sentences explaining the content score.",
  "ats_tips": ["Tip 1 for ATS optimization", "Tip 2", "Tip 3", "Tip 4"],
  "overall_score": 72,
  "summary": "2-3 sentence executive summary of the resume's overall quality and suitability."
}

SCORING RUBRIC (use this consistently):
- 90-100: Exceptional. Could go to top FAANG companies as-is.
- 75-89:  Strong. Competitive for most roles with minor tweaks.
- 60-74:  Average. Functional but needs clear improvements.
- 40-59:  Weak. Several significant issues to fix.
- 0-39:   Poor. Major restructuring needed.

RULES:
- skills_found: List ONLY skills explicitly mentioned (languages, frameworks, tools, certs). Max 20.
- skills_missing: List skills common in job postings for the detected role that are absent. Max 10.
- ats_tips: Give 3-5 SPECIFIC tips, not generic advice. Reference the actual resume content.
- All scores must be integers between 0 and 100.
- summary: Be honest and constructive. Mention the strongest selling point and the biggest gap.
- Output ONLY the JSON object. No other text."""

    user_message = f"""Analyze this resume{f' ({filename})' if filename else ''}:{truncation_note}

{truncated_text}"""

    try:
        response = _get_client().chat.completions.create(
            model="gemini-2.5-flash",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            temperature=0.3,              # See temperature explanation above
            max_tokens=4096,              # Enough for full JSON + all lists
            response_format={"type": "json_object"},  # Force valid JSON output
        )

        raw = response.choices[0].message.content.strip()

        # ── Parse and validate ──────────────────────────────────────────────
        # Even with json_object mode, we validate the shape ourselves.
        # The API guarantees valid JSON syntax but NOT that all our fields exist.
        try:
            result = json.loads(raw)
        except json.JSONDecodeError:
            # The model was cut off mid-JSON (max_tokens reached).
            # We attempt to salvage it by truncating to the last complete field.
            # Strategy: find the last comma at the top level and close the object.
            repaired = _repair_truncated_json(raw)
            if repaired:
                result = repaired
            else:
                raise ValueError(
                    "AI response was cut off and could not be repaired. "
                    "Please try uploading again."
                )

        # Check all expected fields are present
        missing_fields = [f for f in EXPECTED_FIELDS if f not in result]
        if missing_fields:
            raise ValueError(
                f"AI response missing fields: {missing_fields}. "
                f"Raw response: {raw[:300]}"
            )

        # Coerce scores to int (model occasionally returns floats like 72.5)
        for score_field in ("structure_score", "content_score", "overall_score"):
            result[score_field] = max(0, min(100, int(result[score_field])))

        # Ensure list fields are actually lists
        for list_field in ("skills_found", "skills_missing", "ats_tips"):
            if not isinstance(result[list_field], list):
                result[list_field] = [str(result[list_field])]

        return result

    except ValueError:
        raise
    except Exception as e:
        # API-level errors: quota exceeded, network timeout, auth failure, etc.
        raise Exception(f"Gemini API error: {e}")