import React from 'react';

class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    console.error('ErrorBoundary caught:', error, info?.componentStack);
  }

  render() {
    if (this.state.hasError) {
      const isDev = process.env.NODE_ENV === 'development';
      return (
        <div className="rounded-xl p-6 text-center" style={{ background: 'rgba(239,68,68,0.08)', border: '1px solid rgba(239,68,68,0.2)' }}>
          <p className="text-red-400 font-medium text-sm mb-1">This section failed to render</p>
          {isDev && this.state.error && (
            <p className="text-red-300/60 text-xs font-mono mb-3 break-all">{this.state.error.message}</p>
          )}
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="px-3 py-1.5 rounded-lg text-xs font-medium text-white transition-colors"
            style={{ background: 'rgba(124,58,237,0.7)' }}
          >
            Retry
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default ErrorBoundary;
