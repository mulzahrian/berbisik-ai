# Berbisik AI

Berbisik AI adalah aplikasi **text-to-speech (TTS) lokal** dengan fitur **voice cloning**. Aplikasi ini mengubah teks menjadi audio menggunakan model AI yang berjalan di komputer sendiri, lalu meniru karakter suara dari file referensi di folder `ref/`.

Aplikasi ini tidak membutuhkan API key atau layanan cloud saat melakukan inferensi. Setelah model selesai diunduh, backend dapat dijalankan secara offline karena `start-backend.bat` mengaktifkan mode offline Hugging Face.

## Fitur utama

- Antarmuka web React + Vite.
- Backend FastAPI yang berjalan lokal.
- Voice cloning dari file `.mp3`, `.wav`, `.flac`, `.ogg`, atau `.m4a`.
- Dua adapter model yang tersedia:
  - **OmniVoice**: voice cloning multilingual, termasuk Bahasa Indonesia dan English.
  - **Chatterbox Indonesian**: model yang lebih cocok untuk kontrol emosi melalui tag.
- Tag teks seperti `[dramatic]`, `[serious]`, `[pause]`, dan `[laughter]`.
- Progress job, estimasi waktu, pembatalan job, dan riwayat sesi.
- Audio hasil generate dapat diputar langsung dan diunduh sebagai WAV atau MP3.
- Otomatis memilih CPU atau CUDA GPU melalui PyTorch.

> Catatan lisensi: selalu cek lisensi model dan gunakan voice cloning hanya dengan izin pemilik suara. OmniVoice pada konfigurasi ini memiliki lisensi non-komersial. Chatterbox memiliki lisensi dan kebijakan penggunaan tersendiri.

## Gambaran arsitektur

```text
Browser
  │
  │ React UI: teks, bahasa, voice, model, tag, progress
  ▼
Vite dev server :5173
  │  proxy /api → http://127.0.0.1:8000
  ▼
FastAPI backend :8000
  │
  ├─ GET  /api/status
  ├─ POST /api/jobs
  ├─ GET  /api/jobs/{id}
  ├─ DELETE /api/jobs/{id}
  └─ GET  /api/jobs/{id}/audio
       │
       ▼
  Job queue + worker thread
       │
       ▼
  Engine
       ├─ memilih device: cuda atau cpu
       ├─ memuat model dan reference voice
       ├─ memilih adapter berdasarkan model.json
       ├─ memecah teks menjadi chunk
       ├─ menjalankan model.generate()
       └─ menggabungkan audio, lalu membuat WAV/MP3
```

### Alur generate secara detail

1. Browser mengambil status backend melalui `GET /api/status`.
2. Backend memuat model default dari `backend/models/default.txt`.
3. User mengisi teks dan memilih bahasa, voice, serta model.
4. Frontend mengirim `POST /api/jobs`.
5. Backend memvalidasi teks, bahasa, voice, dan model, lalu membuat job dengan status `queued`.
6. Worker mengambil job dari queue dan mengubah status menjadi `running`.
7. `tags.py` memproses tag, memisahkan teks menjadi beberapa chunk, dan menghitung jeda.
8. `engine.py` memastikan reference voice sudah disiapkan.
9. Adapter model memanggil model TTS:
   - `OmniVoiceAdapter` memakai `VoiceClonePrompt`.
   - `ChatterboxAdapter` memakai conditioning voice.
10. Semua potongan audio digabungkan, dinormalisasi, lalu dikonversi menjadi WAV dan MP3.
11. Frontend melakukan polling `GET /api/jobs/{id}` sampai status menjadi `done` atau `error`.
12. Browser memainkan audio dari endpoint `/api/jobs/{id}/audio`.

Generate dilakukan di background worker, sehingga terminal tidak selalu mencetak tulisan `generate`. Terminal Uvicorn terutama mencetak request HTTP. Progress yang paling lengkap terlihat di UI atau melalui endpoint job.

## Struktur folder

```text
text-to-voice/
├─ backend/
│  ├─ app/
│  │  ├─ main.py          # FastAPI, API job, queue, worker
│  │  ├─ engine.py        # device, model loading, reference, output audio
│  │  ├─ adapters.py      # adapter Chatterbox dan OmniVoice
│  │  └─ tags.py          # parser tag gaya, efek suara, dan jeda
│  ├─ models/
│  │  ├─ default.txt      # model yang dipakai saat startup
│  │  ├─ omnivoice/
│  │  │  └─ model.json    # metadata dan konfigurasi OmniVoice
│  │  └─ chatterbox-id/
│  │     └─ model.json    # metadata dan konfigurasi Chatterbox
│  ├─ cache/               # reference clip dan voice prompt/conditioning
│  ├─ download_models.py   # download model ke backend/models/
│  ├─ requirements.txt     # dependency Python
│  └─ .venv/               # virtual environment lokal, tidak perlu di-commit
├─ frontend/
│  ├─ src/
│  │  ├─ App.jsx           # UI dan pemanggilan API
│  │  ├─ App.css           # styling
│  │  └─ main.jsx          # entry React
│  ├─ vite.config.js       # proxy /api ke backend
│  └─ package.json         # dependency dan script frontend
├─ ref/
│  └─ titan-chap-1.mp3     # contoh voice reference
├─ start.bat               # menjalankan backend dan frontend
├─ start-backend.bat       # menjalankan API FastAPI
├─ start-frontend.bat      # menjalankan Vite
└─ stop.bat                # menghentikan port 8000 dan 5173
```

Folder `backend/models/` berisi file model berukuran besar dan sebaiknya tidak dimasukkan ke Git. Folder `backend/cache/` dapat dibuat ulang jika dihapus.

## Persyaratan sistem

### Wajib

- Windows 10/11 atau OS yang mendukung Python dan PyTorch.
- Python 3.11 direkomendasikan untuk konfigurasi project ini.
- Git.
- Node.js dan npm untuk frontend.
- Ruang disk beberapa GB untuk virtual environment, model, dan cache.
- RAM yang cukup untuk model yang dipilih. OmniVoice dan Whisper dapat menggunakan beberapa GB RAM.

### Opsional tetapi sangat disarankan

- NVIDIA GPU yang mendukung CUDA.
- Driver NVIDIA terbaru.
- VRAM yang cukup untuk model. Jika VRAM tidak cukup, gunakan CPU atau konfigurasi device yang sesuai.

PyTorch menyediakan command berbeda untuk CPU dan CUDA. Pilih command sesuai platform di [PyTorch Start Locally](https://pytorch.org/get-started/locally/) atau lihat [daftar versi PyTorch sebelumnya](https://pytorch.org/get-started/previous-versions/).

## 1. Clone repository

Buka PowerShell atau Command Prompt:

```powershell
git clone <URL_REPOSITORY>
cd text-to-voice
```

Ganti `<URL_REPOSITORY>` dengan URL repository yang sebenarnya. Jika folder project sudah tersedia di komputer, langkah clone dapat dilewati.

Pastikan struktur folder benar:

```powershell
Get-ChildItem
```

Anda seharusnya melihat `backend`, `frontend`, `ref`, dan file `start.bat`.

## 2. Membuat virtual environment Python

Jalankan dari root project:

```powershell
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
```

Jika command `py -3.11` tidak tersedia, gunakan:

```powershell
python -m venv backend\.venv
```

## 3. Instalasi mode CPU

Gunakan ini jika tidak memiliki NVIDIA GPU atau memang ingin menjalankan semua inference di CPU:

```powershell
backend\.venv\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cpu torch==2.6.0 torchaudio==2.6.0
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
cd frontend
npm install
cd ..
```

Mode CPU tetap bekerja, tetapi generate jauh lebih lama. Untuk percobaan awal, gunakan teks satu atau dua kalimat.

## 4. Instalasi dengan NVIDIA GPU

1. Install atau update NVIDIA driver.
2. Pastikan GPU terlihat oleh Windows melalui `nvidia-smi`.
3. Hapus virtual environment lama jika sebelumnya memasang wheel CPU, lalu buat ulang:

```powershell
Remove-Item -Recurse -Force backend\.venv
py -3.11 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install --upgrade pip
```

4. Install PyTorch dengan CUDA. Contoh untuk PyTorch 2.6.0 + CUDA 12.6:

```powershell
backend\.venv\Scripts\python.exe -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu126
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
```

Jika driver/GPU Anda membutuhkan CUDA 11.8 atau 12.4, gunakan index URL yang sesuai dari [daftar resmi PyTorch 2.6.0](https://pytorch.org/get-started/previous-versions/). Tidak perlu memasang semua versi CUDA sekaligus.

5. Verifikasi bahwa PyTorch menggunakan GPU:

```powershell
backend\.venv\Scripts\python.exe -c "import torch; print(torch.__version__); print('CUDA:', torch.cuda.is_available()); print(torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU')"
```

Output yang diharapkan:

```text
CUDA: True
Nama GPU Anda
```

Kode backend akan memilih `cuda` secara otomatis jika `torch.cuda.is_available()` bernilai `True`. Jika output `False`, backend tetap berjalan di CPU.

## 5. Download model

Model tidak di-download oleh `start-backend.bat`. Script startup mengaktifkan `HF_HUB_OFFLINE=1`, sehingga model harus diunduh terlebih dahulu saat internet tersedia.

Dari root project:

```powershell
backend\.venv\Scripts\python.exe backend\download_models.py omnivoice chatterbox-id
```

Atau download hanya satu model:

```powershell
backend\.venv\Scripts\python.exe backend\download_models.py omnivoice
```

Script tersebut melakukan hal berikut:

- Mengunduh OmniVoice dari [k2-fsa/OmniVoice](https://huggingface.co/k2-fsa/OmniVoice).
- Mengunduh Whisper ASR yang digunakan untuk membuat transcript reference prompt.
- Mengunduh Chatterbox dari [ResembleAI/chatterbox](https://huggingface.co/ResembleAI/chatterbox).
- Mengunduh fine-tune Bahasa Indonesia dari [grandhigh/Chatterbox-TTS-Indonesian](https://huggingface.co/grandhigh/Chatterbox-TTS-Indonesian).
- Menyimpan semuanya ke `backend/models/`.

Referensi cara download model ke folder lokal dapat dilihat di [dokumentasi Hugging Face Hub](https://huggingface.co/docs/huggingface_hub/en/guides/download).

Jika download gagal, pastikan internet aktif dan jalankan ulang command yang sama. Setelah model selesai diunduh, backend dapat dijalankan offline.

## 6. Menambahkan voice reference

Letakkan file suara di folder `ref/`:

```text
ref/
├─ titan-chap-1.mp3
└─ suara-saya.wav
```

Nama file tanpa ekstensi akan muncul sebagai pilihan voice di UI.

Rekomendasi reference:

- Satu pembicara saja.
- Suara bersih, tanpa musik, echo, atau noise berat.
- Bahasa reference sebaiknya sama dengan bahasa output.
- Durasi efektif 3–10 detik untuk OmniVoice; project ini memilih potongan suara secara otomatis.
- Jika ingin output dramatis, reference sebaiknya juga memiliki intonasi dramatis.

Saat reference berubah, hapus cache voice agar dibuat ulang:

```powershell
Remove-Item -Recurse -Force backend\cache
```

Perintah tersebut hanya menghapus cache yang bisa dibuat ulang, bukan file model dan bukan file di `ref/`.

## 7. Menentukan model default

Model yang dipakai saat startup ditentukan oleh:

```text
backend/models/default.txt
```

Isi file tersebut dengan salah satu nama folder model:

```text
omnivoice
```

atau:

```text
chatterbox-id
```

Model juga dapat diganti melalui dropdown di UI. Backend menolak pergantian model ketika masih ada job yang sedang berjalan.

## 8. Menjalankan aplikasi

Cara paling mudah:

```powershell
start.bat
```

Atau jalankan secara terpisah:

```powershell
start-backend.bat
```

Backend tersedia di `http://127.0.0.1:8000`.

Terminal lain:

```powershell
start-frontend.bat
```

Frontend tersedia di `http://localhost:5173`.

Buka URL frontend di browser dan tunggu sampai status berubah menjadi **Model siap**. Startup pertama dapat memakan waktu karena model harus dimuat ke RAM atau VRAM.

Untuk menghentikan aplikasi:

```powershell
stop.bat
```

## 9. Tag teks dan perbedaan antar model

Contoh:

```text
[serious] Dinding itu sudah berdiri selama seratus tahun.
[dramatic] Lalu tanah mulai bergetar!
[pause] [powerful] Sebuah bayangan raksasa muncul di atas dinding.
```

Tag yang tersedia:

| Kategori | Tag |
| --- | --- |
| Gaya | `neutral`, `normal`, `calm`, `soft`, `whisper`, `sad`, `serious`, `mysterious`, `curious` |
| Energi | `happy`, `excited`, `energetic`, `intense`, `angry`, `dramatic`, `powerful`, `epic` |
| Jeda | `pause`, `short pause`, `long pause`, `beat`, `breath` |
| Inline OmniVoice | `laughter`, `sigh`, `confirmation-en`, `question-en`, dan beberapa tag lain yang terlihat di UI |

Perilaku tag bergantung pada adapter:

- **Chatterbox** memakai parameter style seperti exaggeration, cfg weight, temperature, dan pause.
- **OmniVoice** terutama mengikuti prosodi reference audio. Jeda tetap diproses, sedangkan tag emosi tidak otomatis menjadi kontrol emosi yang kuat pada adapter saat ini.
- Tag yang tidak dikenal akan dilewati dan ditampilkan sebagai peringatan di UI.

## 10. Menggunakan model lain

Project ini tidak bisa langsung memakai model TTS apa pun hanya dengan menaruh file checkpoint ke folder `models`. Model baru harus memiliki:

1. Adapter Python yang mengimplementasikan interface `BaseAdapter`.
2. Entry di `ADAPTERS` pada `backend/app/adapters.py`.
3. Folder model dengan `model.json`.
4. Implementasi `load()`, `prepare_voice()`, dan `synthesize()`.

Format minimal `model.json`:

```json
{
  "type": "nama_adapter",
  "label": "Nama model",
  "languages": {
    "id": "Bahasa Indonesia"
  },
  "license": "Lisensi model"
}
```

Contoh repository/model untuk dipelajari:

- [OmniVoice resmi](https://github.com/k2-fsa/OmniVoice) — multilingual zero-shot voice cloning.
- [OmniVoice di Hugging Face](https://huggingface.co/k2-fsa/OmniVoice) — checkpoint model.
- [Chatterbox resmi](https://github.com/resemble-ai/chatterbox) — open-source TTS dan voice cloning.
- [Chatterbox di Hugging Face](https://huggingface.co/ResembleAI/chatterbox) — checkpoint model resmi.
- [Hugging Face Text-to-Speech models](https://huggingface.co/models?pipeline_tag=text-to-speech) — daftar model TTS umum.

Perhatikan bahwa repository resmi Chatterbox menyatakan proyek tersebut sudah menjadi arsip penelitian dan tidak lagi dipelihara sejak Agustus 2026. Model lokal yang sudah diunduh tetap dapat digunakan oleh project ini, tetapi jangan menganggap repository tersebut akan menerima perbaikan atau update baru.

Jangan menyalin checkpoint model lain ke folder `omnivoice` atau `chatterbox-id` karena format, tokenizer, sampling rate, dan cara conditioning dapat berbeda. Buat adapter terpisah supaya model yang sudah ada tetap aman.

## 11. API backend

### Status

```http
GET /api/status
```

Mengembalikan status model, device, model yang tersedia, voice, bahasa, tag, dan informasi reference voice.

### Membuat job

```http
POST /api/jobs
Content-Type: application/json
```

Contoh body:

```json
{
  "text": "Halo, ini adalah tes suara.",
  "language": "id",
  "voice": "titan-chap-1",
  "model": "omnivoice",
  "seed": 42
}
```

### Melihat progress

```http
GET /api/jobs/{job_id}
```

Status job dapat berupa `queued`, `running`, `done`, `error`, atau `cancelled`.

### Membatalkan job

```http
DELETE /api/jobs/{job_id}
```

### Mengambil audio

```http
GET /api/jobs/{job_id}/audio?format=wav
GET /api/jobs/{job_id}/audio?format=mp3&download=true
```

## 12. Troubleshooting

### Website mengatakan backend belum jalan

Pastikan `start-backend.bat` sedang berjalan dan buka `http://localhost:5173`, bukan file HTML secara langsung. Tes backend:

```powershell
Invoke-RestMethod http://127.0.0.1:8000/api/status
```

### Model tidak ditemukan

Pastikan folder berikut memiliki `model.json`:

```text
backend/models/omnivoice/model.json
backend/models/chatterbox-id/model.json
```

Jika belum ada, jalankan `download_models.py` saat internet aktif.

### Backend berjalan tetapi generation sangat lama

Periksa field `device` pada `/api/status`. Jika nilainya `cpu`, inference berjalan di CPU. Teks 4000 karakter memang dapat membutuhkan waktu lama. Gunakan GPU CUDA atau tes dengan teks pendek terlebih dahulu.

### CUDA tidak terdeteksi

```powershell
backend\.venv\Scripts\python.exe -c "import torch; print(torch.cuda.is_available()); print(torch.__version__)"
```

Jika `False`, kemungkinan wheel CPU masih terpasang, driver belum benar, atau versi CUDA/PyTorch tidak cocok. Install ulang wheel PyTorch CUDA dari halaman resmi PyTorch.

### Audio terdengar terlalu AI atau intonasi kurang

- Gunakan reference audio yang bersih dan memiliki gaya bicara yang ingin ditiru.
- Pastikan bahasa reference dan target sama jika ingin pengucapan lebih stabil.
- Tambahkan tanda baca dan pecah kalimat panjang.
- Gunakan Chatterbox jika prioritasnya kontrol emosi melalui tag.
- Untuk OmniVoice, ingat bahwa reference audio sangat memengaruhi ritme dan intonasi.

### Reference voice tidak berubah setelah mengganti file

Hapus cache lalu restart backend:

```powershell
Remove-Item -Recurse -Force backend\cache
```

## 13. Catatan lisensi dan keamanan

- Jangan clone suara orang lain tanpa persetujuan.
- Jangan gunakan hasil voice cloning untuk penipuan, impersonasi, atau penyamaran identitas.
- Baca lisensi setiap checkpoint sebelum penggunaan komersial.
- Model dan cache berukuran besar; jangan memasukkannya ke commit Git kecuali memang diperlukan.

## Referensi resmi

- [OmniVoice GitHub](https://github.com/k2-fsa/OmniVoice)
- [OmniVoice Hugging Face](https://huggingface.co/k2-fsa/OmniVoice)
- [Chatterbox GitHub](https://github.com/resemble-ai/chatterbox)
- [PyTorch Start Locally](https://pytorch.org/get-started/locally/)
- [PyTorch Previous Versions](https://pytorch.org/get-started/previous-versions/)
- [Hugging Face Hub download guide](https://huggingface.co/docs/huggingface_hub/en/guides/download)

