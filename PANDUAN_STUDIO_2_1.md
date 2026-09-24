# Clipper Studio Local 2.1 — perbaikan render dan review

Paket ini memperbarui Studio 2.0 yang sudah terpasang. Pemrosesan tetap lokal;
tidak ada layanan atau API berbayar baru. Tidak perlu mengunduh model lain.

## Pasang pembaruan

1. Tutup server Clipper dengan Ctrl+C di terminal.
2. Ekstrak seluruh ZIP ke folder baru, di luar `C:\AI\clipper`.
3. Jalankan `PASANG_UPGRADE.cmd`. Folder default adalah `C:\AI\clipper`.
   Untuk lokasi lain: `py -3 steezy_pro_installer.py --target "D:\AI\clipper"`.
4. Pada folder aplikasi, jalankan `CEK_PRO.cmd`. Periksa baris
   **Filter + subtitle + encode: OK**. Pemeriksaan NVENC tetap terpisah.
5. Jalankan `JALANKAN_PRO.cmd`, buka `http://localhost:8765`, lalu Ctrl+F5.
   Label aplikasi harus **LOKAL · 2.1**.

Paket perbaikan ini tidak menjalankan pip secara default. Dependensi Studio 2.0
sudah cukup. Jika CEK_PRO melaporkan modul yang belum terpasang, jalankan installer
dengan `--install-deps` (memerlukan internet, paketnya gratis).

File yang berubah dicadangkan ke `steezy_backups`. Profil `.env.pro`, `.env`,
folder `uploads`, `clips`, `work`, brand, dan modul `intelligence` tidak ditimpa
oleh paket ini. Untuk kembali ke kode sebelumnya, tutup server lalu jalankan
`PULIHKAN_PRO.cmd`. Cadangan instalasi adalah cadangan kode, bukan riwayat edit
kandidat yang dilakukan setelah pemasangan.

## Lanjutkan sesi 65905f865621 tanpa mengulang transkripsi

1. Pilih sesi lama di kiri. Namanya masih dapat berupa `0d2bc185ec69.mp4`,
   karena versi lama menyimpan nama unggahan tersebut.
2. Klik **Pulihkan sesi** jika statusnya masih error.
3. Pilih satu kandidat untuk percobaan. Clip 8 pada data yang diperiksa memiliki
   batas lebih jelas menurut transkrip, tetapi tetap dengarkan sumbernya.
4. Klik **Preview 12 dtk**, kemudian tab **Preview**. Preview membutuhkan render
   singkat, bukan transkripsi ulang. Cek framing, subtitle, dan audio.
5. Centang kandidat yang diinginkan, lalu **Render ... pilihan**.

Kandidat dan transkrip di `work\studio-jobs\65905f865621.json` serta
`work\65905f865621` tetap dipakai. Tombol Pulihkan sesi mengembalikan tahap review;
itulah sebabnya tidak perlu memilih Video baru atau mengulang analisis.

## Periksa dan perbaiki batas pembahasan

- **Periksa AI** meninjau satu kandidat menggunakan konteks sebelum dan sesudahnya.
- **Periksa ulang batas semua** meninjau semua kandidat dari transkrip yang sudah
  tersedia. Ollama harus berjalan. Ini menambah waktu review model, tetapi tidak
  menjalankan Whisper atau memindai ulang seluruh video.
- Bila ditemukan batas yang lolos pemeriksaan, kandidat diperbarui dan hasil
  render lama ditandai perlu diperbarui. Batas sebelumnya dicatat di data kandidat.
- Bila pemeriksaan tidak berhasil, batas lama dipertahankan dan alasan ditampilkan.
  Model tidak boleh pindah ke topik lain hanya agar menghasilkan clip.
- Label **Periksa batas pembahasan** berarti ada tanda kalimat terpotong, durasi
  terlalu panjang, pembuka bergantung konteks, atau metadata yang perlu diperiksa.
  Kandidat seperti ini tidak otomatis dicentang saat sesi dibuka.
- Pemeriksaan ini konservatif. Transkrip tanpa tanda baca dapat memicu peringatan
  walaupun audio terdengar utuh. Dengarkan **Dengar awal** dan **Dengar akhir**.
- Gunakan waktu `00:18:36.92` atau detik `1116.92`. Tombol **Awal [I]** dan
  **Akhir [O]** mengambil posisi pemutar. Simpan koreksi sebelum render.
- **Batasi clip** menghentikan playback sumber pada batas akhir. Matikan untuk
  menjelajah konteks di luar clip. Klik kata di konteks luar juga mematikan batas ini.
- Mode Edit kata hanya mengubah teks; timestamp ucapan dipertahankan.

Pemeriksaan kedua bukan jaminan bahwa semua topik utuh atau akan FYP. Ia memakai
model lokal yang sama dengan prompt berbeda dan pemeriksaan deterministik.
Jika daftar cara atau jawaban belum selesai dalam durasi maksimal, kandidat
memerlukan keputusan manual; mesin tidak memotongnya diam-diam agar tampak lolos.

## Komposisi 9:16 untuk materi dan pembicara

Otomatis mengenali panel presentasi terang berukuran besar. Ini deteksi bentuk,
bukan OCR atau pemahaman isi gambar. Jika panel terdeteksi dan wajah terpisah,
mode vertikal dapat menyusun materi di atas dan pembicara di bawah. Sumber gelap,
banyak pembicara, atau panel tanpa wajah dapat tetap membutuhkan area manual.

Untuk sumber seperti layar papan penjelasan dengan pembicara di samping:

1. Pilih **Materi + pembicara**, rasio **9:16**.
2. Jeda pada frame yang jelas, buka **Area materi & pembicara**.
3. Klik **Tandai materi**, lalu tarik kotak hanya pada papan/slidenya.
4. Klik **Tandai pembicara**, lalu tarik kotak pada area orangnya.
5. Sesuaikan porsi tinggi materi. Simpan koreksi dan buat Preview.

Angka area memakai persen `x,y,lebar,tinggi`. Area manual berlaku sepanjang clip;
untuk sumber yang berubah tata letak, gunakan otomatis atau pisahkan potongan.
Mode landscape mempertahankan materi yang terdeteksi. Zoom hanya dipakai pada
mode fokus pembicara; panel materi tetap stabil. Kotak pada Sumber adalah
panduan area; tab Preview menunjukkan komposisi yang benar-benar dirender.

## Musik, progres, dan render ulang

Musik/efek dapat ditambahkan ke sesi lama melalui panel **Musik & efek suara lokal**.
Klik **Simpan audio sesi**. Perubahan audio berlaku untuk semua kandidat dalam sesi
dan membuat hasil render sebelumnya perlu diperbarui. Angka volume tetap bisa
berbeda per clip. Musik diturunkan ketika suara pembicara terdengar.

Progres encoding mengikuti waktu keluaran FFmpeg. Rencana edit dan log tetap
tersimpan jika render gagal. Satu kegagalan clip tidak membuang hasil clip lain.
Percobaan render berikutnya melewati hasil 2.1 dengan revisi yang sama dan file
MP4 yang masih ada. File sementara tidak menggantikan MP4 selesai ketika encoding gagal.

## Waktu proses dan proyek editor

UI mencatat waktu setiap tindakan (analisis, review, preview, render, ekspor).
`transcript.json` mencatat durasi transkripsi dan seleksi untuk pekerjaan baru;
`selection-report.json` mencatat waktu jendela analisis dan pemakaian cache.
Sesi lama tidak memiliki rincian durasi yang dahulu belum direkam.

Target 30 menit per batch belum dibenchmark pada i5-12500H/RTX 3050 Anda. Pemeriksaan
konteks tambahan mengutamakan kualitas batas dan dapat menambah waktu model.

Ekspor CapCut 9.5 dan Resolve Free 21.0.4 menggunakan mekanisme Studio 2.0 yang sama.
Impor native belum diverifikasi langsung pada kedua editor. Split materi/pembicara
masih perlu disusun ulang di proyek native; MP4 memakai komposisi renderer yang
sudah diperbaiki. Teks, audio, dan keputusan edit tetap disertakan secara terpisah.
Baca BACA_DULU.txt di dalam paket proyek untuk batas kesetaraan animasi dan tata letak.

## Jika masih ada masalah

Kirim pesan error, hasil CEK_PRO, file `.render.log`, dan `edit-plan.json` dari
folder clip terkait. Tidak perlu mengirim ulang video panjang untuk error perintah
FFmpeg. Untuk akurasi ucapan, diperlukan potongan audio/video sumber yang relevan.
