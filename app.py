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
from flask import Flask, request, jsonify, render_template_string
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from resume_analyzer import extract_text, analyze_resume

load_dotenv()

app = Flask(__name__)

MAX_FILE_SIZE_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS  = {".pdf", ".docx"}

# ─── HTML Template ─────────────────────────────────────────────────────────────

HTML_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>AI Resume Evaluator</title>
  <link href="https://fonts.googleapis.com/css2?family=Syne:wght@400;700;800&family=DM+Sans:ital,wght@0,300;0,400;0,500;1,400&display=swap" rel="stylesheet"/>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    :root {
      --bg:        #080910;
      --surface:   #0f1016;
      --surface2:  #14151e;
      --border:    #1c1e2b;
      --border2:   #252838;
      --accent:    #7c6aff;
      --accent-g:  #a78bfa;
      --green:     #22d3a0;
      --yellow:    #f59e0b;
      --red:       #f43f5e;
      --text:      #e2e4f0;
      --muted:     #5a5d78;
      --radius:    14px;
      --radius-sm: 8px;
    }

    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'DM Sans', sans-serif;
      min-height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      padding: 56px 20px 100px;
    }

    /* ── Header ── */
    .eyebrow {
      font-family: 'Syne', sans-serif;
      font-size: 10.5px;
      font-weight: 700;
      letter-spacing: 3.5px;
      text-transform: uppercase;
      color: var(--accent-g);
      border: 1px solid rgba(167,139,250,0.3);
      border-radius: 100px;
      padding: 5px 16px;
      margin-bottom: 22px;
    }

    h1 {
      font-family: 'Syne', sans-serif;
      font-size: clamp(2.1rem, 5vw, 3.4rem);
      font-weight: 800;
      line-height: 1.08;
      text-align: center;
      margin-bottom: 14px;
      background: linear-gradient(135deg, #e2e4f0 30%, var(--accent-g));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }

    .subtitle {
      color: var(--muted);
      font-size: 1rem;
      text-align: center;
      max-width: 400px;
      line-height: 1.6;
      margin-bottom: 44px;
    }

    /* ── Upload card ── */
    .upload-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 36px;
      width: 100%;
      max-width: 540px;
    }

    .drop-zone {
      border: 2px dashed var(--border2);
      border-radius: var(--radius-sm);
      padding: 38px 24px;
      text-align: center;
      cursor: pointer;
      transition: border-color .2s, background .2s;
      position: relative;
      margin-bottom: 20px;
    }

    .drop-zone:hover, .drop-zone.over {
      border-color: var(--accent);
      background: rgba(124,106,255,.05);
    }

    .drop-zone input[type="file"] {
      position: absolute; inset: 0;
      opacity: 0; cursor: pointer;
      width: 100%; height: 100%;
    }

    .drop-icon { font-size: 2.2rem; margin-bottom: 10px; }

    .drop-label {
      font-family: 'Syne', sans-serif;
      font-weight: 700; font-size: .9rem;
      margin-bottom: 5px;
    }

    .drop-hint { font-size: .78rem; color: var(--muted); }

    .file-chosen {
      font-size: .82rem; color: var(--accent-g);
      margin-top: 10px; font-weight: 500;
    }

    .btn-analyze {
      width: 100%;
      background: linear-gradient(135deg, var(--accent), var(--accent-g));
      color: #fff;
      font-family: 'Syne', sans-serif;
      font-weight: 800; font-size: .95rem;
      letter-spacing: .5px;
      border: none; border-radius: var(--radius-sm);
      padding: 15px; cursor: pointer;
      transition: opacity .2s, transform .1s;
      box-shadow: 0 4px 24px rgba(124,106,255,.25);
    }

    .btn-analyze:hover  { opacity: .88; transform: translateY(-1px); }
    .btn-analyze:active { transform: translateY(0); }
    .btn-analyze:disabled { opacity: .35; cursor: not-allowed; transform: none; box-shadow: none; }

    /* ── Spinner ── */
    .spinner {
      display: inline-block; width: 18px; height: 18px;
      border: 2px solid rgba(255,255,255,.2);
      border-top-color: #fff;
      border-radius: 50%;
      animation: spin .65s linear infinite;
      vertical-align: middle; margin-right: 8px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }

    /* ── Results wrapper ── */
    #results {
      width: 100%; max-width: 860px;
      margin-top: 40px; display: none;
    }

    /* ── Overall score hero ── */
    .score-hero {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 36px 40px;
      display: flex;
      align-items: center;
      gap: 36px;
      margin-bottom: 20px;
      flex-wrap: wrap;
    }

    .score-ring {
      width: 110px; height: 110px; flex-shrink: 0;
      position: relative;
    }

    .score-ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }

    .score-ring-text {
      position: absolute; inset: 0;
      display: flex; flex-direction: column;
      align-items: center; justify-content: center;
    }

    .score-ring-num {
      font-family: 'Syne', sans-serif;
      font-weight: 800; font-size: 1.9rem;
      line-height: 1;
    }

    .score-ring-label {
      font-size: .65rem; color: var(--muted);
      text-transform: uppercase; letter-spacing: 1px;
      margin-top: 3px;
    }

    .score-hero-text h2 {
      font-family: 'Syne', sans-serif;
      font-weight: 800; font-size: 1.25rem;
      margin-bottom: 8px;
    }

    .score-hero-text p {
      color: #9496b0; font-size: .9rem;
      line-height: 1.65; max-width: 500px;
    }

    /* ── Score grid ── */
    .scores-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
      margin-bottom: 20px;
    }

    @media (max-width: 600px) { .scores-grid { grid-template-columns: 1fr; } }

    .score-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
    }

    .score-card-header {
      display: flex; align-items: center;
      justify-content: space-between;
      margin-bottom: 14px;
    }

    .score-card-title {
      font-family: 'Syne', sans-serif;
      font-weight: 700; font-size: .82rem;
      text-transform: uppercase; letter-spacing: 1px;
      color: var(--muted);
    }

    .score-badge {
      font-family: 'Syne', sans-serif;
      font-weight: 800; font-size: 1.4rem;
    }

    .score-bar-track {
      height: 6px; background: var(--border2);
      border-radius: 100px; margin-bottom: 12px;
      overflow: hidden;
    }

    .score-bar-fill {
      height: 100%; border-radius: 100px;
      transition: width .8s cubic-bezier(.16,1,.3,1);
    }

    .score-card-feedback {
      font-size: .85rem; color: #8082a0; line-height: 1.6;
    }

    /* Score colors */
    .c-green  { color: var(--green); }
    .c-yellow { color: var(--yellow); }
    .c-red    { color: var(--red); }

    .bg-green  { background: var(--green); }
    .bg-yellow { background: var(--yellow); }
    .bg-red    { background: var(--red); }

    /* ── Skills + Tips grid ── */
    .info-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 16px;
      margin-bottom: 20px;
    }

    @media (max-width: 780px) { .info-grid { grid-template-columns: 1fr 1fr; } }
    @media (max-width: 500px) { .info-grid { grid-template-columns: 1fr; } }

    .info-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 24px;
    }

    .info-card-title {
      font-family: 'Syne', sans-serif;
      font-weight: 700; font-size: .78rem;
      text-transform: uppercase; letter-spacing: 1.2px;
      color: var(--muted);
      margin-bottom: 14px;
      display: flex; align-items: center; gap: 7px;
    }

    .tag-list {
      display: flex; flex-wrap: wrap; gap: 7px;
    }

    .tag {
      font-size: .75rem; font-weight: 500;
      border-radius: 100px;
      padding: 4px 11px;
    }

    .tag-found {
      background: rgba(34,211,160,.1);
      color: var(--green);
      border: 1px solid rgba(34,211,160,.2);
    }

    .tag-missing {
      background: rgba(244,63,94,.08);
      color: var(--red);
      border: 1px solid rgba(244,63,94,.2);
    }

    .tip-list { list-style: none; }

    .tip-list li {
      font-size: .84rem; color: #8890b0;
      line-height: 1.55; padding: 7px 0;
      border-bottom: 1px solid var(--border);
      display: flex; gap: 9px;
    }

    .tip-list li:last-child { border-bottom: none; padding-bottom: 0; }

    .tip-num {
      font-family: 'Syne', sans-serif;
      font-weight: 700; font-size: .72rem;
      color: var(--accent); flex-shrink: 0;
      margin-top: 2px;
    }

    /* ── Error ── */
    .error-card {
      background: rgba(244,63,94,.06);
      border: 1px solid rgba(244,63,94,.25);
      border-radius: var(--radius);
      padding: 20px 24px;
      color: #fb7185; font-size: .9rem;
    }
  </style>
</head>
<body>

  <div class="eyebrow">Internee.pk · Task 2</div>
  <h1>AI Resume Evaluator</h1>
  <p class="subtitle">Upload your PDF or DOCX resume and get a deep AI analysis — scores, skills gap, and ATS tips.</p>

  <div class="upload-card">
    <form id="upload-form">
      <div class="drop-zone" id="drop-zone">
        <input type="file" id="resume-file" name="resume" accept=".pdf,.docx"/>
        <div class="drop-icon">📄</div>
        <div class="drop-label">Drop your resume here</div>
        <div class="drop-hint">PDF or DOCX &nbsp;·&nbsp; Max 5 MB</div>
        <div class="file-chosen" id="file-name"></div>
      </div>
      <button class="btn-analyze" type="submit" id="submit-btn">Analyze Resume →</button>
    </form>
  </div>

  <div id="results"></div>

  <script>
    const form      = document.getElementById('upload-form');
    const fileInput = document.getElementById('resume-file');
    const dropZone  = document.getElementById('drop-zone');
    const fileLabel = document.getElementById('file-name');
    const resultsEl = document.getElementById('results');
    const submitBtn = document.getElementById('submit-btn');

    fileInput.addEventListener('change', () => {
      fileLabel.textContent = fileInput.files[0]?.name || '';
    });

    dropZone.addEventListener('dragover',  e => { e.preventDefault(); dropZone.classList.add('over'); });
    dropZone.addEventListener('dragleave', ()=> dropZone.classList.remove('over'));
    dropZone.addEventListener('drop',      ()=> dropZone.classList.remove('over'));

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const file = fileInput.files[0];
      if (!file) { showError('Please choose a file first.'); return; }

      submitBtn.disabled = true;
      submitBtn.innerHTML = '<span class="spinner"></span>Analyzing…';
      resultsEl.style.display = 'none';

      const fd = new FormData();
      fd.append('resume', file);

      try {
        const res  = await fetch('/upload', { method: 'POST', body: fd });
        const data = await res.json();
        data.error ? showError(data.error) : renderResults(data);
      } catch {
        showError('Network error. Is the Flask server running?');
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = 'Analyze Resume →';
      }
    });

    // ── Score helpers ────────────────────────────────────────────────────────

    function scoreColor(n) {
      if (n >= 75) return 'green';
      if (n >= 50) return 'yellow';
      return 'red';
    }

    function scoreLabel(n) {
      if (n >= 90) return 'Exceptional';
      if (n >= 75) return 'Strong';
      if (n >= 60) return 'Average';
      if (n >= 40) return 'Weak';
      return 'Poor';
    }

    // SVG donut arc for the overall score ring
    function arcPath(score, r) {
      const circ = 2 * Math.PI * r;
      const dash = (score / 100) * circ;
      return `stroke-dasharray: ${dash} ${circ};`;
    }

    // ── Main renderer ────────────────────────────────────────────────────────

    function renderResults(d) {
      const oc   = scoreColor(d.overall_score);
      const r    = 46;
      const circ = 2 * Math.PI * r;
      const dash = (d.overall_score / 100) * circ;

      const colorMap = { green: 'var(--green)', yellow: 'var(--yellow)', red: 'var(--red)' };

      // Overall hero
      const hero = `
        <div class="score-hero">
          <div class="score-ring">
            <svg viewBox="0 0 110 110" xmlns="http://www.w3.org/2000/svg">
              <circle cx="55" cy="55" r="${r}" fill="none" stroke="var(--border2)" stroke-width="7"/>
              <circle cx="55" cy="55" r="${r}" fill="none"
                stroke="${colorMap[oc]}" stroke-width="7"
                stroke-linecap="round"
                stroke-dasharray="${dash.toFixed(1)} ${circ.toFixed(1)}"/>
            </svg>
            <div class="score-ring-text">
              <span class="score-ring-num c-${oc}">${d.overall_score}</span>
              <span class="score-ring-label">/ 100</span>
            </div>
          </div>
          <div class="score-hero-text">
            <h2>${scoreLabel(d.overall_score)} Resume &nbsp;<span class="c-${oc}">·</span></h2>
            <p>${esc(d.summary)}</p>
          </div>
        </div>`;

      // Structure + Content score cards
      const makeScoreCard = (title, score, feedback) => {
        const c = scoreColor(score);
        return `
          <div class="score-card">
            <div class="score-card-header">
              <span class="score-card-title">${title}</span>
              <span class="score-badge c-${c}">${score}</span>
            </div>
            <div class="score-bar-track">
              <div class="score-bar-fill bg-${c}" style="width:${score}%"></div>
            </div>
            <p class="score-card-feedback">${esc(feedback)}</p>
          </div>`;
      };

      const scoresGrid = `
        <div class="scores-grid">
          ${makeScoreCard('Structure', d.structure_score, d.structure_feedback)}
          ${makeScoreCard('Content',   d.content_score,   d.content_feedback)}
        </div>`;

      // Skills found
      const foundTags = (d.skills_found || [])
        .map(s => `<span class="tag tag-found">${esc(s)}</span>`).join('');

      // Skills missing
      const missingTags = (d.skills_missing || [])
        .map(s => `<span class="tag tag-missing">${esc(s)}</span>`).join('');

      // ATS tips
      const tipItems = (d.ats_tips || [])
        .map((t, i) => `<li><span class="tip-num">0${i+1}</span><span>${esc(t)}</span></li>`)
        .join('');

      const infoGrid = `
        <div class="info-grid">
          <div class="info-card">
            <div class="info-card-title">✅ Skills Found</div>
            <div class="tag-list">${foundTags || '<span style="color:var(--muted);font-size:.82rem">None detected</span>'}</div>
          </div>
          <div class="info-card">
            <div class="info-card-title">⚠️ Skills Missing</div>
            <div class="tag-list">${missingTags || '<span style="color:var(--muted);font-size:.82rem">None flagged</span>'}</div>
          </div>
          <div class="info-card">
            <div class="info-card-title">🎯 ATS Tips</div>
            <ul class="tip-list">${tipItems}</ul>
          </div>
        </div>`;

      resultsEl.innerHTML = hero + scoresGrid + infoGrid;
      resultsEl.style.display = 'block';
      resultsEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    function showError(msg) {
      resultsEl.innerHTML = `<div class="error-card">⚠️  ${esc(msg)}</div>`;
      resultsEl.style.display = 'block';
    }

    function esc(s) {
      return String(s)
        .replace(/&/g,'&amp;').replace(/</g,'&lt;')
        .replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
  </script>
</body>
</html>
"""


# ─── Helpers ───────────────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return os.path.splitext(filename)[1].lower() in ALLOWED_EXTENSIONS


# ─── Routes ────────────────────────────────────────────────────────────────────

@app.route("/", methods=["GET"])
def index():
    return render_template_string(HTML_PAGE)


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