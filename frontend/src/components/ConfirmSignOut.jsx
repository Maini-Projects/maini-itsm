import { useEffect } from 'react'
import { useAuth } from '../auth'

// Asks before signing out, so a stray click does not end the session
export default function ConfirmSignOut({ onClose }) {
  const { signOut } = useAuth()
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modalwrap" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="confirm" role="alertdialog" aria-modal="true" aria-label="Sign out">
        <div className="confirm-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" /><path d="M16 17l5-5-5-5" /><path d="M21 12H9" /></svg>
        </div>
        <h3>Sign out?</h3>
        <p>You'll need to sign in again to continue.</p>
        <div className="confirm-actions">
          <button type="button" className="stay" onClick={onClose} autoFocus>Stay signed in</button>
          <button type="button" className="out" onClick={signOut}>Sign out</button>
        </div>
      </div>
    </div>
  )
}
