import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { api, hasSession, onSession } from './api'

const AuthContext = createContext(null)
export const useAuth = () => useContext(AuthContext)

export function AuthProvider({ children }) {
  const [me, setMe] = useState(null)
  const [state, setState] = useState(hasSession() ? 'loading' : 'out') // loading | in | out
  const [counts, setCounts] = useState(null)

  const loadMe = useCallback(async () => {
    try {
      setMe(await api.get('/me'))
      setState('in')
    } catch (e) {
      if (e.status === 401 || e.status === 403) api.logout()
      setState('out')
    }
  }, [])

  useEffect(() => { if (hasSession()) loadMe() }, [loadMe])
  useEffect(() => onSession((s) => { if (!s) { setMe(null); setCounts(null); setState('out') } }), [])

  const refreshCounts = useCallback(async () => {
    try { setCounts(await api.get('/dashboard/summary')) } catch { /* the sidebar just shows no numbers */ }
  }, [])
  useEffect(() => { if (state === 'in') refreshCounts() }, [state, refreshCounts])

  const signIn = async (email, password) => {
    await api.login(email, password)
    setState('loading')
    await loadMe()
  }

  return (
    <AuthContext.Provider value={{ me, state, signIn, signOut: api.logout, counts, refreshCounts }}>
      {children}
    </AuthContext.Provider>
  )
}
