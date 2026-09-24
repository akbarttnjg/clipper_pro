# Laporan pengujian Studio 2.1

Tanggal: 24 September 2026. Lingkungan: Linux, Python 3.12, FFmpeg 6.1.1,
encoder CPU libx264. Tidak ada GPU NVIDIA atau aplikasi editor Windows di lingkungan ini.

## Hasil yang sudah diuji

- 73 pengujian Python lulus: 58 pengujian lama dan 15 regresi baru.
- Regresi baru mencakup: pemilihan sintaks filter modern/lama berdasarkan probe,
  error argumen tidak diulang sebagai error NVENC, deteksi libass tidak tersedia,
  penutup menggantung walaupun skor AI tinggi, padding batas kata, ekspansi
  singkatan, penolakan perpindahan topik saat review, cache review, validasi area,
  deteksi panel, kelanjutan batch, dan pemulihan sesi tanpa analisis ulang.
- Pengujian JavaScript dengan jsdom lulus: sumber lokal, kandidat, escaping teks,
  koreksi kata, waktu jam:menit:detik dikirim sebagai detik, penghentian playback
  pada batas akhir, permintaan review AI, area manual, render, dan preview.
- Endpoint aset CSS/JS mengembalikan berkas yang tepat; nama lain ditolak.
- Tiga render 1080p 30 fps, masing-masing 18,5 detik, berhasil: 9:16, 16:9,
  dan materi/pembicara dengan dua region manual. Subtitle, kutipan pembuka,
  musik, efek suara, progres, serta pemeriksaan dimensi/durasi/audio dipakai.
  Frame hasil diperiksa secara visual. Sumber berupa pola uji, bukan contoh
  kualitas editing editorial atau transkripsi manusia.
- Struktur filter yang dikirim pengguna dijalankan ulang menggunakan sumber
  sintetis 1920x1080. Sembilan cabang, crop dan trim dari filter asli dipertahankan;
  hanya sumber subtitle/lokasi aset diganti untuk lingkungan pengujian.
  Keluaran 1080x1920 sepanjang 131,933 detik lulus QC, dengan 80 pembaruan progres.
  Waktu render sekitar 42 detik memakai preset veryfast. Ini bukan benchmark
  laptop pengguna atau estimasi waktu analisis video panjang.
- Audit lokal data sesi pengguna menandai delapan dari sembilan kandidat untuk
  ditinjau. Data sesi pribadi dan video pengguna tidak disertakan dalam paket.
- Uji installer pada salinan Studio 2.0: dry-run, hash payload, pelestarian profil
  dan data pekerjaan, pemuatan sesi lama, serta rollback. Hasil rinci tersedia
  dalam PACKAGE_TEST.json di dalam ZIP.

## Batas verifikasi

- FFmpeg 9.0.1 dan NVENC pada Windows/RTX 3050 belum dijalankan langsung di sini.
  Jalur modern diverifikasi pada unit test; probe di CEK_PRO menguji sintaks,
  subtitle, dan encode pada binary FFmpeg yang benar-benar terpasang di laptop.
- Pemeriksaan konteks dengan Qwen diuji menggunakan respons terkontrol; kualitas
  keputusan Qwen pada percakapan asli belum dibenchmark. Mekanisme konservatif
  mempertahankan kandidat lama ketika perbaikan tidak lolos pemeriksaan.
- Browser Chromium tidak tersedia di lingkungan ini dan unduhan browser uji
  gagal. Pengujian UI memakai DOM simulasi; tata letak piksel di Chrome Windows
  dan display scaling laptop masih perlu diperiksa saat dipakai.
- DaVinci Resolve Free 21.0.4 dan CapCut 9.5 tidak dijalankan. Ekspor native tetap
  memiliki keterbatasan Studio 2.0; split materi/pembicara perlu disusun ulang
  di editor. MP4 memakai komposisi renderer.
- Target seluruh batch 30 menit, akurasi transkrip, dan performa FYP belum terbukti.

Dua peringatan deprecation dari dependensi test Starlette/httpx tidak menyebabkan
kegagalan pengujian. Tidak ada dependensi baru pada aplikasi runtime.
