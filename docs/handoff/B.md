# Integrasi B 23–43 dan A 01–22

5 Oktober 2026. Branch `upgrade/combined-43`, berbasis A `6d8c6dc` di atas C0 `f67b032` dan Studio 3.3 `b477209`. Status: **versi uji integrasi**. B34 dan B36 belum memenuhi seluruh gate penerimaan karena editor desktop dan video acuan manusia belum tersedia dalam lingkungan pengujian.

Dokumen A sebelumnya adalah catatan serah terima sebelum integrasi. Sambungan produksi yang disebut tertunda di sana sekarang dilayani `StudioService`, `studio_worker`, `studio_exchange`, dan `/api/studio`; hasil final menyertakan envelope C0 aktual dari rencana render. Satu perubahan pada komponen A menambahkan akses draf agar refresh host tidak membuang suntingan.

| No. | Implementasi / bukti saat ini | Batas yang masih relevan |
|---|---|---|
| 23 | Jadwal B-roll memetakan semua shot, offset kontinu, alasan skip, ganti/nonaktifkan. Uji rentang 5–8 yang melintasi cut 6 menghasilkan 3 detik, offset 0 dan 1; juga pada render nyata. | Relevansi editorial B-roll perlu ditinjau pada sumber asli. |
| 24 | Empat resep menggabungkan tipografi, komposisi, ritme, ilustrasi, audio. | Resep bukan jaminan kesamaan visual dengan akun referensi. |
| 25 | Empat tahap utama tersambung ke API produksi. Uji browser lulus. | — |
| 26 | Pemutar besar, bentuk rasio, sumber/preview/final, revisi dan status stale. | — |
| 27 | Bantuan, contoh tipografi, dampak pengaturan, preview cepat/detail. | Contoh bukan simulasi semua isi video. |
| 28 | Lajur kata, subtitle, B-roll, komposisi, waveform; penyuntingan rentang dan aset lewat panel. | Penyuntingan melalui formulir; belum berupa drag trim multitrack. |
| 29 | Riwayat perubahan, undo dengan pemeriksaan konflik, dua pemutar pembanding artefak. | Preview yang sudah dibersihkan harus dibuat ulang. |
| 30 | Batch gaya, pengecualian manual, opsi menimpa eksplisit. Tes dua rasio lulus. | — |
| 31 | Hash isi penuh sumber/aset/font, tahap terpisah, preview 640/1280, cache final divalidasi. Cache reuse dan perubahan isi di tengah file diuji. | Mengubah beberapa parameter analisis dapat menginvalidasi lebih banyak preview secara konservatif. |
| 32 | Inventory pemilik/jenis/ukuran, pilihan cache saja, listing revision, batas opsional, proteksi sumber/aset/final. | Normalisasi sumber dan data analisis tidak dihapus lewat tombol preview. |
| 33 | LUFS/true peak diukur pada audio AAC final, normalisasi, limiter, ducking musik, fade sambungan, waveform. | Fixture sintetis lulus; kualitas dengar manusia dan musik asli belum dinilai. |
| 34 | Pembuat paket CapCut/Resolve dan pemeriksaan struktur berjalan dengan writer sebenarnya. | **Belum lulus gate native.** Impor dan bandingkan dengan Reference di kedua editor; catat versi. |
| 35 | Antrean satu proses berat, OCR CPU, pelepasan model antartahap, worker terpisah. | RTX 3050 4 GB / CUDA lokal belum diuji; model dapat jatuh ke CPU sesuai konfigurasi. |
| 36 | CLI/API benchmark WER/CER, istilah, angka/negasi, coverage cerita, duplikasi. | **Belum lulus gate mutu acuan.** Perlu sumber mentah, transkrip manusia, cerita acuan, penilaian visual dan waktu koreksi. |
| 37 | SQLite transaction, CAS revisi, operation ID idempotent, draf tersimpan. Tes API dan dua tab browser lulus. | Konflik membutuhkan tinjauan eksplisit sebelum simpan ulang. |
| 38 | MediaContext, rotasi/SAR, waktu nol, VFR→CFR, track suara dan normalisasi HDR. Fixture rotasi, SAR, dua track, audio terlambat, VFR lulus. | HDR belum diverifikasi dengan fixture; konversi memerlukan filter FFmpeg yang tersedia. |
| 39 | Pengaturan, timeline, recipe, preview, final, ekspor per rasio. Empat render dan uji independensi lulus. | — |
| 40 | Patch koreksi satu klip atau shared utterance, lineage sumber, pengecualian manual; heard words immutable. | Alias global tetap berbeda dengan koreksi ucapan tertentu. |
| 41 | Antrean persist, cancel process tree milik job, deteksi worker terputus, retry/resume tahap. | Tidak melanjutkan proses pada frame yang persis sama setelah crash. |
| 42 | Backup ZIP isi/checksum, relink konten identik, restore proyek baru, sesi lama hilang sumber tetap dapat dipulihkan. | Riwayat lama disertakan sebagai arsip; sesi tanpa checksum wajib analisis ulang. |
| 43 | Halaman kata maksimal 200, UI 100, pencarian, patch kecil. Tes 10.001 kata lulus. | Render/analisis worker tetap membaca transkrip penuh di luar browser. |

## Berkas dan kontrak

`project_store.py`: revisi, immutable ASR takes, heard/display words, sparse patches, undo, job/artifact tables. `studio_service.py`: validasi dan transaksi proyek, migrasi sesi lama, route adapter A. `job_queue.py`/`studio_worker.py`: claim global satu job, kepemilikan PID, dependensi, proses berat, validasi hasil sebelum commit.

`media_context.py`: satu sistem koordinat untuk OpenCV/ASR/FFmpeg. `studio_exchange.py`: token render berasal dari snapshot A; EditTimeline, CaptionPlan, SceneAnalysis dan RenderManifest berasal dari plan aktual, dengan frame akhir eksklusif dan hash konten. `illustration_schedule.py`: ketersediaan aset berbeda dari pemakaian aktual; offset dipertahankan pada split shot. `dependency_cache.py`: sumber, aset dan font dikenali dari isi.

`studio_storage.py`: inventory milik aplikasi, proteksi sumber/aset, cache dan backup. `audio_quality.py`: waveform dan QC hasil encode. `export_verify.py`: struktur paket dan status native yang jujur. `static/studio4.*`: shell baru; panel A menggunakan layanan nyata.

API utama: `/api/studio/projects`, `/changes`, `/projects/{id}/words`, `/history`, `/undo`, `/jobs`, `/storage`, `/restore`, `/benchmark`. File yang dapat dibuka memakai ID terdaftar. Endpoint lama tetap untuk kompatibilitas, tetapi POST proyek yang sudah dimigrasi ditolak agar tab UI lama tidak menimpa database baru.

## Pengujian dan gate lanjutan

Suite akhir lulus 310 tes otomatis dengan 5 peringatan deprecation. Uji browser lulus 11 pemeriksaan tanpa page error; empat render media dan lima fixture geometri lulus. Laporan rilis ada di `verification/summary.json`, log pytest, laporan browser, media dan geometri. Semua video pengujian gabungan sintetis dan memakai encode CPU. Hasil ini menguji jalur sebenarnya, bukan akurasi model pada video pengguna.

Urutan penerimaan di komputer sasaran: jalankan CEK_PRO; analisis satu rekaman sumber asli dengan istilah XAUUSD/negasi/angka; tinjau pemilihan cerita, batas dan subtitle pada kedua rasio; bandingkan preview dengan final; impor paket pada CapCut dan DaVinci; rekam versi, perbedaan efek, media offline dan audio sync. Benchmark membutuhkan teks manusia serta rentang cerita yang disepakati, dan penilaian manusia untuk estetika, relevansi ilustrasi dan waktu koreksi. Simpan bukti tersebut sebelum menyatakan rilis produksi lulus.
