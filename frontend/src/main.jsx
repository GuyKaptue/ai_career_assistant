import React, { Component } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import { I18nProvider } from './i18n';
import { StatusProvider } from './hooks/useStatus.jsx';
import { ThemeProvider, initializeTheme } from './hooks/useTheme';
import { ViewProvider } from './hooks/useView';
import { AuthDialogProvider } from './hooks/useAuthDialog';
import { SettingsDialogProvider } from './hooks/useSettingsDialog';
import { debugLog, installGlobalErrorCollector } from './lib/debug';
import './styles.css';

installGlobalErrorCollector();
initializeTheme();

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary" role="alert" aria-live="assertive">
          <h2>Something went wrong</h2>
          <p>{this.state.error?.message || 'An unexpected error occurred'}</p>
          <button onClick={() => this.setState({ hasError: false, error: null })}>
            Reload Application
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

debugLog('boot', 'mounting AI Career Assistant', {
  apiUrl: import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000 (default)',
  hasSupabaseUrl: Boolean(import.meta.env.VITE_SUPABASE_URL),
  hasSupabaseAnonKey: Boolean(import.meta.env.VITE_SUPABASE_ANON_KEY),
  hint: 'Values are never printed; only presence. If the UI stays blank, copy window.__ACA_DEBUG__.snapshot() — see docs/debugging/react-not-defined.md.',
});

const rootElement = document.getElementById('root');
if (!rootElement) {
  debugLog('boot', 'FATAL: #root element missing from index.html — cannot mount React tree');
  throw new Error('ACA boot failed: #root element missing (see [ACA:boot] debug line).');
}

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <ErrorBoundary>
      <ThemeProvider>
        <I18nProvider>
          <StatusProvider>
            <AuthDialogProvider>
              <SettingsDialogProvider>
                <ViewProvider>
                  <App />
                </ViewProvider>
              </SettingsDialogProvider>
            </AuthDialogProvider>
          </StatusProvider>
        </I18nProvider>
      </ThemeProvider>
    </ErrorBoundary>
  </React.StrictMode>,
);

debugLog('boot', 'React tree mounted successfully');
