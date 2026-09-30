# Laporan verifikasi Clipper Studio Local 3.1

Basis kode: Studio 2.4, commit `4886fd044fa7a8912ac77c3e9cba60c2338e8849`.
Lingkungan pengembangan: Linux, Python 3.12, FFmpeg/libx264 pada CPU.
Laporan ini membedakan pemeriksaan logika, media sintetis, dan hal yang belum diuji.

## Tes kode

`python -m pytest clipper/tests -q`: **180 passed**, satu peringatan deprecation
Starlette/httpx pada test client; tidak ada tes gagal.
`node --check static/studio.js`, kompilasi Python, dan `git diff --check`: lolos.

Cakupan baru mencakup bukti kutipan dan waktu sumber; penolakan kutipan rekaan,
segmen salah, cerita belum selesai, risiko dan angka/waktu ASR mencurigakan;
keputusan kedaluwarsa setelah perubahan isi; pembatalan keputusan saat review gagal;
hook dipindah sekali tanpa kata ganda akibat pembulatan frame; negasi dalam frasa
caption; B-roll yang dipilih dari kandidat kedua atau seluruhnya ditolak; serta
alur otomatis sesi baru/lama, tanpa kandidat lolos, dan kegagalan ekspor.
Respons model dalam tes kode disimulasikan. Tes ini tidak mengukur kualitas Qwen.

## Render dan ekspor dengan media sintetis

Dua render FFmpeg sungguhan menggunakan sumber sintetis 34 detik, transkrip contoh,
gaya Shorts dinamis, dan hook kalimat utuh yang dipindahkan ke depan:

| Hasil | Rasio | Durasi | Pemeriksaan |
|---|---|---|---|
| 1080 × 1920 | 9:16 | 33,13 detik | Stream, dimensi, durasi, batas caption: lolos |
| 1920 × 1080 | 16:9 | 33,13 detik | Stream, dimensi, durasi, batas caption: lolos |

ID kata pada edit plan tidak berulang. Frame hasil pada kedua rasio diperiksa untuk
memastikan caption muncul dalam area gambar. Tidak ada overlay banner judul.
Detektor YuNet dilewati pada sumber sintetis tanpa wajah; fallback berjalan.
Ini bukan pengujian pelacakan wajah atau kualitas crop pada video nyata.

Paket proyek dengan dua timeline berhasil dibuat. Draft CapCut, XML/Lua/Fusion
DaVinci, media dan edit plan tersedia; `capcut_error` kosong. **Impor dan playback
di aplikasi CapCut/DaVinci belum diuji**, sehingga kesetaraan animasi native belum
terverifikasi.

## Alur UI

DOM JavaScript aktual dijalankan dengan jsdom dan respons GET dari server FastAPI
aktual. Endpoint mutasi ditangkap agar tidak memulai model. Pemeriksaan lolos:

- Memuat sesi dan panel bukti cerita; tombol payoff menuju detik sumber yang benar.
- Tombol otomatis mengirim indeks kandidat yang dipilih.
- Tujuh preset tersedia; memilih Shorts mengatur font/animasi sambil mempertahankan
  posisi caption bawah dan perataan kiri yang sudah dipilih manual.
- Form proyek baru memakai alur otomatis, Shorts, B-roll otomatis, paket editor,
  serta mengirim opsi hook dan pemangkasan.

Browser Chromium tidak tersedia pada lingkungan ini dan unduhannya gagal.
Pengujian UI di atas memeriksa interaksi DOM, **bukan screenshot browser, ukuran
viewport, atau pemutaran video interaktif**.

## Paket dan installer

Paket berisi **90 file payload**. ZIP lolos pemeriksaan CRC, dan checksum SHA-256
setiap file cocok dengan manifest. Installer Python dijalankan melalui CLI pada
salinan utuh commit Studio 2.4 dengan tambahan data pengguna simulasi.

- Dry-run tidak mengubah target. Payload yang sengaja dirusak ditolak sebelum
  penyalinan. Pemasangan menggunakan manifest offline tanpa memanggil pip.
- Semua file terpasang sesuai checksum. Konfigurasi, sesi, cache/transkrip, video,
  hasil lama, preset pribadi, lingkungan Python, serta backup lama tetap utuh.
- Menjalankan installer lagi tidak membuat perubahan atau backup kedua.
- Rollback menolak menimpa kode yang diubah setelah instalasi. Setelah perubahan
  simulasi tersebut dibatalkan, rollback memulihkan snapshot file awal secara tepat
  dan menghapus file baru yang diperkenalkan upgrade.

Launcher `.cmd` disertakan untuk Windows; eksekusi native launcher tersebut belum
diuji karena lingkungan pengujian menggunakan Linux.

## Belum terverifikasi

- Qwen 3:8b dan Whisper medium sungguhan pada sumber nyata 1–2 jam.
- Waktu proses, pemakaian VRAM, NVENC, dan launcher CMD pada Windows/RTX 3050 4 GB.
- Relevansi stok dari gambar video; versi ini menilai metadata, bukan frame.
- Kualitas seleksi, retensi, dan hasil kreatif yang setara akun referensi.
- Impor interaktif native CapCut/DaVinci.

Tidak ada model atau dependensi wajib baru. Uji satu video nyata setelah memasang
upgrade, lalu periksa pembuka, penutup, caption, B-roll dan satu paket editor.
