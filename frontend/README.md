# AI Career Assistant - Frontend

Modern React + Vite frontend for the AI Career Assistant application. Built with **shadcn/ui** and **Tailwind CSS v4** for a professional, accessible, and maintainable UI.

## 📁 Project Structure

```
frontend/
├── src/
│   ├── components/
│   │   ├── ui/              # shadcn/ui components (Button, Card, Input, etc.)
│   │   ├── AsyncStates.jsx  # Loading, Empty, Error states
│   │   ├── AuthGuard.jsx    # Authentication guard component
│   │   └── StatusBanner.jsx # Global status notifications
│   ├── features/
│   │   ├── auth/            # Authentication components
│   │   ├── chat/            # AI Chat platform
│   │   ├── documents/       # CV/Resume generation
│   │   ├── jobs/            # Job search and discovery
│   │   ├── resume-checker/  # ATS resume analysis
│   │   └── tracker/         # Application tracking
│   ├── hooks/              # Custom React hooks
│   ├── i18n/               # Internationalization
│   ├── lib/                # Utilities and API client
│   ├── styles.css         # Global styles with Tailwind
│   ├── App.jsx            # Main application shell
│   └── main.jsx           # Entry point with ErrorBoundary
├── components.json        # shadcn/ui configuration
├── tailwind.config.js     # Tailwind CSS theme
├── vite.config.js         # Vite configuration
└── package.json
```

## 🎨 Design System

### Color Palette

| Token | Light Mode | Dark Mode | Usage |
|-------|------------|-----------|-------|
| `--primary` | `#2d63f3` | `#4c73ff` | Primary actions, buttons |
| `--primary-foreground` | `#ffffff` | `#ffffff` | Text on primary |
| `--background` | `#f5f7fb` | `#0f172a` | Page background |
| `--foreground` | `#1d2433` | `#e2e8f4` | Primary text |
| `--card` | `rgba(255, 255, 255, 0.9)` | `#16203a` | Card backgrounds |
| `--muted` | `#f5f7fb` | `#16203a` | Muted surfaces |
| `--accent` | `#eef3ff` | `#1f2a48` | Accent surfaces |
| `--border` | `rgba(26, 42, 91, 0.08)` | `rgba(255, 255, 255, 0.08)` | Borders |

### Typography

- **Font Family**: Inter (fallback: Segoe UI, sans-serif)
- **Base Size**: 16px
- **Heading Scale**: `text-3xl`, `text-2xl`, `text-xl`
- **Body**: `text-sm`, `text-base`

### Spacing & Layout

- **Container Width**: `max-w-6xl` (1200px max)
- **Card Radius**: `rounded-xl` (0.75rem)
- **Button Radius**: `rounded-lg` (0.5rem)
- **Shadows**: `shadow-soft`, `shadow-medium`, `shadow-hard`

### Animations

- **Fade In**: 200ms ease-in-out
- **Slide In**: 300ms ease-out
- **Scale In**: 200ms ease-out

## 🚀 Getting Started

### Prerequisites

- Node.js 18+ 
- npm or yarn

### Installation

```bash
cd frontend
npm install
```

### Development

```bash
# Start the Vite dev server on http://localhost:5173
npm run dev

# Or use the Makefile
make frontend-dev
```

### Production Build

```bash
npm run build
npm run preview
```

### Testing

```bash
npm test          # Run all tests
npm run test:watch  # Watch mode
```

## 🧩 UI Components

The frontend uses **shadcn/ui** components built on top of Tailwind CSS. Available components:

### Base Components
- `Button` - Primary, secondary, outline, ghost, destructive variants
- `Input` - Text input with focus states
- `Textarea` - Multi-line text input
- `Label` - Form labels
- `Select` - Dropdown select
- `Badge` - Status indicators
- `Card` - Content containers
- `Dialog` - Modal dialogs

### Custom Components
- `AuthPanel` - Supabase authentication
- `DocumentStudio` - CV/Resume form
- `TemplateGallery` - Template selection with preview
- `ResumeChecker` - ATS analysis tool
- `ApplicationTracker` - Kanban-style job application tracking
- `JobDiscovery` - Job search with filters
- `Chat` - AI conversation interface
- `Sidebar` - Chat session sidebar
- `PromptBox` - Chat input with attachments
- `ChatCanvas` - Message display
- `ArtifactPanel` - Document preview

## 🌐 Routing

The app uses a simple view-based routing in `App.jsx`:

- **Chat View** (default): AI conversation interface
- **Dashboard View**: Document generation and tools

Navigation between views is handled by the `view` state in `App.jsx`.

## 🌍 Internationalization (i18n)

Multi-language support with translations for:
- English (en)
- German (de)
- French (fr)

Translations are managed in `src/i18n/locales/` and accessed via the `useI18n()` hook.

## ⚡ Features

### AI Chat Platform
- Claude-style conversational workspace
- Session management with sidebar
- Model selection (auto or specific)
- PDF attachment for context
- Artifact preview for generated documents

### Document Generation
- CV generation with templates
- Cover letter generation
- Real-time preview

### ATS Resume Checker
- Upload CV PDF for text extraction
- Compare resume against job descriptions
- Get ATS optimization score

### Job Discovery
- Search multiple job providers
- CV-based ranking with RAG
- Save jobs to tracker
- Location and keyword filters

### Application Tracker
- Kanban-style pipeline (Applied → Interview → Offer → Rejected)
- Quick-add form
- Move cards between stages
- Delete applications

### Status System
- Global status banner
- Loading, success, error states
- Error boundary for crash recovery

## 🛠 Configuration

### Environment Variables

Create a `.env.local` file in the `frontend/` directory:

```bash
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://your-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-anon-key
```

### Vite Configuration

- **Port**: 5173
- **Host**: 0.0.0.0 (accessible from network)
- **Tailwind CSS**: Enabled via `@tailwindcss/vite` plugin

## 🎯 Architecture Decisions

### UI Library: shadcn/ui + Tailwind CSS

**Rationale:**
- ✅ Industry default for modern React apps (2026)
- ✅ High design freedom with accessible, production-ready components
- ✅ Tailwind-native with modern tooling
- ✅ No vendor lock-in (components are yours)
- ✅ Perfect for career/job-seeker product needing professional design

### State Management

- Local component state for form inputs
- Custom hooks (`useSession`, `useI18n`, `useStatus`, etc.)
- No external state management library needed

### Styling

- Tailwind CSS v4 with `@tailwindcss/vite` plugin
- CSS custom properties for theming
- Light and dark mode support
- Responsive design with mobile-first approach

## 📝 Component Hierarchy

```
App
├── ErrorBoundary
│   └── I18nProvider
│       └── StatusProvider
│           ├── Header (with branding and actions)
│           ├── AuthPanel
│           ├── Chat View
│           │   ├── Sidebar
│           │   │   ├── Session list
│           │   │   └── Model selector
│           │   ├── ChatCanvas (messages)
│           │   ├── PromptBox (input)
│           │   └── ArtifactPanel (preview)
│           └── Dashboard View
│               ├── DocumentStudio
│               ├── TemplateGallery
│               ├── ResumeChecker
│               ├── ApplicationTracker
│               └── JobDiscovery
└── StatusBanner
```

## 🔧 Customization

### Adding New Components

```bash
# Install shadcn/ui CLI
npm install -D shadcn

# Add a new component
npx shadcn@latest add button
```

### Theme Customization

Edit `tailwind.config.js` to modify colors, fonts, and other design tokens.

### Adding New Translations

1. Add a new locale file in `src/i18n/locales/` (e.g., `es.js`)
2. Import and add to the `locales` object in `src/i18n/index.jsx`

## 📊 Performance

- **Vite HMR**: Instant hot module replacement
- **Optimized Build**: ~460KB JavaScript, ~36KB CSS (gzipped)
- **Automatic JSX Runtime**: No need for `import React` in every file

## 🚨 Error Handling

- **ErrorBoundary**: Catches render errors at the root level
- **Status System**: Global error reporting via `useStatus()`
- **Individual Component Errors**: Each component handles its own errors gracefully

## 📄 License

MIT License - Feel free to use and modify as needed.

---

**Built with:**
- React 18
- Vite 5
- Tailwind CSS 4
- shadcn/ui
- Supabase (Auth)
