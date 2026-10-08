# Verifikasi Pembenahan 1 — Clipper Studio 4.0.7

- 98 tes Python lulus: 20 regresi pembenahan, 73 regresi gaya/service/workflow, dan 5 tes installer/paket.
- Tiga pemeriksaan Node lulus: status antrean/component caption, transkrip Tahap 3, dan workspace Tahap 6.
- Tes installer dijalankan kembali setelah resolusi WORK_DIR disamakan dengan urutan .env/.env.pro aplikasi; lima tes lulus.
- Semua payload Python lolos AST parse. Entry Remotion memakai JavaScript dan lolos pemeriksaan sintaks Node.
- FFmpeg/libass asli membuktikan toggle backdrop mengubah piksel dan video clean bebas overlay/sisipan sementara final mempertahankan overlay.
- SQLite/service/worker asli membuktikan kamus baru memperoleh take tampilan baru, cache reuse tetap stabil, dan koreksi manual bertahan pada lineage yang terverifikasi.
- NumPy float64 nyata mereproduksi error validator lama; adapter baru mempertahankan angka dan mengubah tipe menjadi float Python. Hasil CTC valid diterima; nilai invalid, overlap dan skor tanpa bukti tetap ditolak.
- Proyek Motion Canvas generated mempunyai request.json yang dapat diresolusikan dari kedua modul src. Browser/build renderer tersebut belum dijalankan.
- Installer diuji pada fixture sementara: checksum/konflik/path traversal, copy kode, backup SQLite, pemasangan ulang, kegagalan post-probe, dan rollback. Probe Python target dipalsukan pada tes fixture; belum merupakan uji Windows.

Model ASR/CTC nyata, Remotion/Motion Canvas browser, native CapCut/Resolve dan GPU laptop belum dieksekusi. Data model pada tes hanyalah fixture yang dikendalikan; bukan pengukuran akurasi bahasa Indonesia. Framing/cerita/tipografi kreatif masih dikerjakan pada tahap 2–5.

Log check-1 memuat paket fixture dengan commit nol sebagai data tes. Manifest paket rilis yang diberikan memakai commit sumber lokal lengkap.
