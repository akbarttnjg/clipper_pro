# Pengujian Clipper Studio Local 2.3.1

Verifikasi: 28 September 2026 (WIB). Basis fork `akbarttnjg/clipper_pro`, commit `05eefb4ad40f022071ec124591f765f408461a53`, ditambah pembaruan lokal 2.3 dan 2.3.1.

## Fungsional

| Pemeriksaan | Hasil |
|---|---|
| Python | 147 tes lulus; 1 peringatan dependensi |
| Konflik posisi | 36 kombinasi gaya/posisi/perataan melawan anchor otomatis; posisi manual menang, tepi baris sejajar |
| Vertikal | Rata kiri/tengah/kanan pada area bawah lulus |
| Sesi/preset lama | Nilai awal perataan diterapkan; judul lama tidak hidup kembali; preset tidak mengganti geometri |
| Render | MP4 1920×1080 kiri/rata kiri dan kanan/rata kanan; 1080×1920 bawah/rata kanan; masing-masing 8 detik, 30 fps |
| Validasi hasil | Dimensi, durasi, audio, posisi/perataan rencana teks, ketiadaan judul pembuka |
| Ekspor | Paket dua timeline dibuat; tanpa galat generator CapCut |
| UI | Posisi/perataan tersimpan, preset mempertahankan posisi, tanpa kontrol judul, preview durasi aktual, pilihan font dan preset, salin gaya, tab dan perapian teks |
| Layar | 1920×1080, 1366×768, 900×700; tidak meluap horizontal, akses render tersedia |

Uji menggunakan sumber sintetis pendek dan transkrip uji. `title_card=true` serta penempatan aman sengaja diaktifkan untuk mereproduksi konflik lama. Browser headless memakai sumber WEBM karena decoder H.264 tidak tersedia; MP4 diperiksa menggunakan FFmpeg/ffprobe dan frame hasil.

## Installer

Paket diuji pada salinan 2.3 di folder terisolasi dengan nama mengandung spasi: CRC ZIP, hash seluruh payload, dry-run tanpa perubahan, pemasangan offline, pemasangan ulang idempoten, perlindungan data pengguna, penolakan rollback terhadap perubahan baru, dan pemulihan byte-identik.

ZIP menggunakan format standar tanpa kompresi (ZIP_STORED), tanpa cache Python. SHA-256 disediakan sebagai berkas pendamping.

## Batas pengujian

Lingkungan: Linux, Python 3.12, encoder CPU libx264. CMD Windows dan NVENC laptop belum diuji langsung. Impor interaktif pada CapCut 9.5/Resolve Free 21.0.4 belum terverifikasi; animasi native dapat berbeda dari ASS.

Pemeriksaan perataan menilai kotak kata pada posisi akhir, bukan bentuk optis semua huruf, oklusi wajah/diagram, atau seluruh frame animasi masuk. Komposisi otomatis preview dapat berbeda karena potongan analisis lebih pendek. Periksa satu hasil sumber asli sebelum produksi banyak clip. Model pemilihan topik tidak diganti.
