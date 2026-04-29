import { Component, type ReactNode } from 'react'

interface Props {
  children: ReactNode
  fallback?: ReactNode
}

interface State {
  hasError: boolean
  error: Error | null
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div className="h-screen flex items-center justify-center bg-surface-0">
          <div className="bg-surface-1 border border-red-900/30 rounded-xl p-8 w-[500px] text-center">
            <p className="text-2xl text-red-400 mb-2">Something went wrong</p>
            <p className="text-sm text-gray-400 mb-4">
              The Juniper encountered an unexpected error.
            </p>
            <pre className="bg-surface-0 rounded p-3 text-xs text-red-300 text-left overflow-auto max-h-[200px] border border-surface-3 mb-4">
              {this.state.error?.message || 'Unknown error'}
              {this.state.error?.stack && `\n\n${this.state.error.stack}`}
            </pre>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="bg-accent-blue hover:bg-blue-600 text-white font-medium py-2 px-6 rounded-lg transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
