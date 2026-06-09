"""
app.py
------
AI Resume Evaluator — Flask backend
Internee.pk Task 2

Routes:
  GET  /         → Upload form
  POST /upload   → File processing + AI analysis → JSON response
"""

import os
import tempfile
from flask import Flask, request, jsonify, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from resume_analyzer import extract_text, analyze_resume

load_dotenv()

app = Flask(__name__)

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS  = {".pdf", ".docx"}

# ─── Helpers ───────────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    # Serve index.html from the same folder as app.py
    return send_from_directory(os.path.dirname(os.path.abspath(__file__)), "index.html")


@app.route("/upload", methods=["POST"])
def upload():
    """
    Handle resume upload:
      1. Validate file (type + size)
      2. Write to secure tempfile
      3. Extract text
      4. Analyze with Gemini → structured JSON
      5. Return JSON to frontend

    Why tempfile?
    - Random OS-assigned path → no path traversal risk
    - Auto-cleanup in finally block → no disk accumulation
    - Concurrent uploads get separate files → no collisions
    """
    if "resume" not in request.files:
        return jsonify({"error": "No file uploaded."}), 400

    file = request.files["resume"]

    if not file.filename:
        return jsonify({"error": "Empty filename."}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "Only PDF and DOCX files are accepted."}), 400

    file_bytes = file.read()
    if len(file_bytes) > MAX_FILE_SIZE_BYTES:
        return jsonify({"error": "File exceeds 5 MB limit."}), 413

    ext      = os.path.splitext(secure_filename(file.filename))[1].lower()
    tmp_path = None

    try:
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp_path = tmp.name
            tmp.write(file_bytes)

        # Step 1: Extract text
        resume_text = extract_text(tmp_path)

        # Step 2: Guard — no API key means dev mode
        if not os.getenv("OPENAI_API_KEY"):
            return jsonify({
                "overall_score": 0,
                "summary": "[DEV MODE] No API key set. Text extraction succeeded.",
                "structure_score": 0, "structure_feedback": "No key set.",
                "content_score": 0,   "content_feedback": "No key set.",
                "skills_found": [], "skills_missing": [],
                "ats_tips": [f"Extracted {len(resume_text)} characters successfully."],
            })

        # Step 3: AI analysis → structured dict
        result = analyze_resume(resume_text, filename=file.filename)
        return jsonify(result)

    except ValueError as e:
        return jsonify({"error": str(e)}), 422
    except Exception as e:
        app.logger.error(f"Upload error: {e}")
        return jsonify({"error": "Processing failed. Please try again."}), 500
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)


# ─── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("━" * 52)
    print("  AI Resume Evaluator — Internee.pk Task 2")
    print("  http://127.0.0.1:5000")
    print("━" * 52)
    app.run(debug=True, port=5000)