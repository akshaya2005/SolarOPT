import { Component } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.jsx'

class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('SolarOPT Dashboard Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '40px', fontFamily: 'system-ui, sans-serif', maxWidth: '800px', margin: '40px auto', background: '#fef2f2', border: '1px solid #fecaca', borderRadius: '12px' }}>
          <h2 style={{ color: '#991b1b', marginTop: 0 }}>SolarOPT Encountered a Runtime Error</h2>
          <p style={{ color: '#7f1d1d' }}>{this.state.error?.message || String(this.state.error)}</p>
          <pre style={{ background: '#ffffff', padding: '16px', borderRadius: '8px', overflow: 'auto', fontSize: '12px', color: '#334155' }}>
            {this.state.error?.stack}
          </pre>
          <button
            type="button"
            onClick={() => window.location.reload()}
            style={{ marginTop: '16px', padding: '10px 18px', background: '#dc2626', color: '#ffffff', border: 'none', borderRadius: '6px', cursor: 'pointer', fontWeight: 600 }}
          >
            Reload Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

createRoot(document.getElementById('root')).render(
  <ErrorBoundary>
    <App />
  </ErrorBoundary>,
)
