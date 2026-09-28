# Pengujian Clipper Studio Local 2.4

Tanggal pengemasan: 29 September 2026 WIB. Basis fork `akbarttnjg/clipper_pro`, commit `05eefb4ad40f022071ec124591f765f408461a53`, ditambah pembaruan lokal 2.3/2.3.1.

## Hasil

| Pemeriksaan | Hasil |
|---|---|
| Python | 160 tes lulus, 1 peringatan dependensi |
| API stok | Kontrak respons/auth Pexels, Pixabay, Coverr; cache 24 jam; key tidak bocor; respons kuota dan media rusak gagal dengan aman |
| Sumber stok | Koleksi lokal didahulukan; tanpa key/aset tidak memanggil perencana; papan tulis tidak memakai B-roll |
| Waktu ilustrasi | Pemetaan waktu setelah trim, perlindungan materi/kutipan, batas sisipan |
| Tipografi | Kelengkapan urutan kata, perataan manual, pengukuran baris, peringatan waktu/angka tanpa menulis ulang transkrip asli |
| Render nyata | 1920×1080 dan 1080×1920, 30 fps, masing-masing 16 detik; B-roll 3 detik |
| Validasi frame | Warna sumber/sisipan diperiksa sebelum, saat dan sesudah sisipan; subtitle tetap di atas B-roll |
| Materi | Render 16:9 dan 9:16 masing-masing 8 detik; dua area dan durasi jeda terjaga |
| Ekspor nyata | Dua timeline, file XML dan draft CapCut; track B-roll/teks/suara terpisah; video dasar tidak berisi sisipan |
| UI | Save/clear API key, key tersamarkan, status persiapan singkat, posisi/perataan, enam template, font, ukuran, preset pribadi, salin gaya, perapian, preview dari tengah sumber |
| Layar | 1920×1080, 1366×768, 900×700; tanpa overflow horizontal; akses render tersedia; tanpa galat JavaScript |
| ZIP/installer | Lihat hasil pemeriksaan paket di bawah |

Render menggunakan media sintetis pendek dengan transkrip terkendali. Browser headless memakai sumber WebM karena tidak menyediakan decoder H.264; render MP4 diperiksa lewat FFmpeg/ffprobe dan frame hasil. Ini bukan benchmark kualitas sumber YouTube pengguna sepanjang 1–2 jam.

## Paket instalasi

Pemeriksaan paket dilakukan terhadap ZIP final: CRC, isi setiap anggota, hash seluruh payload, ekstraksi ke folder baru, dry-run tanpa perubahan, pemasangan offline pada salinan 2.3.1 dengan path ber-spasi, data pengguna tetap utuh, pemasangan ulang idempoten, penolakan rollback terhadap edit baru, serta pemulihan byte-identik. ZIP memakai ZIP_STORED agar kompatibel dengan ekstraktor standar.

## Batas verifikasi

- Lingkungan Linux, Python 3.12, encoder libx264. NVENC dan CMD Windows pada laptop pengguna belum dijalankan langsung.
- Pexels/Pixabay/Coverr diuji dengan fixture sesuai dokumentasi, tanpa API key akun pengguna. Hasil stok sebenarnya dan kuota akun belum teruji langsung.
- Qwen/Whisper baru tidak dipasang; peningkatan akurasi dan durasi sumber panjang belum diukur pada hardware pengguna.
- File proyek berhasil dibuat dan strukturnya diperiksa; impor interaktif di CapCut 9.5 dan Resolve Free 21.0.4 belum terverifikasi. Blur/fade native CapCut belum sama dengan ASS.
- Tidak ada penilaian otomatis yang menjamin cerita lengkap, relevansi semua stok, atau FYP. B-roll dipilih lewat pencarian teks, belum melalui model vision. Podcast dua pembicara nyata belum diuji.
- Posisi akhir baris diverifikasi, bukan kualitas optis setiap frame atau semua wajah/papan. Area manual dapat membantu sumber dengan tata letak tetap.

Rujukan kontrak API: https://www.pexels.com/api/ ; https://pixabay.com/api/docs/ ; https://api.coverr.co/docs/videos/ ; https://api.coverr.co/docs/auth/ . Konsep pencarian stok terinspirasi MoneyPrinterTurbo; implementasi adapter dan integrasi ini dibuat untuk Clipper.
