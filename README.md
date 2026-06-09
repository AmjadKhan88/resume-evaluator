# AI Resume Evaluator
### Internee.pk — Task 2

Upload a PDF or DOCX resume and get instant AI-powered feedback on skills, structure, and improvements.

---

## Project Structure

```
resume-evaluator/
├── app.py              # Flask app — routes, upload handling, AI call
├── resume_analyzer.py  # Text extraction (PDF + DOCX)
├── requirements.txt    # Python dependencies
├── .env.example        # Environment variable template
└── README.md
```

---

## Quick Start

### 1. Clone / enter the project folder
```bash
cd resume-evaluator
```

### 2. Create a virtual environment
```bash
python -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up your API key
```bash
cp .env.example .env
# Open .env and paste your OpenAI API key
```

### 5. Run the app
```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

---

## Testing Without an API Key

The app works in **DEV MODE** without an OpenAI key — it will show you the extracted text instead of AI feedback. This lets you verify that file upload and text extraction work before adding the key.

---

## Key Design Decisions

| Decision | Why |
|---|---|
| `tempfile` for uploads | Security + auto-cleanup, no static uploads folder needed |
| File size check in memory | Avoids writing oversized files to disk at all |
| `secure_filename()` | Sanitizes user-supplied filenames to prevent path traversal |
| Text capped at 6000 chars | Stays within GPT-3.5-turbo's context limits comfortably |
| Scanned PDF detection | Explicit error message instead of silent empty analysis |

---

## Tech Stack
- **Flask** — web framework
- **PyPDF2** — PDF text extraction
- **python-docx** — DOCX text extraction  
- **OpenAI API** — GPT-3.5-turbo for resume analysis
- **python-dotenv** — environment variable management