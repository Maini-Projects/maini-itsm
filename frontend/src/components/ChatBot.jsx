import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { Dots } from './ui'

const START = ['How many open incidents are there?', 'Show the latest high priority incidents', 'When is the next release?', 'Which incidents are past their SLA?']

const load = () => { try { return JSON.parse(sessionStorage.getItem('itsm.chat')) || [] } catch { return [] } }

export default function ChatBot() {
  const { me } = useAuth()
  const [open, setOpen] = useState(false)
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirming, setConfirming] = useState(false)
  const [msgs, setMsgs] = useState(load)
  const end = useRef(null)
  useEffect(() => { try { sessionStorage.setItem('itsm.chat', JSON.stringify(msgs.slice(-40))) } catch { /* not kept */ } }, [msgs])
  useEffect(() => { if (open) end.current?.scrollIntoView({ block: 'end' }) }, [msgs, busy, open])

  const ask = async (q) => {
    const question = q.trim()
    if (!question || busy) return
    setText('')
    setMsgs((m) => [...m, { from: 'me', text: question }])
    setBusy(true)
    try {
      const r = await api.get('/assistant', { q: question })
      setMsgs((m) => [...m, { from: 'bot', text: r.answer, items: r.items, suggestions: r.suggestions }])
    } catch (e) {
      setMsgs((m) => [...m, { from: 'bot', text: e.message || 'Something went wrong. Please try again.' }])
    } finally { setBusy(false) }
  }

  return (
    <>
      {open && (
        <section className="chat" aria-label="Assistant">
          <header>
            <div><b>Assistant</b><span>Ask about tickets, releases and approvals</span></div>
            <button onClick={() => { setConfirming(false); setOpen(false) }} title="Minimize (keeps the conversation)" aria-label="Minimize assistant">–</button>
            <button onClick={() => setConfirming(true)} title="Close (ends the conversation)" aria-label="Close assistant">✕</button>
          </header>
          <div className="chat-body">
            <div className="msg bot">Hi {me.full_name.split(' ')[0]}! I can look things up for you. Try one of these:
              <div className="chips">{START.map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>
            </div>
            {msgs.map((m, i) => (
              <div key={i} className={`msg ${m.from}`}>
                {m.text}
                {m.items?.length > 0 && (
                  <ul>{m.items.map((it, j) => <li key={j}><Link to={it.to} onClick={() => setOpen(false)}>{it.label}</Link>{it.meta && <small> · {it.meta}</small>}</li>)}</ul>
                )}
                {m.suggestions?.length > 0 && <div className="chips">{m.suggestions.map((s) => <button key={s} onClick={() => ask(s)}>{s}</button>)}</div>}
              </div>
            ))}
            {busy && <div className="msg bot"><Dots /></div>}
            <div ref={end} />
          </div>
          <form onSubmit={(e) => { e.preventDefault(); ask(text) }}>
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask a question…" aria-label="Your question" maxLength={300} autoFocus />
            <button type="submit" disabled={busy || !text.trim()}>Send</button>
          </form>
          {confirming && (
            <div className="chat-confirm" role="alertdialog" aria-label="Close the assistant">
              <div>
                <b>Close the assistant?</b>
                <p>This ends the conversation and clears the history. Use minimize (–) to keep it.</p>
                <div className="row">
                  <button className="no" onClick={() => setConfirming(false)}>Keep chatting</button>
                  <button className="yes" onClick={() => { setMsgs([]); setConfirming(false); setOpen(false) }}>Yes, close</button>
                </div>
              </div>
            </div>
          )}
        </section>
      )}
      <button className="chat-fab" onClick={() => setOpen((o) => !o)} aria-label={open ? 'Minimize assistant' : 'Open assistant'}>
        {!open && msgs.length > 0 && <i className="chat-dot" title="Conversation in progress" />}
        {open ? '⌄' : (
          <svg viewBox="0 0 24 24" width="26" height="26" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M21 11.5a8.4 8.4 0 0 1-9 8.3 9 9 0 0 1-3.6-.8L3 21l1.9-4.9A8.2 8.2 0 0 1 3 11.5 8.5 8.5 0 0 1 12 3a8.5 8.5 0 0 1 9 8.5z" /></svg>
        )}
      </button>
    </>
  )
}
