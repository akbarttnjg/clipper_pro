# Laporan pengujian Clipper Studio Local 3.2

Tanggal: 1 Oktober 2026. Basis: commit `5d307201fe8f9e333df94fd8174eaa566febf370` dari `akbarttnjg/clipper_pro` dan payload paket 3.1 yang dibandingkan byte-per-byte. Platform pengujian: Linux, Python 3.12.14, FFmpeg/libx264, OpenCV, Chromium headless. Ini bukan pengukuran di laptop pengguna.

## Hasil

| Pemeriksaan | Hasil |
|---|---|
| Suite unit/integrasi Python | 217 lulus; satu peringatan deprecation Starlette/httpx, bukan kegagalan |
| Sintaks JavaScript dan whitespace patch | Lulus |
| UI desktop dan lebar 390 px | Lulus; tidak ada error JavaScript/HTTP atau tombol aksi melewati layar |
| Render 16:9 | MP4 1920×1080, 7,6 detik; QC teknis lulus |
| Render 9:16 | MP4 1080×1920, 7,6 detik; QC teknis lulus |
| B-roll pada kedua rasio | Media berukuran kanvas, jalur subtitle kosong terverifikasi; file yang sama dipakai untuk ekspor |
| Paket editor | Dua timeline berhasil dibuat; generator CapCut tidak melaporkan error |
| Model wajah YuNet | File dapat dimuat; lisensi dan checksum disertakan |
| Installer 3.1 → 3.2 dan pemulihan | Lulus: 99 file payload diverifikasi, 90 file baseline kembali identik setelah rollback |
| Data pengguna saat pemasangan | 11 file sentinel (konfigurasi, venv, sumber, final, sesi, koreksi, audio, preset) tetap identik |
| Pemasangan ulang paket sama | Tidak menulis perubahan atau membuat cadangan tambahan |
| Suite pada aplikasi hasil instalasi | 217 lulus; dijalankan dari folder target yang mengandung spasi |

## Cakupan yang diperiksa

- Cache: preview baru/lama yang dikenali, penggunaan ulang fingerprint, perubahan teks/aset, path traversal, symlink, penolakan saat pekerjaan aktif, dan file terkunci. Video final, sesi, transkrip, rencana edit, audio ekspor, serta file pengguna tetap tersedia.
- Seleksi: seluruh jendela tetap dikunjungi setelah jawaban rusak, percobaan ulang jendela gagal, kandidat cadangan sampai batas hasil terverifikasi, adaptif lebih dari sepuluh, dan pembedaan cerita yang memakai kosakata serupa. Respons model pada pengujian ini berupa fixture, bukan benchmark Qwen.
- Transkrip: koreksi istilah dengan konteks, kamus eksplisit, prioritas edit manual, log/teks mentah/waktu sumber, perlindungan angka dan penyangkalan, serta syarat penerimaan hasil dengar ulang. Pemanggilan model Whisper penuh belum dijalankan.
- Tata letak: papan terang/gelap, wajah berpindah, area materi, ruang penuh, posisi manual, pemisahan frasa pada pergantian adegan, dan batas animasi. Deteksi tulisan menggunakan pola visual, bukan OCR semantik.
- UI: membuka sesi, memutar URL keluaran, perbandingan pembersihan tanda baca, posisi manual, menyimpan koreksi, nilai awal adaptif/luas, delapan preset, dan tombol penghapusan cache tanpa menghapus final.
- Installer: pemeriksaan versi dasar, checksum, penolakan path keluar, rollback saat salin gagal, dan perlindungan perubahan kode setelah instalasi tercakup dalam suite.

## Batas hasil ini

Video di folder `contoh` adalah fixture sintetis dengan audio nada, bukan rekaman pengguna atau demo akurasi model. Tidak tersedia sumber mentah panjang 1–2 jam dan model Qwen/Whisper penuh di lingkungan pengujian ini. Akurasi kata, jumlah/kualitas cerita dibanding Opus/Vizard, penggunaan VRAM, dan waktu selesai pada RTX 3050 4 GB belum diukur.

Pembuatan paket editor teruji, tetapi impor native pada CapCut Desktop 9.5.0 atau DaVinci Resolve Free 21.0.4 Build 5 belum diuji. Instalasi dijalankan melalui Python pada Linux; peluncur `.cmd` dan perilaku penguncian file Windows perlu dijalankan pada perangkat pengguna. Kasus file terkunci disimulasikan pada suite.

Jumlah klip mengikuti isi yang lolos verifikasi. Upgrade tidak menjanjikan jumlah tertentu, akurasi sempurna, tampilan identik dengan referensi TikTok, atau waktu selesai 30 menit.
