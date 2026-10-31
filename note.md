# Build: GitHub Daily Auto Commit Bot

Bertindak sebagai Senior Software Engineer dan DevOps Engineer. Bangun sebuah project bernama **GitHub Daily Automation Bot** yang dapat menjalankan aktivitas maintenance repository secara otomatis setiap hari dan melakukan commit serta push ke GitHub apabila terdapat perubahan yang benar-benar diperlukan.

## 1. Tujuan Utama

Saya ingin sistem otomatisasi GitHub yang:
- Berjalan otomatis setiap hari tanpa perlu menjalankan script secara manual.
- Tidak membutuhkan laptop atau komputer lokal dalam keadaan menyala.
- Dapat melakukan commit dan push ke repository GitHub.
- Berjalan stabil dalam jangka panjang.
- Memiliki mekanisme error handling, logging, dan monitoring.
- Menghindari aktivitas commit palsu atau spam.

Bebas memilih bahasa pemrograman dan arsitektur terbaik. Prioritaskan solusi yang ringan, stabil, gratis untuk penggunaan wajar, dan mudah dipelihara.

## 2. Teknologi

Prioritaskan:
- Python 3.12+
- GitHub Actions untuk scheduler dan cloud execution.
- GitHub REST API jika memang diperlukan.
- Git untuk commit dan push.
- GitHub Secrets untuk konfigurasi sensitif.

Boleh menggunakan teknologi lain jika memiliki alasan teknis yang lebih baik.

## 3. Fitur Utama

### A. Daily Automation
- Jalankan workflow secara otomatis setiap hari.
- Gunakan cron scheduler GitHub Actions.
- Gunakan zona waktu Asia/Jakarta sebagai acuan.
- Sediakan manual trigger sebagai opsi tambahan.
- Pastikan workflow tetap berjalan tanpa komputer lokal aktif.

### B. Intelligent Commit
- Periksa kondisi repository sebelum melakukan commit.
- Lakukan maintenance yang relevan dan benar-benar diperlukan.
- Commit hanya apabila terdapat perubahan nyata dan bermakna.
- Jangan membuat empty commit.
- Jangan membuat perubahan file artifisial hanya untuk menghasilkan kotak hijau.
- Jangan membuat commit berulang apabila tidak ada perubahan.
- Gunakan commit message konvensional seperti:
  - chore: automated maintenance
  - fix: automated maintenance correction
  - docs: update project documentation
  - test: update automated test coverage

### C. Git Automation
- Otomatis melakukan git fetch sebelum maintenance.
- Pastikan branch yang digunakan adalah branch default repository.
- Periksa konflik sebelum push.
- Jangan menggunakan force push.
- Tangani kegagalan push dengan aman.
- Hindari mengubah histori commit yang sudah ada.

### D. Reliability
- Implementasikan logging.
- Implementasikan retry dengan exponential backoff untuk kegagalan sementara.
- Implementasikan timeout.
- Hindari concurrent workflow yang menyebabkan konflik.
- Buat laporan status eksekusi.
- Tangani API rate limit GitHub.
- Pastikan kegagalan satu eksekusi tidak merusak repository.

## 4. GitHub Actions

Buat workflow:
`.github/workflows/daily-automation.yml`

Persyaratan:
- Scheduled execution setiap hari pukul 00.00 WIB.
- Gunakan GitHub-hosted runner.
- Gunakan permissions seminimal mungkin.
- Gunakan GITHUB_TOKEN bawaan jika cukup.
- Jangan menaruh token atau credential di source code.
- Gunakan actions dengan versi stabil dan aman.
- Sediakan workflow_dispatch.
- Tambahkan concurrency control.
- Pastikan workflow dapat berjalan secara independen.

## 5. Security

Prioritaskan keamanan:
- Tidak menggunakan token hardcoded.
- Tidak mengekspos secrets di log.
- Tidak mengubah file di luar direktori project.
- Tidak menghapus data repository secara otomatis.
- Tidak menjalankan perintah berbahaya.
- Tidak menggunakan backdated commit untuk memanipulasi contribution graph.
- Tidak melakukan spam commit atau push.
- Patuhi GitHub Terms of Service dan Acceptable Use Policies.

## 6. Monitoring

Sediakan:
- Log waktu eksekusi.
- Status sukses atau gagal.
- Jumlah file yang berubah.
- Commit SHA apabila berhasil.
- Ringkasan hasil maintenance.
- Mekanisme notifikasi opsional jika workflow gagal.

## 7. Struktur Project

Buat struktur project yang bersih dan profesional sesuai arsitektur pilihanmu.

Pisahkan:
- Core automation.
- Git operations.
- Scheduler/workflow.
- Configuration.
- Logging.
- Tests.
- Documentation.

Tambahkan README.md yang menjelaskan instalasi, konfigurasi, cara kerja, keamanan, dan troubleshooting.

## 8. Testing

Sebelum menyelesaikan project:
- Jalankan unit tests.
- Uji deteksi perubahan file.
- Uji kondisi tidak ada perubahan.
- Uji kegagalan Git push.
- Uji validasi konfigurasi.
- Validasi file GitHub Actions.
- Pastikan tidak ada credential yang bocor.

## 9. Deployment

Saya menggunakan Windows sebagai komputer lokal dan GitHub sebagai remote repository.

Buat panduan:
1. Instalasi dependency.
2. Konfigurasi project.
3. Membuat repository GitHub.
4. Menghubungkan remote.
5. Push pertama.
6. Mengaktifkan GitHub Actions.
7. Menguji workflow.
8. Memastikan scheduler berjalan otomatis.
9. Troubleshooting.

Minimalkan konfigurasi manual.

## 10. Acceptance Criteria

Project dianggap selesai apabila:
- Bisa dijalankan di GitHub Actions.
- Workflow berjalan otomatis setiap hari.
- Tidak membutuhkan laptop menyala.
- Bisa melakukan commit dan push ketika ada perubahan maintenance yang nyata.
- Tidak membuat commit kosong atau perubahan artifisial.
- Tidak melakukan force push.
- Tidak membutuhkan eksekusi manual harian.
- Dokumentasi lengkap.
- Semua pengujian berhasil.

## Instruksi Pengerjaan

Jangan hanya membuat contoh kode atau prototype.

Bangun project secara lengkap, implementasikan semua file, jalankan testing, perbaiki error, validasi workflow, dan siapkan project agar siap di-push ke GitHub.

Jangan mengarang keberhasilan testing. Laporkan hasil pengujian yang benar-benar sudah dijalankan.

Jika ada keputusan teknis yang belum ditentukan, pilih pendekatan paling aman dan sederhana.