# AI Career Assistant — Open-Source Project Description

## 1. Project Overview

**AI Career Assistant** is a fully open-source, self-hostable web application that helps job seekers manage every stage of their job hunt — from writing tailored CVs and cover letters to passing ATS filters, finding relevant roles, and tracking applications. It combines the intelligence of open-source AI models hosted on **Hugging Face** with the reliability of **Supabase** (self-hosted or cloud free tier) as the backend, and renders polished, modern CVs using proven open-source template engines such as **Reactive Resume**.

The project is released under the **MIT License**, has **no billing or subscription layer**, and can be deployed by any individual, university, NGO, or company at zero software cost. All features are available to every user from day one.

---

## 2. Vision & Mission

**Vision:** To make professional-grade career tools freely available to everyone, everywhere — regardless of income, geography, or technical background.

**Mission:** Build a transparent, community-driven, privacy-respecting career toolkit that removes the friction from job hunting: writing documents, passing ATS filters, discovering roles, and staying organized — all with open-source software and open AI models.

---

## 3. Guiding Principles

| Principle | How It Is Applied |
|-----------|-------------------|
| **Open Source First** | MIT-licensed codebase; all dependencies are permissively licensed |
| **No Billing** | Every feature is free; no paywalls, trials, or subscriptions |
| **Privacy by Default** | Self-hostable; user data never leaves the instance unless the admin chooses |
| **AI Transparency** | Uses open-weight models (Mistral, Llama, Zephyr) via Hugging Face |
| **ATS-Friendly Output** | Templates follow semantic, parseable structure |
| **Community Driven** | Contributions welcome for templates, prompts, and languages |

---

## 4. Target Audience

- **Active job seekers** applying to many roles and needing tailored documents fast
- **Career changers** reframing their experience for a new industry
- **Recent graduates** unfamiliar with ATS systems
- **Passive candidates** quietly exploring opportunities
- **Freelancers and contractors** who regularly update CVs
- **Universities, NGOs, and outplacement services** that want to offer free career support

Primary launch languages: **English**, with community translations for German, French, Spanish, and Dutch.

---

## 5. Core Features (All Free, All Open Source)

### 5.1 CV & Cover Letter Builder
Users enter their experience, education, and skills plus a target job description. Open-source LLMs served through Hugging Face generate a tailored, ATS-optimized CV and matching cover letter in minutes.

### 5.2 Unlimited Edits & Downloads
Every generated document is stored in Supabase and remains editable in the browser. Users can download as many versions as they like in **Word (.docx)** or **PDF** format with no limits and no watermarks.

### 5.3 Resume Checker (ATS Optimization)
Users paste or upload an existing resume and receive:
- An **ATS compatibility score** (0–100)
- **Keyword match analysis** against a job description
- **Formatting and readability scores**
- **Missing keywords** to add
- **Strengths and improvement suggestions**

### 5.4 Resignation Letter Tool
A quick generator for professional resignation letters with selectable tone (formal, warm, brief), automatically including the last working day, manager name, and notice period.

### 5.5 Job Search
An integrated job discovery module that aggregates roles from free, public job APIs (e.g., Adzuna free tier, Remotive, Arbeitnow) matching the user's profile, skills, and location.

### 5.6 Job Tracker
A personal kanban-style dashboard backed by Supabase to log every application, update its status (Applied → Interview → Offer → Rejected), set follow-up reminders, and store notes and job URLs.

### 5.7 Priority Support → Replaced by Community Support
In place of a paid support tier, the project offers **community support** through GitHub Discussions, a Matrix/Discord channel, and a documentation site. Because everything is open source, users can also self-serve fixes, extend the code, or open issues.

---

## 6. Business Model — None

This is a **non-commercial, open-source project**. There is:

- No subscription, no free trial, no paywall
- No Stripe integration or payment processing
- No ads, tracking, or data monetization

**Sustainability** comes from:
- Community contributions (code, translations, templates)
- Optional donations via GitHub Sponsors or Open Collective
- Optional paid hosting/support offered by third parties (not part of this project)

---

## 7. Technical Architecture

| Layer | Technology |
|-------|-----------|
| **Frontend** | React / Next.js (or vanilla SPA) + Tailwind CSS |
| **Backend API** | Python (FastAPI or Flask) |
| **AI Models** | Hugging Face Inference API (free tier) or self-hosted via Ollama / HF Inference Endpoints — models such as `Mistral-7B-Instruct`, `Llama-3.1-8B-Instruct`, `Zephyr-7B-Beta`, and `BAAI/bge-large-en-v1.5` for semantic matching |
| **Database & Auth** | **Supabase** (self-hosted or free cloud tier) — Postgres, Auth, Row-Level Security |
| **CV Template Engine** | **Reactive Resume** (MIT) — 12+ modern templates, JSON schema, PDF export |
| **PDF Generation** | Gotenberg (Docker) for HTML→PDF; `python-docx` for Word export |
| **Job Data** | Adzuna free tier, Remotive API, Arbeitnow API |
| **Hosting** | Any Docker-capable host: Fly.io, Railway, Render, self-hosted VPS |

### Supabase Role
Supabase provides the entire backend-as-a-service layer:
- **Authentication** — email/password, magic links, OAuth
- **Postgres Database** — tables for `profiles`, `documents`, `applications`, `job_cache`
- **Row-Level Security** — every user can only access their own rows
- **Storage** — optional storage for uploaded resume files
- **Realtime** — live updates on the job tracker board

Because Supabase is itself open source, the entire stack can be **self-hosted end-to-end** with no vendor lock-in.

---

## 8. Open-Source CV Template Integration

### 8.1 Strategy
Rather than designing CV templates from scratch, the project builds on proven open-source templates that already meet modern design, ATS-friendliness, and export standards.

### 8.2 Primary Template Engine: Reactive Resume

| Aspect | Detail |
|--------|--------|
| **License** | MIT — free for commercial and non-commercial use |
| **Tech Stack** | TanStack Start (React 19, Vite), TypeScript, Tailwind CSS, Radix UI |
| **Templates** | Azurill, Bronzor, Chikorita, Ditto, Gengar, Glalie, Kakuna, Lapras, Leafish, Onyx, Pikachu, Rhyhorn |
| **Export** | PDF, JSON |
| **Features** | Real-time preview, drag-and-drop sections, rich text editor, custom colors/fonts/spacing, A4/Letter, custom CSS |
| **Self-Hosting** | Docker + PostgreSQL + Gotenberg |
| **Repository** | `github.com/AmruthPillai/Reactive-Resume` |

### 8.3 Complementary Templates

| Template | Stack | License | Best For |
|----------|-------|---------|----------|
| **ITCV** | Typst (YAML) | CC BY-SA 3.0 | Tufte-inspired, data-driven |
| **Open CV Template** | HTML/CSS/JS | MIT | Zero-dependency, print-ready |
| **vcard-react** | Next.js + Tailwind | Open | Developer portfolio CV |
| **Next.js Resume** | Next.js + Contentlayer | Open | Markdown-driven |
| **Minimalist CV** | Next.js + TS + Tailwind | Open | Single-file data config |
| **React-CV** | React/Next.js | Open | Adaptable, print-ready |
| **Mono Resume** | Next.js + TS + Tailwind | MIT | Monospace tech aesthetic |

### 8.4 Selection Criteria
1. ATS compatibility (semantic structure, selectable text)
2. PDF export quality (vector, consistent margins)
3. Customizability (colors, fonts, section ordering)
4. Active maintenance
5. Permissive license (MIT preferred)

### 8.5 Architectural Separation
- **Hugging Face models** → produce structured content (name, experience, skills)
- **Template engine** (Reactive Resume + alternatives) → visual presentation
- **Gotenberg** → HTML→PDF conversion

New templates can be added without touching the AI pipeline; AI model upgrades do not affect design.

---

## 9. User Flow (End-to-End)

1. **Sign up** with email or OAuth via Supabase Auth — free, instant.
2. **Onboarding** — enter name, target role, location, and paste a sample job description.
3. **Generate documents** — CV and cover letter produced by Hugging Face models.
4. **Run ATS check** — resume scored, feedback displayed.
5. **Browse jobs** — matching roles listed from free job APIs.
6. **Save to tracker** — one click adds the role with status "Applied."
7. **Update statuses** — move cards through Applied → Interview → Offer.
8. **Download as Word/PDF** — unlimited, no cost.
9. **Community support** — ask questions in GitHub Discussions or chat.

---

## 10. Key Differentiators

- **100% free and open source** — MIT licensed, no billing, no hidden costs
- **All-in-one** — replaces a CV builder, ATS checker, cover letter tool, job board, and tracker
- **AI-first** — every output is tailored using open-weight models, not templates
- **Self-hostable end-to-end** — Supabase + HF + Docker, zero vendor lock-in
- **Privacy-respecting** — no tracking, no ads, user data stays on the instance
- **Modern CV designs** — powered by Reactive Resume's 12+ templates
- **Fast time-to-value** — first CV in under 5 minutes

---

## 11. Success Metrics (KPIs)

Because there is no revenue, success is measured by impact and community health:

- **Active instances** deployed (via opt-in telemetry or GitHub stars/forks)
- **Documents generated per month**
- **Average ATS score improvement** (before vs. after using the checker)
- **Job applications tracked per user**
- **Contributors per quarter** (code, templates, translations)
- **Community response time** (GitHub Discussions, Matrix)
- **Net Promoter Score (NPS)** from user surveys

---

## 12. Roadmap

| Phase | Milestone |
|-------|-----------|
| **MVP (Weeks 1–6)** | CV builder, cover letter, resume checker, Supabase auth + storage |
| **Phase 2 (Weeks 7–12)** | Reactive Resume template integration, PDF/DOCX export, job search |
| **Phase 3 (Q2)** | Job tracker, resignation tool, i18n (DE/FR/ES/NL) |
| **Phase 4 (Q3)** | Optional Ollama support for fully offline, self-hosted LLM inference |
| **Phase 5 (Q4)** | Mobile PWA, community template marketplace, university/NGO deployment kit |

---

## 13. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AI hallucination in documents | Human-in-the-loop editing; clear "AI-generated, review before sending" notice |
| HF free-tier rate limits | Cache generations; support self-hosted Ollama fallback |
| Supabase free-tier limits | Full self-hosting guide; support alternative Postgres backends |
| Template licensing drift | Only permissive licenses (MIT, CC BY-SA) accepted; license audit in CI |
| Low community adoption | Clear docs, one-command Docker deploy, active Discussions |
| GDPR compliance | Supabase EU region, privacy policy, one-click data deletion endpoint |

---

## 14. Licensing

- **Project code:** MIT License
- **Reactive Resume templates:** MIT License (attribution preserved)
- **Alternative templates:** as per their respective licenses (MIT, CC BY-SA 3.0)
- **AI models:** as per Hugging Face model cards (mostly Apache 2.0 or similar open licenses)

All third-party attributions are maintained in a `LICENSES.md` file at the repository root.

---

## 15. Summary

**AI Career Assistant** is a free, open-source, self-hostable platform that gives every job seeker the tools a professional career coach would provide: AI-written CVs and cover letters, ATS optimization, resignation letters, job discovery, and application tracking. It is built on Hugging Face's open models, Supabase's open backend, and Reactive Resume's open templates — with no billing, no paywalls, and no tracking.

It is designed to be **fast to deploy, cheap to run, and easy to fork**, so that individuals, universities, and NGOs can offer world-class career support to anyone who needs it — for free, forever.

