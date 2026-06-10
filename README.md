# AI Resume Evaluator

Professional resume analysis web app built for **Internee.pk Internship - Task 2**.

The app accepts PDF or DOCX resumes, extracts readable text, and returns structured AI feedback including skills detected, missing skills, ATS tips, structure score, content score, and an overall resume score.

## Features

- Upload resume files in PDF or DOCX format
- Validate file type and 5 MB upload size limit
- Extract text from digital PDFs and Word documents
- Analyze resume quality with Gemini through LangChain
- Return structured JSON feedback for the frontend
- Developer mode when no API key is configured
- Ready for deployment on Vercel

## Tech Stack

- **Python**
- **Flask**
- **LangChain**
- **Google Gemini**
- **PyPDF2**
- **python-docx**
- **HTML, CSS, JavaScript**
- **Vercel**

## Project Structure

```text
resume-evaluator/
|-- app.py               # Flask application and upload routes
|-- resume_analyzer.py   # Resume text extraction and AI analysis logic
|-- index.html           # Frontend upload interface
|-- requirements.txt     # Python dependencies
|-- vercel.json          # Vercel deployment configuration
|-- .env.example         # Environment variable template
|-- .gitignore
|-- .vercelignore
`-- README.md
```

## Getting Started

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd resume-evaluator
```

### 2. Create a virtual environment

```bash
python -m venv venv
```

Activate it:

```bash
# Windows
venv\Scripts\activate

# macOS/Linux
source venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

Create a `.env` file from the example:

```bash
cp .env.example .env
```

Add your Gemini API key:

```env
OPENAI_API_KEY=your_gemini_api_key_here
```

> Note: The variable is named `OPENAI_API_KEY` in this project, but it is used as the Google Gemini API key by `langchain-google-genai`.

### 5. Run locally

```bash
python app.py
```

Open:

```text
http://127.0.0.1:5000
```

## API Endpoints

| Method | Route | Description |
|---|---|---|
| GET | `/` | Serves the upload page |
| POST | `/upload` | Accepts a resume file and returns AI analysis |

## Upload Rules

- Supported formats: `.pdf`, `.docx`
- Maximum file size: 5 MB
- Password-protected PDFs are rejected
- Scanned/image-only PDFs may fail because they do not contain selectable text

## Vercel Deployment

This project includes `vercel.json`, so Vercel can run the Flask app with the Python serverless runtime.

### Deploy Steps

1. Push this project to GitHub.
2. Open [Vercel](https://vercel.com/).
3. Click **Add New Project** and import your repository.
4. Keep the default framework settings.
5. Add this environment variable in Vercel:

```text
OPENAI_API_KEY=your_gemini_api_key_here
```

6. Click **Deploy**.

After deployment, the app will be available at your Vercel project URL.

## Environment Variables

| Variable | Required | Description |
|---|---:|---|
| `OPENAI_API_KEY` | Yes | Gemini API key used by LangChain for resume analysis |

If this variable is missing, the app runs in developer mode and only confirms text extraction.

## How It Works

1. User uploads a PDF or DOCX resume.
2. Flask validates the file type and size.
3. The file is saved temporarily using Python's `tempfile`.
4. Text is extracted using PyPDF2 or python-docx.
5. LangChain sends the resume content to Gemini.
6. The app returns structured JSON feedback to the frontend.

## Author

Developed as **Internee.pk Internship Task 2**.
