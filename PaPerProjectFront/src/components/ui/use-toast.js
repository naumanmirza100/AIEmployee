import React, { useState, useEffect } from "react"
import { withSeverity } from "@/utils/messageSeverity"
import { ToastAction } from "@/components/ui/toast"

const TOAST_LIMIT = 1

let count = 0
function generateId() {
  count = (count + 1) % Number.MAX_VALUE
  return count.toString()
}

const toastStore = {
  state: {
    toasts: [],
  },
  listeners: [],
  
  getState: () => toastStore.state,
  
  setState: (nextState) => {
    if (typeof nextState === 'function') {
      toastStore.state = nextState(toastStore.state)
    } else {
      toastStore.state = { ...toastStore.state, ...nextState }
    }
    
    toastStore.listeners.forEach(listener => listener(toastStore.state))
  },
  
  subscribe: (listener) => {
    toastStore.listeners.push(listener)
    return () => {
      toastStore.listeners = toastStore.listeners.filter(l => l !== listener)
    }
  }
}

const API_KEYS_PAGE = '/company/settings/api-keys'

// "Add your own key in Settings → API Keys": a company login gets a button that goes there. The message
// that an agent's free AI allowance is used up gets a title that says so, not "Error".
function withKeysLink(props) {
  const text = typeof props.description === 'string' ? props.description : ''
  if (!/API Keys/i.test(text)) return props
  let isCompanyLogin = false
  try { isCompanyLogin = !!localStorage.getItem('company_auth_token') && !localStorage.getItem('auth_token') } catch { /* no storage */ }
  const title = /free AI allowance/i.test(text) && /^\s*(error|warning|oops)[!.]?\s*$/i.test(String(props.title || ''))
    ? 'Free AI allowance used up' : props.title
  if (!isCompanyLogin || props.action || window.location.pathname.startsWith(API_KEYS_PAGE)) return { ...props, title }
  const action = React.createElement(ToastAction, {
    altText: 'Open API Keys',
    'data-testid': 'toast-open-api-keys',
    onClick: () => window.location.assign(API_KEYS_PAGE),
  }, 'Open API Keys')
  return { ...props, title, action, duration: Math.max(props.duration || 0, 10000) }
}

export const toast = ({ ...given }) => {
  // Red only for real errors; a warning or refusal is shown in amber (see messageSeverity).
  const props = withKeysLink(withSeverity(given))
  const id = generateId()

  const update = (props) =>
    toastStore.setState((state) => ({
      ...state,
      toasts: state.toasts.map((t) =>
        t.id === id ? { ...t, ...props } : t
      ),
    }))

  const dismiss = () => toastStore.setState((state) => ({
    ...state,
    toasts: state.toasts.filter((t) => t.id !== id),
  }))

  toastStore.setState((state) => ({
    ...state,
    toasts: [
      { ...props, id, dismiss },
      ...state.toasts,
    ].slice(0, TOAST_LIMIT),
  }))

  return {
    id,
    dismiss,
    update,
  }
}

export function useToast() {
  const [state, setState] = useState(toastStore.getState())
  
  useEffect(() => {
    const unsubscribe = toastStore.subscribe((state) => {
      setState(state)
    })
    
    return unsubscribe
  }, [])
  
  useEffect(() => {
    const timeouts = []

    state.toasts.forEach((toast) => {
      if (toast.duration === Infinity) {
        return
      }

      const timeout = setTimeout(() => {
        toast.dismiss()
      }, toast.duration || 5000)

      timeouts.push(timeout)
    })

    return () => {
      timeouts.forEach((timeout) => clearTimeout(timeout))
    }
  }, [state.toasts])

  return {
    toast,
    toasts: state.toasts,
  }
}