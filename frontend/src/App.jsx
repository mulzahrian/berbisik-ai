import { useEffect, useRef, useState } from 'react'
import './App.css'

const MAX_CHARS = 4000
const SAMPLE_TEXT = `[serious] Dinding itu sudah berdiri selama seratus tahun. [curious] Tapi apa yang sebenarnya menunggu di balik dinding itu?

[intense] Lalu tanah mulai bergetar. [dramatic] Sebuah bayangan raksasa muncul di atas dinding. [pause] [powerful] Dan umat manusia kembali mengingat rasa takut.`

const TAG_LABELS = {
  neutral: 'Netral', calm: 'Tenang', soft: 'Lembut', whisper: 'Berbisik', sad: 'Sedih', serious: 'Serius',
  mysterious: 'Misterius', curious: 'Penasaran', happy: 'Senang', excited: 'Bersemangat', energetic: 'Energik',
  intense: 'Intens', angry: 'Marah', dramatic: 'Dramatis', powerful: 'Kuat', epic: 'Epik',
}

const ICONS = {
  spark: 'M12 3l1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7L12 3Zm6.5 12.5.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2Z',
  waveform: 'M3 12h2.2l1.4-6 2.8 12 1.8-8 1.8 5.5 1.6-3.5H21',
  library: 'M4 5.5A2.5 2.5 0 0 1 6.5 3H20v16H6.5A2.5 2.5 0 0 0 4 21.5v-16ZM4 18.5A2.5 2.5 0 0 1 6.5 16H20',
  folder: 'M3 6.5A2.5 2.5 0 0 1 5.5 4H10l2 2h6.5A2.5 2.5 0 0 1 21 8.5v7A2.5 2.5 0 0 1 18.5 18h-13A2.5 2.5 0 0 1 3 15.5v-9Z',
  history: 'M4 12a8 8 0 1 0 2.3-5.6L4 8.7M4 4v4.7h4.7M12 7v5l3.5 2',
  settings: 'M12 15.2a3.2 3.2 0 1 0 0-6.4 3.2 3.2 0 0 0 0 6.4Zm7.3-3.2a7.5 7.5 0 0 0-.1-1.2l1.8-1.4-1.8-3.1-2.2.9a8 8 0 0 0-2-1.2L14.7 3h-3.5l-.3 2.3a8 8 0 0 0-2 1.2l-2.2-.9-1.8 3.1 1.8 1.4a7.5 7.5 0 0 0 0 2.4l-1.8 1.4 1.8 3.1 2.2-.9a8 8 0 0 0 2 1.2l.3 2.3h3.5l.3-2.3a8 8 0 0 0 2-1.2l2.2.9 1.8-3.1-1.8-1.4c.1-.4.1-.8.1-1.2Z',
  help: 'M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18Zm-2.2-10.2a2.3 2.3 0 1 1 4.1 1.4c-.8.9-1.9 1.2-1.9 2.6M12 17.8v.1',
  chevron: 'm7 9 5 5 5-5', download: 'M12 3v11m0 0 4-4m-4 4-4-4M4 17v1.5A2.5 2.5 0 0 0 6.5 21h11a2.5 2.5 0 0 0 2.5-2.5V17',
  play: 'm9 6 9 6-9 6V6Z', stop: 'M6 6h12v12H6z', plus: 'M12 5v14M5 12h14',
}

function Icon({ name, size = 18, strokeWidth = 1.8 }) {
  return <svg aria-hidden="true" className="icon" width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={strokeWidth} strokeLinecap="round" strokeLinejoin="round"><path d={ICONS[name]} /></svg>
}

function fmtTime(sec) {
  if (sec == null) return '–'
  const s = Math.round(sec)
  const m = Math.floor(s / 60)
  return m ? `${m}m ${s % 60}d` : `${s}d`
}

async function api(path, options) {
  const res = await fetch(path, options)
  if (!res.ok) {
    let msg = res.statusText
    try {
      const body = await res.json()
      msg = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch { /* not json */ }
    throw new Error(msg)
  }
  return res.json()
}

export default function App() {
  const [server, setServer] = useState(null)
  const [serverDown, setServerDown] = useState(false)
  const [text, setText] = useState(() => localStorage.getItem('tts-text') ?? SAMPLE_TEXT)
  const [language, setLanguage] = useState(() => localStorage.getItem('tts-lang-v2') ?? 'id')
  const [voice, setVoice] = useState('')
  const [job, setJob] = useState(null)
  const [error, setError] = useState('')
  const [history, setHistory] = useState([])
  const [pollKey, setPollKey] = useState(0)
  const textRef = useRef(null)

  useEffect(() => localStorage.setItem('tts-text', text), [text])
  useEffect(() => localStorage.setItem('tts-lang-v2', language), [language])

  useEffect(() => {
    let timer
    const poll = async () => {
      try {
        const s = await api('/api/status')
        setServer(s); setServerDown(false); setVoice((v) => v || s.voices[0] || '')
        if (s.model !== 'ready' && s.model !== 'error') timer = setTimeout(poll, 2000)
      } catch { setServerDown(true); timer = setTimeout(poll, 3000) }
    }
    poll()
    return () => clearTimeout(timer)
  }, [pollKey])

  const activeModel = server?.active_model
  const modelLanguages = server?.models?.[activeModel]?.languages ?? { id: 'Bahasa Indonesia' }
  const lang = language in modelLanguages ? language : Object.keys(modelLanguages)[0]
  const running = job && (job.status === 'queued' || job.status === 'running')

  const switchModel = async (name) => {
    setError('')
    try {
      await api('/api/model', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ model: name }) })
      setServer((s) => ({ ...s, model: 'loading', active_model: name })); setPollKey((k) => k + 1)
    } catch (e) { setError(e.message) }
  }

  useEffect(() => {
    if (!running) return undefined
    const timer = setInterval(async () => {
      try {
        const j = await api(`/api/jobs/${job.id}`)
        setJob(j)
        if (j.status === 'done') setHistory((h) => [{ ...j, text: text.slice(0, 120), at: new Date() }, ...h].slice(0, 10))
        if (j.status === 'error') setError(j.error)
      } catch (e) { setError(e.message) }
    }, 1500)
    return () => clearInterval(timer)
  }, [running, job?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const insertTag = (tag) => {
    const el = textRef.current; const start = el?.selectionStart ?? text.length; const end = el?.selectionEnd ?? text.length; const insert = `[${tag}] `
    if (text.length - (end - start) + insert.length > MAX_CHARS) return
    setText(text.slice(0, start) + insert + text.slice(end))
    requestAnimationFrame(() => { el?.focus(); if (el) el.selectionStart = el.selectionEnd = start + insert.length })
  }

  const generate = async () => {
    setError('')
    try {
      const j = await api('/api/jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text, language: lang, voice, model: activeModel }) }); setJob(j)
    } catch (e) { setError(e.message) }
  }
  const cancel = async () => { if (job) setJob(await api(`/api/jobs/${job.id}`, { method: 'DELETE' })) }
  const ready = server?.model === 'ready'
  const progress = job?.total_chunks ? Math.round((job.done_chunks / job.total_chunks) * 100) : 0
  const tagsUsed = [...text.matchAll(/\[(.{1,40}?)\]/g)].map((m) => m[1].toLowerCase().trim())
  const inlineTags = server?.inline_tags ?? []
  const known = new Set([...(server?.styles ?? []), ...(server?.pause_tags ?? []), ...inlineTags, ...(inlineTags.length ? ['laugh', 'laughs', 'sighs'] : [])])
  const unknownTags = [...new Set(tagsUsed.filter((t) => server && !known.has(t)))]
  const refText = server?.voice_info?.[voice]?.ref_text
  const statusText = serverDown ? 'Backend belum tersambung' : !server ? 'Menghubungkan ke backend...' : server.model === 'loading' ? 'Memuat model AI...' : server.model === 'not_loaded' ? 'Menyiapkan model...' : server.model === 'ready' ? `Model siap · ${server.device?.toUpperCase()}` : `Gagal memuat model${server.error ? ` · ${server.error}` : ''}`

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand"><div className="brand-mark"><Icon name="waveform" size={22} /></div><span>berbisik<span className="brand-dot">.</span></span></div>
        <div className="sidebar-label">Workspace</div>
        <nav className="nav-list" aria-label="Navigasi utama"><button className="nav-item active"><Icon name="spark" /><span>Create</span></button><button className="nav-item"><Icon name="library" /><span>Voice library</span></button><button className="nav-item"><Icon name="folder" /><span>Projects</span><span className="nav-count">0</span></button><button className="nav-item"><Icon name="history" /><span>History</span></button></nav>
        <div className="sidebar-spacer" />
        <div className={`backend-card ${serverDown ? 'offline' : ready ? 'online' : ''}`}><span className="live-dot" /><div><strong>{ready ? 'Local engine ready' : serverDown ? 'Engine offline' : 'Connecting...'}</strong><small>{ready ? `${server.device?.toUpperCase() ?? 'CPU'} · private` : 'Check your backend'}</small></div></div>
        <button className="nav-item muted"><Icon name="settings" /><span>Settings</span></button><div className="profile-row"><div className="avatar">B</div><div><strong>Berbisik workspace</strong><small>Local account</small></div><span className="more">•••</span></div>
      </aside>

      <div className="main-shell">
        <header className="topbar"><div className="breadcrumbs"><span>Workspace</span><span>/</span><strong>Text to Speech</strong></div><div className="topbar-actions"><span className={`status-pill ${serverDown ? 'down' : ready ? 'ready' : 'loading'}`}><span className="status-dot" />{statusText}</span><button className="icon-button" aria-label="Help"><Icon name="help" size={19} /></button></div></header>
        <main className="workspace">
          <div className="page-heading"><div><p className="eyebrow">CREATE</p><h1>Text to Speech</h1><p className="page-subtitle">Turn your words into natural, expressive speech.</p></div><button className="new-project"><Icon name="plus" size={17} /> New project</button></div>
          <div className="studio-grid">
            <section className="editor-panel panel">
              <div className="panel-header"><div><h2>Script</h2><p>Write or paste your script below.</p></div><button className="small-button" type="button" onClick={() => setText('')}>Clear</button></div>
              <div className="editor-controls"><label className="control-field"><span>Model</span><div className="select-wrap"><select value={activeModel ?? ''} disabled={running || server?.model === 'loading'} onChange={(e) => switchModel(e.target.value)}>{Object.entries(server?.models ?? {}).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}</select><Icon name="chevron" size={15} /></div></label><label className="control-field"><span>Language</span><div className="select-wrap"><select value={lang} onChange={(e) => setLanguage(e.target.value)}>{Object.entries(modelLanguages).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select><Icon name="chevron" size={15} /></div></label><label className="control-field"><span>Voice</span><div className="select-wrap"><select value={voice} onChange={(e) => setVoice(e.target.value)}>{(server?.voices ?? []).map((v) => <option key={v}>{v}</option>)}</select><Icon name="chevron" size={15} /></div></label></div>
              {server && Object.keys(server.models ?? {}).length === 0 && <div className="inline-alert">Belum ada model di <code>{server.models_dir}</code>. Jalankan <code>download_models.py</code>.</div>}{refText && <div className="reference-note"><span>Reference transcript</span><em>“{refText}”</em></div>}
              <div className="script-editor"><textarea ref={textRef} value={text} maxLength={MAX_CHARS} onChange={(e) => setText(e.target.value)} placeholder="Start writing your script..." rows={14} /><div className="editor-footer"><span className={text.length >= MAX_CHARS ? 'limit' : ''}>{text.length.toLocaleString('id-ID')} / {MAX_CHARS.toLocaleString('id-ID')} characters</span>{unknownTags.length > 0 && <span className="warn">Unknown tag: {unknownTags.map((t) => `[${t}]`).join(' ')}</span>}</div></div>
              <div className="tag-toolbar"><div className="tag-heading"><span className="tag-icon"><Icon name="spark" size={14} /></span><span>Quick tags</span></div><div className="tag-list">{(server?.styles ?? Object.keys(TAG_LABELS)).filter((t) => t !== 'normal').slice(0, 10).map((t) => <button key={t} type="button" className="tag" onClick={() => insertTag(t)} title={TAG_LABELS[t]}>[{t}]</button>)}{(server?.pause_tags ?? ['pause', 'long pause']).map((t) => <button key={t} type="button" className="tag pause" onClick={() => insertTag(t)}>[{t}]</button>)}{inlineTags.map((t) => <button key={t} type="button" className="tag sfx" onClick={() => insertTag(t)}>[{t}]</button>)}</div></div>
              {server?.model === 'ready' && !server.supports_emotion && <div className="hint">Tag emosi mengatur tempo dan jeda. Pilih model Chatterbox untuk kontrol intensitas emosi penuh.</div>}
              <div className="generate-row"><div className="generate-info"><span className="keyboard-key">⌘</span><span>Enter to generate</span></div><div className="actions"><button className="primary" disabled={!ready || running || !text.trim()} onClick={generate}><Icon name={running ? 'stop' : 'play'} size={16} />{running ? 'Generating...' : 'Generate speech'}</button>{running && <button className="secondary" onClick={cancel}>Cancel</button>}</div></div>
              {error && <div className="error">⚠ {error}</div>}
              {job && <div className="job-output">{running && <><div className="progress-label"><span>{job.status === 'queued' ? `Waiting in queue (#${job.queue_position})` : `Generating audio · ${progress}%`}</span><span>{fmtTime(job.eta_sec)} remaining</span></div><div className="bar"><div style={{ width: `${progress}%` }} /></div>{job.current_text && <div className="current">🔊 {job.current_text}</div>}</>}{job.status === 'cancelled' && <div className="job-meta">Generation cancelled.</div>}{job.status === 'done' && <div className="result"><audio controls autoPlay src={`/api/jobs/${job.id}/audio?format=wav`} /><div className="job-meta">Duration {fmtTime(job.duration_sec)} · generated in {fmtTime(job.elapsed_sec)}</div><div className="downloads"><a className="btn" href={`/api/jobs/${job.id}/audio?format=mp3&download=true`}><Icon name="download" size={15} /> MP3</a><a className="btn ghost" href={`/api/jobs/${job.id}/audio?format=wav&download=true`}><Icon name="download" size={15} /> WAV</a></div></div>}</div>}
            </section>
            <aside className="right-column"><section className="settings-card panel"><div className="panel-header compact"><div><h2>Voice settings</h2><p>Fine-tune your output.</p></div><button className="icon-button subtle" aria-label="Settings"><Icon name="settings" size={17} /></button></div><div className="voice-preview"><div className="voice-avatar"><Icon name="waveform" size={20} /></div><div><strong>{voice || 'No voice selected'}</strong><span>{refText ? 'Custom reference voice' : 'Reference voice'}</span></div><span className="voice-status"><span className="status-dot" />Ready</span></div><div className="setting-row"><span>Voice consistency</span><span className="setting-value">Default</span></div><div className="setting-row"><span>Style</span><span className="setting-value">Expressive</span></div><div className="setting-row"><span>Output format</span><span className="setting-value">WAV · 44.1 kHz</span></div></section><section className="tips-card"><div className="tips-icon"><Icon name="spark" size={16} /></div><div><strong>Make it sound alive</strong><p>Use tags like <code>[curious]</code>, <code>[pause]</code>, or <code>[dramatic]</code> to shape the delivery.</p></div></section><section className="usage-card panel"><div className="usage-top"><div><p className="eyebrow">SESSION</p><h3>Local & private</h3></div><Icon name="settings" size={18} /></div><div className="usage-line"><span>Voice reference</span><strong>{voice || 'Not selected'}</strong></div><div className="usage-line"><span>Characters used</span><strong>{text.length.toLocaleString('id-ID')}</strong></div></section></aside>
          </div>
          {history.length > 1 && <section className="history-section panel"><div className="section-heading"><div><p className="eyebrow">RECENT</p><h2>Session history</h2></div><span>{history.length - 1} generations</span></div>{history.slice(1).map((h) => <div key={h.id} className="history-item"><div className="history-file"><div className="file-icon"><Icon name="waveform" size={17} /></div><div className="history-text"><strong>{h.text}…</strong><span>{h.at?.toLocaleTimeString?.([], { hour: '2-digit', minute: '2-digit' }) ?? 'Just now'}</span></div></div><audio controls src={`/api/jobs/${h.id}/audio?format=wav`} /><a className="history-download" href={`/api/jobs/${h.id}/audio?format=mp3&download=true`}><Icon name="download" size={15} /> MP3</a></div>)}</section>}
          <section className="help-section panel"><div className="section-heading"><div><p className="eyebrow">QUICK GUIDE</p><h2>Expressive tags</h2></div><Icon name="help" size={18} /></div><div className="help-content"><p>Tags apply to the text that follows until another tag is used.</p><pre>[serious] Dinding itu berdiri seratus tahun. [intense] Lalu tanah mulai bergetar! [pause] [powerful] Dan manusia kembali mengenal rasa takut.</pre></div></section>
        </main>
      </div>
    </div>
  )
}
