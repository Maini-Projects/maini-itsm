import { useState } from 'react'
import { api } from '../api'
import { Field, FormModal, useToast } from './ui'
import PasswordInput from './PasswordInput'

export default function ChangePassword({ onClose }) {
  const toast = useToast()
  const [cur, setCur] = useState(''), [next, setNext] = useState(''), [again, setAgain] = useState('')
  const submit = async () => {
    if (next !== again) throw new Error('The new passwords do not match.')
    await api.post('/auth/password', { current_password: cur, new_password: next })
    toast('Password changed.')
  }
  return (
    <FormModal title="Change password" submitLabel="Change password" onClose={onClose} onSubmit={submit} width={460}>
      <div className="form" style={{ gridTemplateColumns: '1fr' }}>
        <Field label="Current password"><PasswordInput value={cur} onChange={(e) => setCur(e.target.value)} autoComplete="current-password" required /></Field>
        <Field label="New password"><PasswordInput value={next} onChange={(e) => setNext(e.target.value)} minLength={8} autoComplete="new-password" required /></Field>
        <Field label="Repeat new password"><PasswordInput value={again} onChange={(e) => setAgain(e.target.value)} autoComplete="new-password" required /></Field>
      </div>
    </FormModal>
  )
}
