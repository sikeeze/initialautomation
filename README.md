# GitHub Daily Automation Bot

Bot pemeliharaan repository otomatis yang berjalan setiap hari di GitHub
Actions.  Melakukan maintenance yang nyata, dan commit + push hanya jika
ada perubahan yang benar-benar diperlukan.

## Cara Kerja

Setiap pukul 00:00 WIB (17:00 UTC), workflow GitHub Actions menjalankan
`run_daily.py`, yang mengeksekusi pipeline:

1.  `git fetch` — sinkronisasi dengan remote
2.  Validasi keadaan repo (branch default, tidak ada force push)
3.  Menjalankan task maintenance (lihat daftar di bawah)
4.  Mendeteksi perubahan nyata
5.  Commit + push hanya jika ada perubahan
6.  Membuat laporan status

Yang membuat ini bukan "spam commit bot":

-   **Tidak ada empty commit.** `git commit` dijalankan tanpa
    `--allow-empty`; jika tidak ada perubahan, tidak ada commit.
-   **Tidak ada perubahan artifisial.** Setiap task hanya menulis file
    jika menemukan masalah nyata (link mati, dependency usang, format
    tidak rapi). Jika semua sehat, tidak ada file yang disentuh.
-   **Tidak ada backdate.** Tidak ada fitur commit dengan tanggal masa
    lalu. Ini memang tidak akan mengisi contribution graph, tetapi
    backdate melanggar GitHub Terms of Service.
-   **Tidak ada force push.** Push biasa dengan retry exponential
    backoff; jika konflik tidak teratasi, push gagal aman.
-   **Concurrency control.** Workflow tidak bisa berjalan paralel.

## Task Maintenance

| Task | Frekuensi | Perubahan dibuat hanya jika...
|---|---|---|
| `dead-link-check` | harian | ...ditemukan link mati di markdown
| `stale-branch-report` | harian | ...daftar branch stale (>30 hari) berubah
| `format-check` | harian | ...ada file dengan trailing whitespace / tidak ada final newline
| `dependency-check` | harian | ...daftar dependency usang berubah
| `gitignore-hygiene` | harian | ...entry standar .gitignore hilang

## Struktur Project

```
run_daily.py                    # Entry point
src/config.py                   # Konfigurasi dari env + validasi
src/logging_utils.py            # Logging + sensor token + laporan status
src/git_ops.py                  # Fetch/commit/push, deteksi perubahan
src/maintenance.py              # Task maintenance
src/orchestrator                # Pipeline orchestration
tests/test_all.py               # Unit tests
.github/workflows/run_daily.yml # Scheduler GitHub Actions
```

## Instalasi & Deployment

### 1. Persiapan lokal

```bash
git clone https://github.com/sikeeze/initialautomation.git
cd initialautomation
python -m pip install -r requirements-dev.txt
```

### 2. Konfigurasi

Semua konfigurasi via environment variables. Tidak ada file config
manual, tidak ada token di source code.

| Variabel | Wajib | Default | Keterangan
|---|---|---|---
| `GITHUB_REPOSITORY` | ya | — | Format `owner/name`
| `GITHUB_TOKEN` | ya | — | Token otomatis dari Actions
| `GITHUB_WORKSPACE` | ya | — | Direktori checkout
| `INPUT_BRANCH` | tidak | `main` | Branch target
| `INPUT_DRY_RUN` | tidak | `false` | Stage tanpa commit/push
| `INPUT_RUN_LINK_CHECK` | tidak | `true` | Aktifkan dead link check
| `INPUT_RUN_STALE_BRANCH_REPORT` | tidak | `true` | Aktifkan laporan branch stale
| `INPUT_RUN_FORMAT_CHECK` | tidak | `true` | Aktifkan pemeriksaan format
| `INPUT_RUN_DEPENDENCY_CHECK` | tidak | `true` | Aktifkan cek dependency
| `INPUT_EXCLUDE_FILES` | tidak | `MAINTENANCE_REPORT.md` | File yang tidak distage
| `LOG_LEVEL` | tidak | `INFO` | Level logging

### 3. Setup GitHub

1.  Push project ini ke repository GitHub.
2.  Buka tab **Settings > Actions > General**.
3.  Pilih **Allow all actions**.
4.  Pastikan **Workflow permissions** = **Read and write permissions**.
5.  Klik **Enable**.

Token: `GITHUB_TOKEN` bawaan GitHub Actions cukup. Tidak perlu PAT.

### 4. Test workflow

**Opsi A: Manual trigger (paling cepat)**

1.  Buka tab **Actions**.
2.  Pilih workflow **Daily Automation**.
3.  Klik **Run workflow**.
4.  Pilih branch `main`, klik **Run workflow**.

**Opsi B: Lokal (dry run)**

```bash
export GITHUB_REPOSITORY="sikeeze/initialautomation"
export GITHUB_TOKEN="ghp_..."  # token GitHub Anda
export GITHUB_WORKSPACE="$PWD"
export INPUT_DRY_RUN=true
python run_daily.py
```

### 5. Verifikasi scheduler

Setelah aktif, workflow berjalan otomatis setiap hari pukul 00:00 WIB.
Cek tab **Actions** untuk histori eksekusi.

Anda bisa memverifikasi jadwal dengan melihat cron schedule di
`.github/workflows/run_daily.yml`:

```yaml
on:
  schedule:
    - cron: '0 17 * * *'  # 00:00 Asia/Jakarta (UTC+7)
```

## Monitoring

Setiap eksekusi menghasilkan:

-   Log di tab Actions
-   Ringkasan di GitHub Step Summary ($GITHUB_STEP_SUMMARY)
-   Laporan di `MAINTENANCE_REPORT.md` (jika ada perubahan)
-   Commit SHA + jumlah file berubah, jika ada commit

## Testing

```bash
python -m pytest tests/ -q
```

Menguji: validasi konfigurasi, deteksi perubahan, kondisi tanpa
perubahan, kegagalan git, redaksi kredensial, dan konstruksi commit
message.

## Keamanan

-   Token hanya dari GitHub Secrets / git credential helper, tidak
    hardcoded.
-   Semua log melalui `RedactingFormatter` yang menyensor pola token
    (`ghp_`, `gho_`, `ghs_`, `github_pat_`).
-   Permission minimal: `contents: write` (push), `metadata: read`.
-   Tidak ada force push, tidak ada rebase destruktif, tidak ada
    perubahan histori.
-   Tidak menjalankan perintah berbahaya; hanya `git` dan `pip list`.
-   Membatasi jumlah file per commit (`max_changes`) untuk mencegah
    perubahan masif tak terduga.
-   Tidak ada fitur backdate / manipulasi contribution graph.

## Troubleshooting

**Workflow tidak berjalan**

-   Cek tab Actions: apakah workflow ada dan enabled?
-   Cron GitHub bisa delay 5-15 menit; bukan error.
-   Repo dalam status dormant (60 hari tanpa activity) menjadwalkan
    workflow di-pause. Push commit manual untuk reaktivasi.

**Push gagal**

-   Cek log apakah "non-fast-forward". Bot akan retry 4x dengan
    backoff; jika masih gagal, gagal aman.
-   Solusi: pull manual di lokal, resolve konflik, push.

**"Branch lokal menyimpang"**

-   Ada commit di lokal yang belum di-remote. Push manual sekali,
    lalu biarkan bot bekerja.

## Lisensi

MIT
