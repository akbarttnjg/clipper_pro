# Clipper Studio 4.0.9 — tipografi dan perbaikan hasil audit

Upgrade ini dibuat dari sumber pembenahan lengkap 4.0.8 dan dua audit yang
dibaca di chat ini. Paket menyertakan seluruh payload pembenahan sebelumnya.

## Cara memasang

1. Ekstrak ZIP ke folder baru, bukan ke folder mesin. Hentikan server dan antrean.
2. Jalankan `CEK_SEBELUM_UPGRADE.cmd --target "C:\AI\clipper"`.
3. Jika lulus, jalankan `PASANG_UPGRADE_4_0_9.cmd --target "C:\AI\clipper"`.
4. Jalankan `JALANKAN_PRO.cmd`, kemudian Ctrl+F5 di browser.
5. Pada klip uji, pilih preset **Adaptif**, **Rapi**, atau **Ekspresif** dan
   **Komposisi frasa: Otomatis**. Simpan, buat preview baru untuk kedua rasio,
   periksa keterbacaan, lalu render final.

Pemasang memeriksa hash dasar yang dikenal, mencadangkan kode dan SQLite,
memeriksa impor setelah penyalinan, dan membatalkan perubahan bila pemeriksaan
gagal. Data proyek, sumber, `.env`, font pribadi, dan model tetap tersimpan.
Hasil 4.0.8 masih tersimpan; cache render lama tidak dianggap hasil 4.0.9.
Pilihan gaya manual dan revisi proyek tetap dipertahankan. Preset Legacy
mempertahankan tata gaya lama; pilih preset baru untuk memakai caption director.

Jika folder mesin bukan `C:\AI\clipper`, ganti argumen target. Jika ada kode
lokal yang berbeda dari dasar terverifikasi, pemeriksaan menolak penimpaan.
Jangan mengatasi penolakan dengan menyalin payload secara manual.

Rollback kode tersedia melalui `PULIHKAN_UPGRADE_4_0_9.cmd --target "C:\AI\clipper"`.
Koreksi proyek setelah upgrade tetap disimpan. Cadangan SQLite disimpan terpisah;
rollback kode tidak mengembalikan database secara diam-diam.

## Perubahan yang dikerjakan

| Area | Perubahan |
|---|---|
| Frasa | Pasangan waktu, negasi, nominal, istilah trading, serta objek negasi singkat tetap utuh. Awal klausa yang jelas tidak disambungkan ke klausa sebelumnya. |
| Fokus | Penekanan memakai kata yang benar-benar diucapkan. Kata kunci global tidak menutup frasa lain seperti “bahaya”, “makin memuncak”, dan “tanpa rencana”. |
| Komposisi | Editorial bersih, frasa fokus besar, dan kutipan tenang. Urutan dan identitas kata tetap sama. Font utama/aksen memakai metrik glyph nyata. |
| Gerak | Seluruh frasa mulai tampil bersama pada dua rasio. Arah dan hierarki terukur; tidak ada pergantian alignment acak per frasa. Template manual tetap dihormati. |
| Ukuran | Landscape memakai skala terhadap lebar keluaran. Pemeriksaan melaporkan tinggi kapital pada asumsi layar lebar 360 px, dengan batas 14 px. Frasa yang masih terlalu kecil perlu ditinjau. |
| Area teks | Kandidat dinilai dari kapasitas, tekstur, terang gambar, area penting, margin platform, serta stabilitas. Pakaian polos boleh menjadi permukaan teks. |
| Ekspor | Bukti editor untuk paket gabungan memilih satu klip dan rasio. Bukti satu timeline tidak meloloskan timeline lain. Resolusi, durasi, dan identitas berkas diperiksa. |
| Diagram | Kelengkapan daftar diperiksa sepanjang blok ucapan, termasuk item kelima yang jauh. Keterangan lanjutan tidak dipotong dari item terakhir. Daftar ambigu dilewati. |
| Antrean | Proses menunggu dengan jeda yang dapat dibatalkan saat pemilik antrean lain sedang bekerja; tidak berputar tanpa jeda. |
| Cache | Hash yang sama dibaca sekali dalam setiap fase validasi segar. Hasil tetap diperiksa lagi setelah tahap berat dan sebelum publikasi. |
| Waktu | Transkripsi, OCR/bukti, koreksi, pemilihan cerita, serta total analisis dilaporkan terpisah. Total analisis tidak mencakup render dan ekspor editor. |

## Komponen tambahan

**MediaPipe Selfie Multiclass** menjadi komponen opsional ke-27. Tidak perlu
mengunduh SAM atau model VLM besar untuk mengaktifkan perbaikan tipografi ini.
YuNet dan RapidOCR yang sudah dipasang tetap dipakai bila siap.

Untuk memakai MediaPipe, buka panel Komponen, pasang **MediaPipe Selfie
Multiclass**, lalu jalankan **uji sampel CPU**. Interpreter komponen terpisah;
lingkungan aplikasi utama tidak diubah. Resep memakai MediaPipe 0.10.21,
NumPy 1.26.4, OpenCV contrib 4.11.0.86, serta model resmi versi 1 dengan
SHA-256 yang dikunci. Unduhan model 16.37 MB; kebutuhan lingkungan sekitar
2 GB disk, bergantung wheel dan cache. Bobot tidak disertakan dalam ZIP ini.

Rendering memakai maksimal delapan frame sumber per klip. Hair/face/accessory
menambah area yang dilindungi. Clothing diberi skor sebagai permukaan yang
boleh ditimpa, bukan larangan menutupi seluruh orang. Mask dan provenance
disimpan dalam cache lokal. Kerusakan mask membatalkan pemakaian cache.
Tanpa komponen yang siap, YuNet/OCR dan statistik gambar tetap bekerja.
Pilihan **Pendukung area teks** dapat menonaktifkan segmentasi untuk klip aktif.

Sumber resmi: [MediaPipe Image Segmenter](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter),
[API Python](https://developers.google.com/edge/mediapipe/solutions/vision/image_segmenter/python),
[MediaPipe 0.10.21](https://pypi.org/project/mediapipe/0.10.21/).
Model SHA-256: `c6748b1253a99067ef71f7e26ca71096cd449baefa8f101900ea23016507e0e0`.

## Batas pembuktian

Lihat `verification/` untuk hasil tes, render dan metadata pembuktian.
Render pembanding memakai bagian utuh **13.5 detik dari plate sumber lama**,
transkrip tersimpan dan observasi wajah lama; MediaPipe menjalankan inference
CPU yang sebenarnya. Ini tidak membuktikan kualitas pada dua MP4 terbaru,
karena berkas pada chat akun lain tidak dapat diambil di sesi ini.

Uji sampel model memastikan inference dan format mask berjalan, bukan akurasi
setiap piksel pada setiap frame. Area aman platform adalah profil margin,
bukan jaminan untuk seluruh aplikasi dan ukuran layar. Hasil perlu dilihat.
Kualitas estetika dan isi tidak dinyatakan “lulus” hanya dari SSIM atau tes kode.
CapCut/Resolve diuji konstruksi berkas dan struktur; buka/edit/simpan/render
langsung dalam editor Windows tetap perlu diuji pada komputer pengguna.
Target 30 menit untuk sumber 1–2 jam belum dibuktikan oleh render pendek ini.
