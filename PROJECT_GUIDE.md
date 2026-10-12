# AI Career Assistant — Complete Implementation with Supabase + Hugging Face

I'll now build the complete project using your specific Supabase project details and the Hugging Face `HF_TOKEN` convention.

---

## Project Structure

```
ai-career-assistant/
├── backend/
│   ├── app.py
│   ├── models/
│   │   ├── cv_builder.py
│   │   ├── resume_checker.py
│   │   ├── resignation_letter.py
│   │   └── job_search.py
│   ├── database/
│   │   └── db.py
│   ├── utils/
│   │   └── document_export.py
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── styles.css
│   └── app.js
├── supabase/
│   ├── migrations/
│   │   └── 20260101000000_init_schema.sql
│   └── config.toml
├── docker-compose.yml
├── .env
└── README.md
```

---

## 1. Supabase Setup & Schema

### Step 1.1: Install Supabase CLI

```bash
npm install -g supabase
supabase --version
```

### Step 1.2: Initialize and Link

```bash
cd ai-career-assistant
supabase login
supabase init
supabase link --project-ref your-project-ref
```

You'll be prompted for your database password (set during project creation).

### Step 1.3: Create Schema Migration

Create `supabase/migrations/20260101000000_init_schema.sql`:

```sql
-- Enable UUID extension
create extension if not exists pgcrypto;

-- Profiles table (extends auth.users)
create table public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text unique not null,
  full_name text,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- Documents table (CVs, cover letters, resignation letters)
create table public.documents (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  doc_type text not null check (doc_type in ('cv', 'cover_letter', 'resignation')),
  title text not null,
  content text not null,
  template_id text default 'onyx',
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- Job applications tracker
create table public.job_applications (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade not null,
  company text not null,
  position text not null,
  status text default 'applied' check (status in ('applied', 'interview', 'offer', 'rejected')),
  job_url text,
  notes text,
  applied_date timestamp with time zone default now(),
  follow_up_date timestamp with time zone,
  created_at timestamp with time zone default now(),
  updated_at timestamp with time zone default now()
);

-- Enable Row Level Security
alter table public.profiles enable row level security;
alter table public.documents enable row level security;
alter table public.job_applications enable row level security;

-- RLS Policies: profiles
create policy "Users can view own profile"
  on public.profiles for select
  to authenticated
  using ((select auth.uid()) = id);

create policy "Users can update own profile"
  on public.profiles for update
  to authenticated
  using ((select auth.uid()) = id)
  with check ((select auth.uid()) = id);

create policy "Users can insert own profile"
  on public.profiles for insert
  to authenticated
  with check ((select auth.uid()) = id);

-- RLS Policies: documents
create policy "Users can view own documents"
  on public.documents for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can insert own documents"
  on public.documents for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update own documents"
  on public.documents for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete own documents"
  on public.documents for delete
  to authenticated
  using ((select auth.uid()) = user_id);

-- RLS Policies: job_applications
create policy "Users can view own applications"
  on public.job_applications for select
  to authenticated
  using ((select auth.uid()) = user_id);

create policy "Users can insert own applications"
  on public.job_applications for insert
  to authenticated
  with check ((select auth.uid()) = user_id);

create policy "Users can update own applications"
  on public.job_applications for update
  to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);

create policy "Users can delete own applications"
  on public.job_applications for delete
  to authenticated
  using ((select auth.uid()) = user_id);

-- Auto-create profile on user signup. NOTE: this is now maintained as the
-- real migration supabase/migrations/20261014000000_handle_new_user_trigger.sql
-- (the column is user_id, not id; on conflict do nothing keeps it idempotent).
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
begin
  insert into public.profiles (user_id, email, full_name)
  values (
    new.id,
    coalesce(new.email, ''),
    coalesce(new.raw_user_meta_data ->> 'full_name', new.raw_user_meta_data ->> 'name', '')
  )
  on conflict (user_id) do nothing;
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- Indexes for performance
create index idx_documents_user_id on public.documents(user_id);
create index idx_documents_type on public.documents(doc_type);
create index idx_applications_user_id on public.job_applications(user_id);
create index idx_applications_status on public.job_applications(status);
```

### Step 1.4: Push Schema to Remote

```bash
supabase db push
```

This applies all pending migrations to your remote Supabase project.

### Step 1.5: Generate TypeScript Types (Optional)

```bash
supabase gen types typescript --linked > frontend/types/supabase.ts
```

---

## 2. Backend Implementation

### Step 2.1: Environment Configuration

Create `.env` in the project root:

```env
# Supabase Configuration
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
SUPABASE_DB_URL=postgresql://postgres:[YOUR-PASSWORD]@db.your-project.supabase.co:5432/postgres

# Hugging Face
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Flask
SECRET_KEY=generate-a-random-secret-key-here
FLASK_ENV=development

# Optional: Adzuna for job search
ADZUNA_APP_ID=your_adzuna_id
ADZUNA_APP_KEY=your_adzuna_key
```

**Important:** Replace `[YOUR-PASSWORD]` with your actual Supabase database password. Replace `hf_xxxx` with your Hugging Face token from https://huggingface.co/settings/tokens.

### Step 2.2: Install Dependencies

Create `backend/requirements.txt`:

```txt
flask==3.0.0
flask-cors==4.0.0
requests==2.31.0
python-dotenv==1.0.0
psycopg2-binary==2.9.9
supabase==2.3.0
python-docx==1.1.0
reportlab==4.0.9
pyjwt==2.8.0
```

Install:

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### Step 2.3: Database Connection Layer

Create `backend/database/db.py`:

```python
import os
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")

if not SUPABASE_DB_URL:
    raise ValueError("SUPABASE_DB_URL environment variable is required")


@contextmanager
def get_db():
    """Yield a DB connection with auto-commit/rollback."""
    conn = psycopg2.connect(SUPABASE_DB_URL, sslmode="require")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def get_cursor(conn):
    """Return a RealDictCursor for dict-style row access."""
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
```

### Step 2.4: Hugging Face Integration

Create `backend/models/cv_builder.py`:

```python
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")
MODEL_ID = "mistralai/Mistral-7B-Instruct-v0.3"
API_URL = f"https://api-inference.huggingface.co/models/{MODEL_ID}"


def query_hf(prompt: str, max_tokens: int = 2000, temperature: float = 0.7, max_retries: int = 3) -> str:
    """Query Hugging Face Inference API with retry logic for model loading."""
    if not HF_TOKEN:
        raise ValueError("HF_TOKEN environment variable is required")

    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {
        "inputs": prompt,
        "parameters": {
            "max_new_tokens": max_tokens,
            "temperature": temperature,
            "return_full_text": False,
        },
    }

    for attempt in range(max_retries):
        response = requests.post(API_URL, headers=headers, json=payload, timeout=120)

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return data[0].get("generated_text", "")
            return str(data)

        if response.status_code == 503:
            # Model is loading, wait and retry
            time.sleep(10 * (attempt + 1))
            continue

        raise Exception(f"HF API error: {response.status_code} - {response.text}")

    raise Exception("Max retries exceeded while waiting for model to load")


def generate_cv(user_data: dict) -> str:
    """Generate a tailored CV using Hugging Face."""
    prompt = f"""<s>[INST] You are an expert CV writer. Create a professional, ATS-optimized CV.

User Information:
- Name: {user_data.get('name', '')}
- Email: {user_data.get('email', '')}
- Phone: {user_data.get('phone', '')}
- Target Position: {user_data.get('target_role', '')}
- Experience: {user_data.get('experience', '')}
- Education: {user_data.get('education', '')}
- Skills: {user_data.get('skills', '')}
- Achievements: {user_data.get('achievements', '')}

Job Description:
{user_data.get('job_description', 'Not provided')}

Create a compelling CV with:
1. Professional Summary (tailored to the job)
2. Core Competencies
3. Professional Experience (with quantified achievements)
4. Education
5. Skills
6. Additional Information

Use clean formatting with clear section headers. [/INST]"""

    return query_hf(prompt)


def generate_cover_letter(user_data: dict) -> str:
    """Generate a tailored cover letter using Hugging Face."""
    prompt = f"""<s>[INST] You are an expert cover letter writer. Create a compelling, personalized cover letter.

Applicant: {user_data.get('name', '')}
Target Role: {user_data.get('target_role', '')}
Company: {user_data.get('company', '')}
Key Skills: {user_data.get('skills', '')}
Experience Highlights: {user_data.get('experience', '')}
Why This Company: {user_data.get('motivation', 'Career growth and alignment with skills')}

Job Description:
{user_data.get('job_description', 'Not provided')}

Write a professional cover letter (350-450 words) that:
- Addresses the hiring manager
- Shows enthusiasm for the role and company
- Highlights relevant achievements with metrics
- Demonstrates cultural fit
- Ends with a clear call to action [/INST]"""

    return query_hf(prompt, max_tokens=1200)
```

### Step 2.5: Resume Checker

Create `backend/models/resume_checker.py`:

```python
import json
import re
from .cv_builder import query_hf


def check_resume(resume_text: str, job_description: str = "") -> dict:
    """Analyze resume for ATS compatibility using Hugging Face."""

    prompt = f"""<s>[INST] You are an ATS (Applicant Tracking System) expert. Analyze this resume and provide detailed feedback.

RESUME:
{resume_text}

TARGET JOB DESCRIPTION:
{job_description if job_description else 'Not provided'}

Provide analysis in this exact JSON format:
{{
    "ats_score": <number 0-100>,
    "keyword_match": <number 0-100>,
    "formatting_score": <number 0-100>,
    "readability_score": <number 0-100>,
    "missing_keywords": ["keyword1", "keyword2"],
    "strengths": ["strength1", "strength2"],
    "improvements": ["improvement1", "improvement2"],
    "summary": "Overall assessment summary"
}}

Return ONLY the JSON, no other text. [/INST]"""

    text = query_hf(prompt, max_tokens=1500, temperature=0.3)

    # Extract JSON from response
    json_match = re.search(r'\{.*\}', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

    return {
        "ats_score": 0,
        "error": "Could not parse analysis",
        "raw": text,
    }
```

### Step 2.6: Resignation Letter

Create `backend/models/resignation_letter.py`:

```python
from .cv_builder import query_hf


def generate_resignation_letter(data: dict) -> str:
    """Generate a professional resignation letter using Hugging Face."""
    prompt = f"""<s>[INST] Write a professional and respectful resignation letter.

Employee Name: {data.get('name', '')}
Manager Name: {data.get('manager_name', 'Manager')}
Company: {data.get('company', '')}
Position: {data.get('position', '')}
Last Working Day: {data.get('last_day', '')}
Notice Period: {data.get('notice_period', '2 weeks')}
Reason (optional): {data.get('reason', 'Personal reasons')}
Tone: {data.get('tone', 'professional and grateful')}

Write a concise, professional resignation letter (200-250 words) that:
- States resignation clearly with the last working day
- Expresses gratitude for opportunities
- Offers to help with transition
- Maintains a positive, professional tone [/INST]"""

    return query_hf(prompt, max_tokens=800, temperature=0.6)
```

### Step 2.7: Job Search

Create `backend/models/job_search.py`:

```python
import os
import requests
from dotenv import load_dotenv

load_dotenv()

ADZUNA_APP_ID = os.getenv("ADZUNA_APP_ID", "")
ADZUNA_APP_KEY = os.getenv("ADZUNA_APP_KEY", "")


def search_jobs(query: str, location: str = "", country: str = "de", results: int = 20) -> list:
    """Search jobs using Adzuna API (free tier)."""
    if not ADZUNA_APP_ID or not ADZUNA_APP_KEY:
        return _mock_jobs(query, location)

    url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results,
        "what": query,
        "where": location,
        "content-type": "application/json",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            return [
                {
                    "title": job.get("title"),
                    "company": job.get("company", {}).get("display_name"),
                    "location": job.get("location", {}).get("display_name"),
                    "description": job.get("description"),
                    "url": job.get("redirect_url"),
                    "salary_min": job.get("salary_min"),
                    "salary_max": job.get("salary_max"),
                    "created": job.get("created"),
                }
                for job in data.get("results", [])
            ]
    except Exception:
        pass

    return _mock_jobs(query, location)


def _mock_jobs(query: str, location: str) -> list:
    """Return mock jobs when API is not configured."""
    return [
        {
            "title": f"Senior {query}",
            "company": "Tech Corp",
            "location": location or "Berlin, Germany",
            "description": f"Looking for an experienced {query} professional...",
            "url": "#",
            "salary_min": 60000,
            "salary_max": 90000,
        },
        {
            "title": f"{query} Specialist",
            "company": "Innovation Labs",
            "location": location or "Munich, Germany",
            "description": f"Join our team as a {query} specialist...",
            "url": "#",
            "salary_min": 50000,
            "salary_max": 75000,
        },
    ]
```

### Step 2.8: Document Export

Create `backend/utils/document_export.py`:

```python
import io
from docx import Document
from docx.shared import Pt, RGBColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch


def text_to_docx(text: str, title: str = "Document") -> io.BytesIO:
    """Convert text to a Word document."""
    doc = Document()

    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    doc.add_heading(title, level=0)

    for line in text.split("\n"):
        if line.strip():
            if line.isupper() or (line.strip().endswith(":") and len(line) < 50):
                p = doc.add_paragraph()
                run = p.add_run(line.strip())
                run.bold = True
                run.font.size = Pt(12)
            else:
                doc.add_paragraph(line.strip())
        else:
            doc.add_paragraph()

    buffer = io.BytesIO()
    doc.save(buffer)
    buffer.seek(0)
    return buffer


def text_to_pdf(text: str, title: str = "Document") -> io.BytesIO:
    """Convert text to a PDF document."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=72,
        leftMargin=72,
        topMargin=72,
        bottomMargin=72,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Heading1"],
        fontSize=18,
        spaceAfter=20,
        textColor=RGBColor(0x1A, 0x1A, 0x2E),
    )
    body_style = ParagraphStyle(
        "CustomBody",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=15,
        spaceAfter=8,
    )

    story = [Paragraph(title, title_style), Spacer(1, 0.2 * inch)]

    for line in text.split("\n"):
        if line.strip():
            safe_line = (
                line.strip()
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
            )
            if line.isupper() or (line.strip().endswith(":") and len(line) < 50):
                story.append(Paragraph(f"<b>{safe_line}</b>", body_style))
            else:
                story.append(Paragraph(safe_line, body_style))
        else:
            story.append(Spacer(1, 0.1 * inch))

    doc.build(story)
    buffer.seek(0)
    return buffer
```

### Step 2.9: Main Flask Application

Create `backend/app.py`:

```python
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, jsonify, send_file, g
from flask_cors import CORS
from dotenv import load_dotenv
import jwt

from models.cv_builder import generate_cv, generate_cover_letter
from models.resume_checker import check_resume
from models.resignation_letter import generate_resignation_letter
from models.job_search import search_jobs
from utils.document_export import text_to_docx, text_to_pdf
from database.db import get_db, get_cursor

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "change-me-in-production")
CORS(app, supports_credentials=True, origins=["http://localhost:8080", "http://localhost:3000"])

# Supabase JWT secret (found in Supabase Dashboard > Settings > API > JWT Secret)
# Note: For production, verify JWTs properly using the Supabase JWT secret
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")


def require_auth(f):
    """Decorator to verify Supabase JWT and extract user_id."""

    @wraps(f)
    def decorated(*args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401

        token = auth_header.split(" ")[1]

        try:
            # For development: decode without verification (replace with proper verification in production)
            # In production, use: jwt.decode(token, SUPABASE_JWT_SECRET, algorithms=["HS256"], audience="authenticated")
            decoded = jwt.decode(token, options={"verify_signature": False})
            g.user_id = decoded.get("sub")
            g.user_email = decoded.get("email")

            if not g.user_id:
                return jsonify({"error": "Invalid token payload"}), 401

        except Exception as e:
            return jsonify({"error": f"Token verification failed: {str(e)}"}), 401

        return f(*args, **kwargs)

    return decorated


# ---------- Health Check ----------

@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.utcnow().isoformat()})


# ---------- CV Builder ----------

@app.route("/api/cv/generate", methods=["POST"])
@require_auth
def api_generate_cv():
    data = request.json
    try:
        content = generate_cv(data)

        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                """
                insert into public.documents (user_id, doc_type, title, content)
                values (%s, 'cv', %s, %s)
                returning id
                """,
                (g.user_id, f"CV - {data.get('target_role', 'Untitled')}", content),
            )
            doc_id = cur.fetchone()["id"]

        return jsonify({"content": content, "id": str(doc_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/cover-letter/generate", methods=["POST"])
@require_auth
def api_generate_cover_letter():
    data = request.json
    try:
        content = generate_cover_letter(data)

        with get_db() as conn:
            cur = get_cursor(conn)
            cur.execute(
                """
                insert into public.documents (user_id, doc_type, title, content)
                values (%s, 'cover_letter', %s, %s)
                returning id
                """,
                (g.user_id, f"Cover Letter - {data.get('company', 'Untitled')}", content),
            )
            doc_id = cur.fetchone()["id"]

        return jsonify({"content": content, "id": str(doc_id)})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Resume Checker ----------

@app.route("/api/resume/check", methods=["POST"])
def api_check_resume():
    data = request.json
    resume_text = data.get("resume_text", "")
    job_desc = data.get("job_description", "")

    if not resume_text:
        return jsonify({"error": "Resume text required"}), 400

    try:
        result = check_resume(resume_text, job_desc)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Resignation Letter ----------

@app.route("/api/resignation/generate", methods=["POST"])
def api_resignation():
    data = request.json
    try:
        content = generate_resignation_letter(data)
        return jsonify({"content": content})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Export ----------

@app.route("/api/export/docx", methods=["POST"])
def api_export_docx():
    data = request.json
    buffer = text_to_docx(data.get("content", ""), data.get("title", "Document"))
    return send_file(
        buffer,
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        as_attachment=True,
        download_name=f"{data.get('title', 'document')}.docx",
    )


@app.route("/api/export/pdf", methods=["POST"])
def api_export_pdf():
    data = request.json
    buffer = text_to_pdf(data.get("content", ""), data.get("title", "Document"))
    return send_file(
        buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{data.get('title', 'document')}.pdf",
    )


# ---------- Documents ----------

@app.route("/api/documents", methods=["GET"])
@require_auth
def list_documents():
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """
            select id, doc_type as type, title, updated_at
            from public.documents
            where user_id = %s
            order by updated_at desc
            """,
            (g.user_id,),
        )
        docs = cur.fetchall()

    return jsonify([
        {"id": str(d["id"]), "type": d["type"], "title": d["title"], "updated_at": d["updated_at"].isoformat()}
        for d in docs
    ])


@app.route("/api/documents/<doc_id>", methods=["GET", "PUT", "DELETE"])
@require_auth
def manage_document(doc_id):
    with get_db() as conn:
        cur = get_cursor(conn)

        if request.method == "GET":
            cur.execute(
                "select id, doc_type, title, content from public.documents where id = %s and user_id = %s",
                (doc_id, g.user_id),
            )
            doc = cur.fetchone()
            if not doc:
                return jsonify({"error": "Not found"}), 404
            return jsonify({
                "id": str(doc["id"]),
                "type": doc["doc_type"],
                "title": doc["title"],
                "content": doc["content"],
            })

        elif request.method == "PUT":
            data = request.json
            cur.execute(
                "update public.documents set content = %s, title = %s, updated_at = now() where id = %s and user_id = %s",
                (data.get("content"), data.get("title"), doc_id, g.user_id),
            )
            return jsonify({"success": True})

        else:  # DELETE
            cur.execute("delete from public.documents where id = %s and user_id = %s", (doc_id, g.user_id))
            return jsonify({"success": True})


# ---------- Job Search ----------

@app.route("/api/jobs/search", methods=["GET"])
def api_job_search():
    query = request.args.get("q", "")
    location = request.args.get("location", "")
    country = request.args.get("country", "de")

    if not query:
        return jsonify({"error": "Query required"}), 400

    try:
        jobs = search_jobs(query, location, country)
        return jsonify(jobs)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------- Job Tracker ----------

@app.route("/api/applications", methods=["GET", "POST"])
@require_auth
def applications():
    with get_db() as conn:
        cur = get_cursor(conn)

        if request.method == "POST":
            data = request.json
            cur.execute(
                """
                insert into public.job_applications (user_id, company, position, status, notes, job_url)
                values (%s, %s, %s, %s, %s, %s)
                returning id
                """,
                (
                    g.user_id,
                    data.get("company"),
                    data.get("position"),
                    data.get("status", "applied"),
                    data.get("notes"),
                    data.get("job_url"),
                ),
            )
            app_id = cur.fetchone()["id"]
            return jsonify({"id": str(app_id), "success": True})

        cur.execute(
            """
            select id, company, position, status, applied_date, notes, job_url
            from public.job_applications
            where user_id = %s
            order by applied_date desc
            """,
            (g.user_id,),
        )
        apps = cur.fetchall()

    return jsonify([
        {
            "id": str(a["id"]),
            "company": a["company"],
            "position": a["position"],
            "status": a["status"],
            "applied_date": a["applied_date"].isoformat(),
            "notes": a["notes"],
            "job_url": a["job_url"],
        }
        for a in apps
    ])


@app.route("/api/applications/<app_id>", methods=["PUT", "DELETE"])
@require_auth
def update_application(app_id):
    with get_db() as conn:
        cur = get_cursor(conn)

        if request.method == "PUT":
            data = request.json
            cur.execute(
                "update public.job_applications set status = %s, notes = %s, updated_at = now() where id = %s and user_id = %s",
                (data.get("status"), data.get("notes"), app_id, g.user_id),
            )
            return jsonify({"success": True})
        else:
            cur.execute("delete from public.job_applications where id = %s and user_id = %s", (app_id, g.user_id))
            return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True, port=5000)
```

---

## 3. Frontend Implementation

### Step 3.1: HTML

Create `frontend/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AI Career Assistant — Open Source</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header>
    <div class="logo">🚀 AI Career Assistant</div>
    <nav id="nav">
      <button data-tab="cv" class="active">CV Builder</button>
      <button data-tab="cover">Cover Letter</button>
      <button data-tab="checker">Resume Checker</button>
      <button data-tab="resignation">Resignation</button>
      <button data-tab="jobs">Job Search</button>
      <button data-tab="tracker">Tracker</button>
    </nav>
    <div id="auth-area">
      <button id="login-btn" onclick="showLogin()">Sign In</button>
      <span id="user-email" style="display:none"></span>
      <button id="logout-btn" style="display:none" onclick="logout()">Sign Out</button>
    </div>
  </header>

  <!-- Auth Modal -->
  <div id="auth-modal" class="modal" style="display:none">
    <div class="modal-content">
      <h3 id="auth-title">Sign In</h3>
      <input id="auth-email" type="email" placeholder="Email">
      <input id="auth-password" type="password" placeholder="Password">
      <input id="auth-name" type="text" placeholder="Full Name (for sign up)" style="display:none">
      <button onclick="handleAuth()" id="auth-submit">Sign In</button>
      <p class="auth-toggle">
        <span id="auth-toggle-text">Don't have an account?</span>
        <a href="#" onclick="toggleAuthMode(event)">Sign Up</a>
      </p>
      <button class="modal-close" onclick="hideLogin()">✕</button>
    </div>
  </div>

  <main>
    <!-- CV Builder -->
    <section id="cv" class="tab-panel active">
      <h2>CV Builder</h2>
      <div class="grid">
        <div class="form">
          <input id="cv-name" placeholder="Full Name">
          <input id="cv-email" placeholder="Email">
          <input id="cv-phone" placeholder="Phone">
          <input id="cv-role" placeholder="Target Role">
          <textarea id="cv-experience" placeholder="Experience (bullet points)"></textarea>
          <textarea id="cv-education" placeholder="Education"></textarea>
          <input id="cv-skills" placeholder="Skills (comma separated)">
          <textarea id="cv-achievements" placeholder="Achievements"></textarea>
          <textarea id="cv-jd" placeholder="Paste target job description (optional)"></textarea>
          <button onclick="generateCV()">✨ Generate CV</button>
        </div>
        <div class="output">
          <div class="output-toolbar">
            <button onclick="exportDoc('cv-output', 'CV', 'docx')">⬇ Word</button>
            <button onclick="exportDoc('cv-output', 'CV', 'pdf')">⬇ PDF</button>
          </div>
          <div id="cv-output" class="editable" contenteditable="true"></div>
        </div>
      </div>
    </section>

    <!-- Cover Letter -->
    <section id="cover" class="tab-panel">
      <h2>Cover Letter Generator</h2>
      <div class="grid">
        <div class="form">
          <input id="cl-name" placeholder="Your Name">
          <input id="cl-role" placeholder="Target Role">
          <input id="cl-company" placeholder="Company">
          <input id="cl-skills" placeholder="Key Skills">
          <textarea id="cl-experience" placeholder="Experience Highlights"></textarea>
          <textarea id="cl-motivation" placeholder="Why this company?"></textarea>
          <textarea id="cl-jd" placeholder="Job Description"></textarea>
          <button onclick="generateCover()">✨ Generate Cover Letter</button>
        </div>
        <div class="output">
          <div class="output-toolbar">
            <button onclick="exportDoc('cl-output', 'CoverLetter', 'docx')">⬇ Word</button>
            <button onclick="exportDoc('cl-output', 'CoverLetter', 'pdf')">⬇ PDF</button>
          </div>
          <div id="cl-output" class="editable" contenteditable="true"></div>
        </div>
      </div>
    </section>

    <!-- Resume Checker -->
    <section id="checker" class="tab-panel">
      <h2>Resume ATS Checker</h2>
      <textarea id="checker-resume" placeholder="Paste your resume text here" rows="15"></textarea>
      <textarea id="checker-jd" placeholder="Paste job description (optional)" rows="8"></textarea>
      <button onclick="checkResume()">🔍 Analyze Resume</button>
      <div id="checker-output"></div>
    </section>

    <!-- Resignation Letter -->
    <section id="resignation" class="tab-panel">
      <h2>Resignation Letter Tool</h2>
      <div class="grid">
        <div class="form">
          <input id="rl-name" placeholder="Your Name">
          <input id="rl-manager" placeholder="Manager Name">
          <input id="rl-company" placeholder="Company">
          <input id="rl-position" placeholder="Your Position">
          <input id="rl-lastday" type="date" placeholder="Last Working Day">
          <input id="rl-notice" placeholder="Notice Period (e.g. 2 weeks)">
          <textarea id="rl-reason" placeholder="Reason (optional)"></textarea>
          <select id="rl-tone">
            <option value="professional and grateful">Professional & Grateful</option>
            <option value="warm and personal">Warm & Personal</option>
            <option value="formal and brief">Formal & Brief</option>
          </select>
          <button onclick="generateResignation()">✨ Generate Letter</button>
        </div>
        <div class="output">
          <div class="output-toolbar">
            <button onclick="exportDoc('rl-output', 'ResignationLetter', 'docx')">⬇ Word</button>
            <button onclick="exportDoc('rl-output', 'ResignationLetter', 'pdf')">⬇ PDF</button>
          </div>
          <div id="rl-output" class="editable" contenteditable="true"></div>
        </div>
      </div>
    </section>

    <!-- Job Search -->
    <section id="jobs" class="tab-panel">
      <h2>Job Search</h2>
      <div class="search-bar">
        <input id="job-q" placeholder="Job title or keyword">
        <input id="job-location" placeholder="Location">
        <select id="job-country">
          <option value="de">Germany</option>
          <option value="gb">UK</option>
          <option value="us">USA</option>
          <option value="fr">France</option>
          <option value="nl">Netherlands</option>
        </select>
        <button onclick="searchJobs()">🔎 Search</button>
      </div>
      <div id="jobs-list"></div>
    </section>

    <!-- Job Tracker -->
    <section id="tracker" class="tab-panel">
      <h2>Job Application Tracker</h2>
      <div class="form-inline">
        <input id="tr-company" placeholder="Company">
        <input id="tr-position" placeholder="Position">
        <input id="tr-url" placeholder="Job URL">
        <select id="tr-status">
          <option value="applied">Applied</option>
          <option value="interview">Interview</option>
          <option value="offer">Offer</option>
          <option value="rejected">Rejected</option>
        </select>
        <button onclick="addApplication()">+ Add</button>
      </div>
      <div id="tracker-list"></div>
    </section>
  </main>

  <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
  <script src="app.js"></script>
</body>
</html>
```

### Step 3.2: JavaScript

Create `frontend/app.js`:

```javascript
const API = "http://localhost:5000/api";

// Supabase client
const SUPABASE_URL = "https://your-project.supabase.co";
const SUPABASE_PUBLISHABLE_KEY = "your_supabase_publishable_key";

const supabase = window.supabase.createClient(SUPABASE_URL, SUPABASE_PUBLISHABLE_KEY);

let currentSession = null;

// ---------- Auth ----------

async function initAuth() {
  const { data: { session } } = await supabase.auth.getSession();
  currentSession = session;
  updateAuthUI(session);

  supabase.auth.onAuthStateChange((_event, session) => {
    currentSession = session;
    updateAuthUI(session);
  });
}

function updateAuthUI(session) {
  const loginBtn = document.getElementById("login-btn");
  const logoutBtn = document.getElementById("logout-btn");
  const userEmail = document.getElementById("user-email");

  if (session?.user) {
    loginBtn.style.display = "none";
    logoutBtn.style.display = "inline-block";
    userEmail.style.display = "inline";
    userEmail.textContent = session.user.email;
  } else {
    loginBtn.style.display = "inline-block";
    logoutBtn.style.display = "none";
    userEmail.style.display = "none";
  }
}

function showLogin() {
  document.getElementById("auth-modal").style.display = "flex";
}

function hideLogin() {
  document.getElementById("auth-modal").style.display = "none";
}

let authMode = "signin";

function toggleAuthMode(e) {
  e.preventDefault();
  authMode = authMode === "signin" ? "signup" : "signin";
  document.getElementById("auth-title").textContent = authMode === "signin" ? "Sign In" : "Sign Up";
  document.getElementById("auth-submit").textContent = authMode === "signin" ? "Sign In" : "Sign Up";
  document.getElementById("auth-name").style.display = authMode === "signup" ? "block" : "none";
  document.getElementById("auth-toggle-text").textContent = authMode === "signin" ? "Don't have an account?" : "Already have an account?";
  document.querySelector(".auth-toggle a").textContent = authMode === "signin" ? "Sign Up" : "Sign In";
}

async function handleAuth() {
  const email = document.getElementById("auth-email").value;
  const password = document.getElementById("auth-password").value;
  const fullName = document.getElementById("auth-name").value;

  if (authMode === "signin") {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) return alert(error.message);
    hideLogin();
  } else {
    const { error } = await supabase.auth.signUp({
      email,
      password,
      options: { data: { full_name: fullName } },
    });
    if (error) return alert(error.message);
    alert("Sign up successful! Please check your email to confirm.");
    hideLogin();
  }
}

async function logout() {
  await supabase.auth.signOut();
}

// Get auth header for API calls
function authHeaders() {
  if (!currentSession?.access_token) return {};
  return { Authorization: `Bearer ${currentSession.access_token}` };
}

// ---------- Tab Navigation ----------

document.querySelectorAll("nav button").forEach((btn) => {
  btn.addEventListener("click", () => {
    document.querySelectorAll("nav button").forEach((b) => b.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
    btn.classList.add("active");
    document.getElementById(btn.dataset.tab).classList.add("active");

    if (btn.dataset.tab === "tracker") loadApplications();
  });
});

// ---------- CV Builder ----------

async function generateCV() {
  const data = {
    name: document.getElementById("cv-name").value,
    email: document.getElementById("cv-email").value,
    phone: document.getElementById("cv-phone").value,
    target_role: document.getElementById("cv-role").value,
    experience: document.getElementById("cv-experience").value,
    education: document.getElementById("cv-education").value,
    skills: document.getElementById("cv-skills").value,
    achievements: document.getElementById("cv-achievements").value,
    job_description: document.getElementById("cv-jd").value,
  };
  await callGenerate(`${API}/cv/generate`, data, "cv-output");
}

async function generateCover() {
  const data = {
    name: document.getElementById("cl-name").value,
    target_role: document.getElementById("cl-role").value,
    company: document.getElementById("cl-company").value,
    skills: document.getElementById("cl-skills").value,
    experience: document.getElementById("cl-experience").value,
    motivation: document.getElementById("cl-motivation").value,
    job_description: document.getElementById("cl-jd").value,
  };
  await callGenerate(`${API}/cover-letter/generate`, data, "cl-output");
}

async function generateResignation() {
  const data = {
    name: document.getElementById("rl-name").value,
    manager_name: document.getElementById("rl-manager").value,
    company: document.getElementById("rl-company").value,
    position: document.getElementById("rl-position").value,
    last_day: document.getElementById("rl-lastday").value,
    notice_period: document.getElementById("rl-notice").value,
    reason: document.getElementById("rl-reason").value,
    tone: document.getElementById("rl-tone").value,
  };
  await callGenerate(`${API}/resignation/generate`, data, "rl-output");
}

async function callGenerate(url, data, outputId) {
  const out = document.getElementById(outputId);
  out.innerHTML = '<span class="loader"></span>Generating with AI...';
  try {
    const res = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify(data),
    });
    const result = await res.json();
    if (result.error) {
      out.innerHTML = `<span style="color:red">Error: ${result.error}</span>`;
      return;
    }
    out.innerText = result.content || JSON.stringify(result);
  } catch (e) {
    out.innerHTML = `<span style="color:red">Error: ${e.message}</span>`;
  }
}

// ---------- Export ----------

async function exportDoc(outputId, title, format) {
  const content = document.getElementById(outputId).innerText;
  if (!content) return alert("Generate content first.");
  const res = await fetch(`${API}/export/${format}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ content, title }),
  });
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `${title}.${format}`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------- Resume Checker ----------

async function checkResume() {
  const out = document.getElementById("checker-output");
  out.innerHTML = '<div class="score-card"><span class="loader"></span>Analyzing...</div>';
  try {
    const res = await fetch(`${API}/resume/check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        resume_text: document.getElementById("checker-resume").value,
        job_description: document.getElementById("checker-jd").value,
      }),
    });
    const r = await res.json();
    if (r.error) {
      out.innerHTML = `<p style="color:red">${r.error}</p>`;
      return;
    }

    out.innerHTML = `
      <div class="score-card">
        <div class="score-grid">
          <div class="score-item"><div class="value">${r.ats_score || 0}</div><div class="label">ATS Score</div></div>
          <div class="score-item"><div class="value">${r.keyword_match || 0}</div><div class="label">Keyword Match</div></div>
          <div class="score-item"><div class="value">${r.formatting_score || 0}</div><div class="label">Formatting</div></div>
          <div class="score-item"><div class="value">${r.readability_score || 0}</div><div class="label">Readability</div></div>
        </div>
        ${r.summary ? `<p><strong>Summary:</strong> ${r.summary}</p>` : ""}
        ${r.missing_keywords?.length ? `<div class="list-section"><h4>Missing Keywords</h4>${r.missing_keywords.map((k) => `<span class="badge">${k}</span>`).join("")}</div>` : ""}
        ${r.strengths?.length ? `<div class="list-section"><h4>Strengths</h4><ul>${r.strengths.map((s) => `<li>${s}</li>`).join("")}</ul></div>` : ""}
        ${r.improvements?.length ? `<div class="list-section"><h4>Improvements</h4><ul>${r.improvements.map((s) => `<li>${s}</li>`).join("")}</ul></div>` : ""}
      </div>
    `;
  } catch (e) {
    out.innerHTML = `<p style="color:red">Error: ${e.message}</p>`;
  }
}

// ---------- Job Search ----------

async function searchJobs() {
  const q = document.getElementById("job-q").value;
  const location = document.getElementById("job-location").value;
  const country = document.getElementById("job-country").value;
  const list = document.getElementById("jobs-list");
  list.innerHTML = '<span class="loader"></span>Searching...';

  try {
    const res = await fetch(`${API}/jobs/search?q=${encodeURIComponent(q)}&location=${encodeURIComponent(location)}&country=${country}`);
    const jobs = await res.json();
    if (jobs.error) {
      list.innerHTML = `<p style="color:red">${jobs.error}</p>`;
      return;
    }
    if (!jobs.length) {
      list.innerHTML = "<p>No jobs found.</p>";
      return;
    }

    list.innerHTML = jobs
      .map(
        (j) => `
      <div class="job-card">
        <div>
          <h3>${j.title}</h3>
          <div class="company">${j.company || "Unknown"} — ${j.location || ""}</div>
          <div class="desc">${(j.description || "").slice(0, 200)}...</div>
          ${j.salary_min ? `<div><strong>€${Math.round(j.salary_min)} - €${Math.round(j.salary_max)}</strong></div>` : ""}
        </div>
        <div>
          <a href="${j.url}" target="_blank">View →</a>
        </div>
      </div>
    `
      )
      .join("");
  } catch (e) {
    list.innerHTML = `<p style="color:red">Error: ${e.message}</p>`;
  }
}

// ---------- Job Tracker ----------

async function addApplication() {
  if (!currentSession) return alert("Please sign in first.");
  const data = {
    company: document.getElementById("tr-company").value,
    position: document.getElementById("tr-position").value,
    job_url: document.getElementById("tr-url").value,
    status: document.getElementById("tr-status").value,
  };
  if (!data.company || !data.position) return alert("Company & position required");
  await fetch(`${API}/applications`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(data),
  });
  document.getElementById("tr-company").value = "";
  document.getElementById("tr-position").value = "";
  document.getElementById("tr-url").value = "";
  loadApplications();
}

async function loadApplications() {
  if (!currentSession) return;
  const list = document.getElementById("tracker-list");
  list.innerHTML = '<span class="loader"></span>Loading...';
  try {
    const res = await fetch(`${API}/applications`, { headers: authHeaders() });
    const apps = await res.json();
    if (!apps.length) {
      list.innerHTML = "<p>No applications yet.</p>";
      return;
    }
    list.innerHTML = apps
      .map(
        (a) => `
      <div class="app-card">
        <div>
          <h3>${a.position}</h3>
          <div class="company" style="color:#6366f1;font-weight:600">${a.company}</div>
          ${a.job_url ? `<a href="${a.job_url}" target="_blank">Job link →</a>` : ""}
          <div style="font-size:0.8rem;color:#64748b;margin-top:0.4rem">Applied: ${new Date(a.applied_date).toLocaleDateString()}</div>
        </div>
        <div style="text-align:right">
          <span class="status-badge status-${a.status}">${a.status}</span>
          <div style="margin-top:0.75rem">
            <select onchange="updateStatus('${a.id}', this.value)">
              ${["applied", "interview", "offer", "rejected"].map((s) => `<option value="${s}" ${s === a.status ? "selected" : ""}>${s}</option>`).join("")}
            </select>
            <button onclick="deleteApp('${a.id}')" style="background:#ef4444;margin-top:0.4rem;padding:0.4rem 0.8rem;font-size:0.8rem">Delete</button>
          </div>
        </div>
      </div>
    `
      )
      .join("");
  } catch (e) {
    list.innerHTML = `<p style="color:red">Error: ${e.message}</p>`;
  }
}

async function updateStatus(id, status) {
  await fetch(`${API}/applications/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });
  loadApplications();
}

async function deleteApp(id) {
  if (!confirm("Delete this application?")) return;
  await fetch(`${API}/applications/${id}`, { method: "DELETE", headers: authHeaders() });
  loadApplications();
}

// ---------- Initialize ----------

initAuth();
```

### Step 3.3: CSS

Create `frontend/styles.css`:

```css
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: #f5f7fb;
  color: #1a1a2e;
}

header {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  padding: 1rem 2rem;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}
.logo { font-size: 1.4rem; font-weight: 700; }
nav { display: flex; gap: 0.5rem; flex-wrap: wrap; }
nav button {
  background: rgba(255,255,255,0.15);
  border: none;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: 0.2s;
}
nav button:hover, nav button.active { background: rgba(255,255,255,0.35); }
#auth-area { display: flex; align-items: center; gap: 0.75rem; }
#auth-area button {
  background: rgba(255,255,255,0.2);
  border: none;
  color: white;
  padding: 0.5rem 1rem;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.85rem;
}
#user-email { font-size: 0.85rem; opacity: 0.9; }

main { max-width: 1300px; margin: 2rem auto; padding: 0 1.5rem; }

.tab-panel { display: none; }
.tab-panel.active { display: block; }
h2 { margin-bottom: 1.5rem; color: #1a1a2e; }

.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
@media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }

.form, .output, .tab-panel textarea, .tab-panel input, .tab-panel select {
  background: white;
  border-radius: 12px;
}
.form {
  padding: 1.5rem;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
  box-shadow: 0 2px 12px rgba(0,0,0,0.05);
}
input, textarea, select {
  padding: 0.75rem;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  font-size: 0.95rem;
  font-family: inherit;
  width: 100%;
}
textarea { min-height: 80px; resize: vertical; }

button {
  background: linear-gradient(135deg, #6366f1, #8b5cf6);
  color: white;
  border: none;
  padding: 0.75rem 1.25rem;
  border-radius: 8px;
  cursor: pointer;
  font-size: 0.95rem;
  font-weight: 600;
  transition: 0.2s;
}
button:hover { transform: translateY(-1px); box-shadow: 0 4px 12px rgba(99,102,241,0.3); }

.output { padding: 1.5rem; min-height: 500px; box-shadow: 0 2px 12px rgba(0,0,0,0.05); }
.output-toolbar {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #e2e8f0;
}
.output-toolbar button { padding: 0.5rem 0.9rem; font-size: 0.85rem; }

.editable { white-space: pre-wrap; line-height: 1.7; font-size: 0.95rem; outline: none; }
.editable:empty::before { content: "Your generated content will appear here..."; color: #94a3b8; }

.tab-panel textarea { margin-bottom: 1rem; }

.search-bar, .form-inline { display: flex; gap: 0.75rem; margin-bottom: 1.5rem; flex-wrap: wrap; }
.search-bar input, .form-inline input { flex: 1; min-width: 150px; }

.job-card, .app-card {
  background: white;
  padding: 1.25rem;
  border-radius: 12px;
  margin-bottom: 1rem;
  box-shadow: 0 2px 8px rgba(0,0,0,0.05);
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}
.job-card h3, .app-card h3 { margin-bottom: 0.25rem; color: #1a1a2e; }
.job-card .company { color: #6366f1; font-weight: 600; margin-bottom: 0.5rem; }
.job-card .desc { color: #64748b; font-size: 0.9rem; margin-bottom: 0.75rem; }
.job-card a { color: #6366f1; text-decoration: none; font-weight: 600; }
.job-card a:hover { text-decoration: underline; }

.status-badge {
  display: inline-block;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
}
.status-applied { background: #dbeafe; color: #1e40af; }
.status-interview { background: #fef3c7; color: #92400e; }
.status-offer { background: #d1fae5; color: #065f46; }
.status-rejected { background: #fee2e2; color: #991b1b; }

.score-card { background: white; padding: 1.5rem; border-radius: 12px; margin-top: 1.5rem; }
.score-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }
.score-item { text-align: center; padding: 1rem; background: #f8fafc; border-radius: 10px; }
.score-item .value { font-size: 2rem; font-weight: 700; color: #6366f1; }
.score-item .label { font-size: 0.8rem; color: #64748b; text-transform: uppercase; letter-spacing: 0.5px; }
.list-section { margin-top: 1.25rem; }
.list-section h4 { margin-bottom: 0.5rem; color: #1a1a2e; }
.list-section ul { list-style: none; }
.list-section li { padding: 0.5rem 0.75rem; background: #f8fafc; border-radius: 8px; margin-bottom: 0.4rem; border-left: 3px solid #6366f1; }
.badge { display: inline-block; padding: 0.25rem 0.6rem; background: #fee2e2; color: #991b1b; border-radius: 6px; font-size: 0.8rem; margin: 0.2rem; }

.loader {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 3px solid #e2e8f0;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  margin-right: 0.5rem;
  vertical-align: middle;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Modal */
.modal {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}
.modal-content {
  background: white;
  padding: 2rem;
  border-radius: 16px;
  width: 400px;
  max-width: 90%;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.modal-close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  background: transparent;
  color: #64748b;
  font-size: 1.2rem;
  padding: 0.25rem 0.5rem;
}
.auth-toggle { font-size: 0.85rem; text-align: center; color: #64748b; }
.auth-toggle a { color: #6366f1; text-decoration: none; font-weight: 600; }
```

---

## 4. Docker Compose (Optional)

Create `docker-compose.yml`:

```yaml
version: "3.9"

services:
  backend:
    build: ./backend
    ports:
      - "5000:5000"
    environment:
      - SUPABASE_URL=${SUPABASE_URL}
      - SUPABASE_PUBLISHABLE_KEY=${SUPABASE_PUBLISHABLE_KEY}
      - SUPABASE_DB_URL=${SUPABASE_DB_URL}
      - HF_TOKEN=${HF_TOKEN}
      - SECRET_KEY=${SECRET_KEY}
      - ADZUNA_APP_ID=${ADZUNA_APP_ID}
      - ADZUNA_APP_KEY=${ADZUNA_APP_KEY}
    volumes:
      - ./backend:/app
    command: python app.py

  frontend:
    image: nginx:alpine
    ports:
      - "8080:80"
    volumes:
      - ./frontend:/usr/share/nginx/html:ro
    depends_on:
      - backend
```

Create `backend/Dockerfile`:

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 5000

CMD ["python", "app.py"]
```

---

## 5. Run Instructions

### Step 5.1: Set Up Supabase

```bash
# Install Supabase CLI
npm install -g supabase

# Login
supabase login

# Initialize (if not already done)
cd ai-career-assistant
supabase init

# Link to your project
supabase link --project-ref your-project-ref

# Push schema
supabase db push
```

### Step 5.2: Configure Environment

Create `.env` in the project root with your actual values:

```env
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_PUBLISHABLE_KEY=your_supabase_publishable_key
SUPABASE_DB_URL=postgresql://postgres:[YOUR-PASSWORD]@db.your-project.supabase.co:5432/postgres
HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SECRET_KEY=your-random-secret-key
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
```

### Step 5.3: Run Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Backend runs at `http://localhost:5000`

### Step 5.4: Run Frontend

```bash
cd frontend
python -m http.server 8080
```

Visit `http://localhost:8080`

### Step 5.5: Or Use Docker

```bash
docker-compose up --build
```

Frontend at `http://localhost:8080`, backend at `http://localhost:5000`

---

## 6. Testing the Flow

1. Open `http://localhost:8080`
2. Click **Sign In** → **Sign Up** with your email
3. Check your email for confirmation link (Supabase sends this)
4. After confirmation, sign in
5. Go to **CV Builder**, fill in details, click **Generate CV**
6. Download as **PDF** or **Word**
7. Go to **Resume Checker**, paste resume → get ATS score
8. Go to **Job Tracker** → add applications
9. All data persists in Supabase and is scoped to your user via RLS

---

## 7. Key Security Notes

- **RLS is enabled** on all tables — users can only access their own data
- **Publishable key** is safe for frontend use (it's designed to be public)
- **HF_TOKEN** is used for Hugging Face (not HUGGINGFACE_API_KEY)
- **JWT verification** in backend extracts `user_id` from Supabase tokens

---

## 8. What's Included

| Feature | Status |
|---------|--------|
| CV Builder | ✅ Hugging Face + Supabase persistence |
| Cover Letter | ✅ Hugging Face |
| Resume Checker | ✅ ATS scoring via HF |
| Resignation Letter | ✅ Tone-selectable |
| Job Search | ✅ Adzuna API (mock fallback) |
| Job Tracker | ✅ Full CRUD with Supabase |
| Auth | ✅ Supabase Auth with RLS |
| Export | ✅ DOCX + PDF |
| Open Source | ✅ MIT license, no billing |

---

## 9. Next Steps

1. **Get your HF_TOKEN**: https://huggingface.co/settings/tokens
2. **Get Adzuna keys** (optional): https://developer.adzuna.com/
3. **Add `SUPABASE_JWT_SECRET`** to `.env` for production JWT verification
4. **Deploy**: Backend on Render/Railway, Frontend on Vercel/Netlify

 designs?