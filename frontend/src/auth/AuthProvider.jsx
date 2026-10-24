import { useCallback, useEffect, useState } from 'react'
import { authApi } from '../api/client'
import { AuthContext } from './context'

async function restore() {
  try {
    return { status: 'authenticated', user: await authApi.me(), error: null }
  } catch (error) {
    if (error.status === 401 || error.status === 403) return { status: 'anonymous', user: null, error: null }
    return { status: 'error', user: null, error: error.message }
  }
}

export default function AuthProvider({ children }) {
  const [session, setSession] = useState({ status: 'loading', user: null, error: null })
  useEffect(() => {
    let active = true
    restore().then((result) => { if (active) setSession(result) })
    return () => { active = false }
  }, [])
  const retry = useCallback(async () => {
    setSession({ status: 'loading', user: null, error: null })
    setSession(await restore())
  }, [])

  async function login(data) {
    const user = await authApi.login(data)
    setSession({ status: 'authenticated', user, error: null })
  }
  async function logout() {
    await authApi.logout()
    setSession({ status: 'anonymous', user: null, error: null })
  }
  return <AuthContext.Provider value={{ ...session, retry, login, logout }}>{children}</AuthContext.Provider>
}
