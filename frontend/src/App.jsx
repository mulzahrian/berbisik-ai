import { useEffect, useRef, useState } from 'react'
import './App.css'

const MAX_CHARS = 4000
const SAMPLE_TEXT = `[serious] Dinding itu sudah berdiri selama seratus tahun. [curious] Tapi apa yang sebenarnya menunggu di balik dinding itu?

[intense] Lalu tanah mulai bergetar. [dramatic] Sebuah bayangan raksasa muncul di atas dinding. [pause] [powerful] Dan umat manusia kembali mengingat rasa takut.`

const TAG_LABELS = {
  neutral: 'Netral',
  calm: 'Tenang',
  soft: 'Lembut',
  whisper: 'Berbisik',
  sad: 'Sedih',
  serious: 'Serius',
  mysterious: 'Misterius',
  curious: 'Penasaran',
  happy: 'Senang',
  excited: 'Bersemangat',
  energetic: 'Energik',
  intense: 'Intens',
  angry: 'Marah',
  dramatic: 'Dramatis',
  powerful: 'Kuat',
  epic: 'Epik',
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
    } catch {
      /* not json */
    }
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
        setServer(s)
        setServerDown(false)
        setVoice((v) => v || s.voices[0] || '')
        if (s.model !== 'ready' && s.model !== 'error') timer = setTimeout(poll, 2000)
      } catch {
        setServerDown(true)
        timer = setTimeout(poll, 3000)
      }
    }
    poll()
    return () => clearTimeout(timer)
  }, [pollKey])

  const activeModel = server?.active_model
  const modelLanguages = server?.models?.[activeModel]?.languages ?? { id: 'Bahasa Indonesia' }
  const lang = language in modelLanguages ? language : Object.keys(modelLanguages)[0]

  const switchModel = async (name) => {
    setError('')
    try {
      await api('/api/model', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ model: name }),
      })
      setServer((s) => ({ ...s, model: 'loading', active_model: name }))
      setPollKey((k) => k + 1)
    } catch (e) {
      setError(e.message)
    }
  }

  const running = job && (job.status === 'queued' || job.status === 'running')

  useEffect(() => {
    if (!running) return
    const timer = setInterval(async () => {
      try {
        const j = await api(`/api/jobs/${job.id}`)
        setJob(j)
        if (j.status === 'done') {
          setHistory((h) => [{ ...j, text: text.slice(0, 120), at: new Date() }, ...h].slice(0, 10))
        }
        if (j.status === 'error') setError(j.error)
      } catch (e) {
        setError(e.message)
      }
    }, 1500)
    return () => clearInterval(timer)
  }, [running, job?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const insertTag = (tag) => {
    const el = textRef.current
    const start = el?.selectionStart ?? text.length
    const end = el?.selectionEnd ?? text.length
    const insert = `[${tag}] `
    if (text.length - (end - start) + insert.length > MAX_CHARS) return
    const next = text.slice(0, start) + insert + text.slice(end)
    setText(next)
    requestAnimationFrame(() => {
      el.focus()
      el.selectionStart = el.selectionEnd = start + insert.length
    })
  }

  const generate = async () => {
    setError('')
    try {
      const j = await api('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text, language: lang, voice, model: activeModel }),
      })
      setJob(j)
    } catch (e) {
      setError(e.message)
    }
  }

  const cancel = async () => {
    if (!job) return
    setJob(await api(`/api/jobs/${job.id}`, { method: 'DELETE' }))
  }

  const ready = server?.model === 'ready'
  const progress = job?.total_chunks ? Math.round((job.done_chunks / job.total_chunks) * 100) : 0
  const tagsUsed = [...text.matchAll(/\[([^[\]]{1,40})\]/g)].map((m) => m[1].toLowerCase().trim())
  const inlineTags = server?.inline_tags ?? []
  const known = new Set([
    ...(server?.styles ?? []),
    ...(server?.pause_tags ?? []),
    ...inlineTags,
    ...(inlineTags.length ? ['laugh', 'laughs', 'sighs'] : []),
  ])
  const unknownTags = [...new Set(tagsUsed.filter((t) => server && !known.has(t)))]
  const refText = server?.voice_info?.[voice]?.ref_text

  return (
    <div className="app">
      <header>
        <h1>🎙️ Berbisik AI</h1>
        <p className="sub">Text-to-speech lokal dengan kloning suara dari folder <code>ref/</code>. Gratis, tanpa API key.</p>
        <div className={`status ${serverDown ? 'down' : server?.model}`}>
          {serverDown && 'Backend belum jalan. Jalankan start-backend.bat'}
          {!serverDown && !server && 'Menghubungkan...'}
          {!serverDown && server?.model === 'loading' && 'Memuat model AI (bisa 1-3 menit)...'}
          {!serverDown && server?.model === 'not_loaded' && 'Menyiapkan model...'}
          {!serverDown && server?.model === 'ready' && `Model siap (${server.device?.toUpperCase()})`}
          {!serverDown && server?.model === 'error' && `Gagal memuat model: ${server.error}`}
        </div>
      </header>

      <section className="card">
        {server && Object.keys(server.models ?? {}).length === 0 && (
          <div className="error">Belum ada model di <code>{server.models_dir}</code>. Jalankan <code>download_models.py</code>.</div>
        )}
        <div className="row">
          <label>
            Model (dari backend/models)
            <select value={activeModel ?? ''} disabled={running || server?.model === 'loading'} onChange={(e) => switchModel(e.target.value)}>
              {Object.entries(server?.models ?? {}).map(([k, m]) => (
                <option key={k} value={k}>{m.label}</option>
              ))}
            </select>
          </label>
        </div>
        <div className="row">
          <label>
            Bahasa
            <select value={lang} onChange={(e) => setLanguage(e.target.value)}>
              {Object.entries(modelLanguages).map(([k, v]) => (
                <option key={k} value={k}>{v}</option>
              ))}
            </select>
          </label>
          <label>
            Suara (dari ref/)
            <select value={voice} onChange={(e) => setVoice(e.target.value)}>
              {(server?.voices ?? []).map((v) => <option key={v}>{v}</option>)}
            </select>
          </label>
        </div>
        {refText && (
          <div className="ref-text">
            Isi rekaman referensi (hasil transkripsi): <em>“{refText}”</em>
          </div>
        )}

        <div className="tags">
          <span className="tags-title">Gaya/emosi:</span>
          {(server?.styles ?? Object.keys(TAG_LABELS)).filter((t) => t !== 'normal').map((t) => (
            <button key={t} type="button" className="tag" onClick={() => insertTag(t)} title={TAG_LABELS[t]}>
              [{t}]
            </button>
          ))}
          <span className="tags-title">Jeda:</span>
          {(server?.pause_tags ?? ['pause', 'long pause']).map((t) => (
            <button key={t} type="button" className="tag pause" onClick={() => insertTag(t)}>[{t}]</button>
          ))}
          {inlineTags.length > 0 && <span className="tags-title">Suara efek:</span>}
          {inlineTags.map((t) => (
            <button key={t} type="button" className="tag sfx" onClick={() => insertTag(t)}>[{t}]</button>
          ))}
        </div>
        {server?.model === 'ready' && !server.supports_emotion && (
          <div className="hint">
            Model ini meniru intonasi rekaman referensi. Tag emosi mengatur tempo &amp; jeda; untuk kontrol
            intensitas emosi penuh pilih model Chatterbox.
          </div>
        )}

        <textarea
          ref={textRef}
          value={text}
          maxLength={MAX_CHARS}
          onChange={(e) => setText(e.target.value)}
          placeholder="Tulis teks di sini... Gunakan tag seperti [intense], [dramatic], [pause]"
          rows={14}
        />
        <div className="meta">
          <span className={text.length >= MAX_CHARS ? 'limit' : ''}>{text.length} / {MAX_CHARS} karakter</span>
          {unknownTags.length > 0 && (
            <span className="warn">Tag tidak dikenal (akan dilewati): {unknownTags.map((t) => `[${t}]`).join(' ')}</span>
          )}
        </div>

        <div className="actions">
          <button className="primary" disabled={!ready || running || !text.trim()} onClick={generate}>
            {running ? 'Sedang membuat suara...' : 'Generate Suara'}
          </button>
          {running && <button className="secondary" onClick={cancel}>Batal</button>}
        </div>

        {error && <div className="error">⚠️ {error}</div>}

        {job && (
          <div className="job">
            {running && (
              <>
                <div className="bar"><div style={{ width: `${progress}%` }} /></div>
                <div className="job-meta">
                  {job.status === 'queued'
                    ? `Menunggu antrian (#${job.queue_position})...`
                    : `Bagian ${job.done_chunks}/${job.total_chunks} • ${progress}% • berjalan ${fmtTime(job.elapsed_sec)} • sisa ±${fmtTime(job.eta_sec)}`}
                </div>
                {job.current_text && <div className="current">🔊 {job.current_text}</div>}
              </>
            )}
            {job.status === 'cancelled' && <div className="job-meta">Dibatalkan.</div>}
            {job.status === 'done' && (
              <div className="result">
                <audio controls autoPlay src={`/api/jobs/${job.id}/audio?format=wav`} />
                <div className="job-meta">Durasi {fmtTime(job.duration_sec)} • dibuat dalam {fmtTime(job.elapsed_sec)}</div>
                <div className="downloads">
                  <a className="btn" href={`/api/jobs/${job.id}/audio?format=mp3&download=true`}>⬇ Download MP3</a>
                  <a className="btn ghost" href={`/api/jobs/${job.id}/audio?format=wav&download=true`}>⬇ Download WAV</a>
                </div>
              </div>
            )}
          </div>
        )}
      </section>

      {history.length > 1 && (
        <section className="card">
          <h2>Riwayat sesi ini</h2>
          {history.slice(1).map((h) => (
            <div key={h.id} className="history-item">
              <div className="history-text">{h.text}…</div>
              <audio controls src={`/api/jobs/${h.id}/audio?format=wav`} />
              <a href={`/api/jobs/${h.id}/audio?format=mp3&download=true`}>MP3</a>
              <a href={`/api/jobs/${h.id}/audio?format=wav&download=true`}>WAV</a>
            </div>
          ))}
        </section>
      )}

      <section className="card help">
        <h2>Cara pakai tag</h2>
        <p>Tag gaya berlaku untuk teks setelahnya sampai tag berikutnya. Contoh:</p>
        <pre>[serious] Dinding itu berdiri seratus tahun. [intense] Lalu tanah mulai bergetar! [pause] [powerful] Dan manusia kembali mengenal rasa takut.</pre>
        <p>Tag emosi mengatur intensitas ekspresi suara (exaggeration), tempo, dan jeda. Tag jeda (<code>[pause]</code>, <code>[long pause]</code>) menambahkan hening.</p>
      </section>
    </div>
  )
}
