# Verifikasi Clipper Studio 4.0.10 — 10 Oktober 2026

Dasar: GitHub main `2e5d97621be0d2576f62c13c4c04696c6cadef06` (4.0.9).
4.0.10 dibangun kembali dari kode tersebut dan audit percakapan terakhir.

## Cakupan pengujian

Hasil gabungan: **87 kasus lulus, 1 dilewati, 0 gagal** dari 88 kasus.
Uji yang dilewati adalah pemeriksaan impor aplikasi lengkap dengan dependensi nyata.

- Regresi tata letak 4.0.9 dan Style5: 61 kasus.
- Regresi/integrasi baru 4.0.10: 22 kasus (geometri, frasa, preview/final,
  penempatan, waktu segmentasi, kontrak alignment, dan usulan E5).
- Pemasang: file sistem dan SQLite nyata; uji pemasangan, idempotensi, backup,
  rollback, kode lokal berbeda, payload rusak, serta kegagalan pemeriksaan akhir.
  Proses server dan impor dependensi tujuan diganti fixture pada empat uji ini.
  Satu uji impor inti nyata dilewati jika dependensi tidak tersedia.
- UI: harness DOM Node untuk modul Style5, bukan pengujian browser Windows.
- Python: kompilasi modul aplikasi dan tools.

Hasil akhir perintah dan jumlah kasus tersedia di `verification/tests.txt` pada
paket. Uji seluruh aplikasi belum dijalankan: OpenCV, FastAPI dan dependensi
aplikasi lain tidak tersedia dalam lingkungan pembuat paket.

## Render nyata melalui FFmpeg, sumber sintetis

| Ukuran | Durasi | Waktu render di lingkungan pembuat | Minimum huruf a pada lebar tampilan 360 px | Pita cadangan |
|---|---:|---:|---:|---:|
| 1080 × 1920 / 9:16 | 62 detik | 13,532 detik | 14,67 px | 0 dari 5 shot |
| 1920 × 1080 / 16:9 | 62 detik | 12,797 detik | 15,00 px | 0 dari 5 shot |

Kedua video lolos decode FFmpeg sampai akhir. Masing-masing berisi 33 frasa.
Tidak ada laporan teks terlalu kecil, tabrakan atau keluar bidang pada fixture.
Ada **empat peringatan kecepatan baca per rasio**: mulai 12, 24, 27 dan 30 detik.
Peringatan tidak dihapus; hasil ini tidak disebut lulus seluruh keterbacaan.

Frame pada detik 50,5 dan 53,6 diperiksa: frasa fokus tidak menjadi tiga baris dan
`terus-terusan` tetap satu unit. Video/JSON dan frame contoh disertakan pada
folder `verification/`. Reproduksi: `python tools/qa_typography10.py --output qa410`.

Fixture menggunakan gambar geometris, transkrip uji, kotak wajah/ponsel yang
ditentukan dan audio hening. Ini menguji geometri, komposisi, subtitle dan
encoding; **bukan** uji deteksi wajah, transkripsi, kualitas suara, atau video asli
pengguna. Waktu render di atas tidak mewakili laptop RTX 3050 pengguna dan tidak
membuktikan target video 1–2 jam selesai dalam 30 menit.

## Batas yang tetap terbuka

Bobot nyata E5, WhisperX/CTC dan MediaPipe belum dijalankan dalam verifikasi ini.
Kontrak input/output, cache, fallback, perlindungan timing manual dan asal kata
diuji dengan fixture. Preview/font pada Windows serta hasil pada footage asli
perlu dinilai setelah pemasangan. Native CapCut/Resolve dan renderer browser
Remotion/Motion Canvas tidak diuji ulang. Mekanisme ekspor CapCut dipertahankan;
pembenahan teks Resolve ditunda sesuai prioritas pengguna.

## Sumber keputusan

- Percakapan terbaru: https://chatgpt.com/share/6ac96d42-b6bc-83ec-b726-f36453211fca
- Dasar kode: https://github.com/akbarttnjg/clipper_pro/tree/2e5d97621be0d2576f62c13c4c04696c6cadef06
- Panduan pemasangan dan pengaturan: `docs/UPGRADE_4_0_10.md`.
