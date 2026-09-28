# Pengujian Clipper Studio Local 2.3

Tanggal verifikasi akhir: 27 September 2026. Basis kode: fork `akbarttnjg/clipper_pro`, commit `05eefb4ad40f022071ec124591f765f408461a53`.

## Hasil yang telah diperiksa

| Pemeriksaan | Hasil |
|---|---|
| Suite Python | 104 tes lulus; 1 peringatan dependensi |
| Sintaks JavaScript dan diff | Lulus |
| Font | TTF valid; identitas family/style, lebar teks Pillow, dan tag ASS sesuai untuk kelima pasangan preset |
| Perapian subtitle | Sumber, negasi, kata keraguan, angka, serta waktu kata tetap tersimpan; tersedia perbandingan dan mode semua kata |
| Sesi 2.2 | Dapat dipulihkan dengan nilai bawaan fitur baru; tidak membutuhkan analisis ulang |
| Preview | Memakai posisi cursor sumber; tidak menggeser batas kandidat atau mengubah transkrip asli |
| Render 9:16 | MP4 uji 1080×1920, 30 fps, 8 detik; audio, dimensi, durasi, dan subtitle diperiksa |
| Render 16:9 | MP4 uji 1920×1080, 30 fps, 8 detik; audio, dimensi, durasi, dan subtitle diperiksa |
| Ekspor proyek | Paket dua timeline dibuat; rujukan berkas font teks native tersedia; generator CapCut tidak melaporkan galat |
| Galeri | Lima video 9,8 detik dirender oleh mesin ASS yang sama; gambar poster dibundel |
| UI browser | Pemilihan preset/font, ukuran, simpan koreksi, preset pribadi, salin gaya ke dua clip, empat tab, perbandingan teks, dan preview posisi tengah lulus tanpa galat JavaScript |
| Ukuran layar | 1920×1080, 1366×768, dan 900×700: tidak ada luapan horizontal dokumen; tombol render dan akses pengaturan tersedia |

Uji browser memakai video sumber WEBM untuk menguji pemutaran dan pencarian posisi karena Chromium headless pada lingkungan pengujian tidak menyertakan decoder H.264. MP4 final diperiksa dengan FFmpeg/ffprobe dan cuplikan hasil render, bukan dengan klaim pemutaran MP4 pada browser tersebut.

## Pemasangan

Paket diuji pada salinan instalasi 2.2 di folder terisolasi yang namanya mengandung spasi. Seluruh pemeriksaan berikut lulus:

- ZIP dapat dibaca tanpa galat CRC; seluruh 83 berkas payload cocok dengan hash manifest.
- Mode `--dry-run` tidak mengubah berkas target.
- Installer CLI memasang 44 berkas baru/berubah tanpa mengunduh dependensi.
- Berkas uji dalam `work`, `uploads`, `clips`, `.venv`, serta `.env`, `.env.pro`, `brand.json`, dan `style-presets.json` tetap identik.
- Pemasangan ulang tidak membuat cadangan tambahan atau mengubah program yang sudah cocok.
- Pemulihan menolak menimpa berkas program yang diedit setelah pemasangan.
- Setelah konflik uji diselesaikan, pemulihan mengembalikan seluruh berkas lama persis sesuai hash awal dan menghapus berkas program baru.

Uji ini memverifikasi logika installer Python di Linux. Peluncur CMD dan filesystem Windows tetap perlu dijalankan pada laptop pengguna.

## Batas bukti

- Render memakai video sintetis pendek yang berisi area materi dan pembicara tiruan. Ini menguji komposisi/teks/audio, bukan kualitas potongan pada seluruh rekaman pengguna.
- Lingkungan uji menggunakan Linux, Python 3.12, dan encoder CPU libx264. NVENC RTX 3050 serta peluncur `.cmd` Windows belum dijalankan di lingkungan ini.
- Impor interaktif pada CapCut 9.5 dan DaVinci Resolve Free 21.0.4 belum diverifikasi. Font/style diteruskan ke proyek; animasi native dapat berbeda dari ASS. ASS bukan format layer native yang dijamin didukung kedua editor.
- Kecepatan sumber 1–2 jam, akurasi Whisper, kelengkapan cerita, retensi penonton dan FYP tidak dapat disimpulkan dari pengujian ini. Mesin analisis yang sudah ada tidak diganti oleh upgrade 2.3.

Periksa satu preview dari sumber asli sebelum merender banyak clip. Semua font/preset dalam paket bekerja tanpa API berbayar.
