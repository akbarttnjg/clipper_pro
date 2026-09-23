# Laporan pengujian Clipper Studio Local 2.0

Tanggal: 23 September 2026. Basis kode fork:
`akbarttnjg/clipper_pro @ 7d74f843e7a851fb88af8bf66d0dc7d311a5c2ae`.

Pengujian dilakukan di lingkungan Linux pengembangan, Python 3.12, dengan FFmpeg
CPU. Hasil ini bukan pengujian langsung pada laptop Windows pengguna.

| Area | Pemeriksaan | Hasil |
|---|---|---|
| Regresi Python | `python -m pytest clipper/tests -q` | 58 lulus; 2 peringatan deprecation test client |
| Seleksi topik | Batas sumber, kutipan penutup, deduplikasi, fallback manual, cache | Lulus dengan respons model fixture; bukan pengukuran kualitas Qwen pada podcast |
| API dan sesi | Koreksi transkrip, validasi waktu, simpan/pulihkan sesi, revisi ekspor, origin | Lulus |
| Antarmuka | jsdom: sumber lokal, kandidat, koreksi kata, simpan, render, preview, escaping | Lulus; tata letak di browser Windows belum diuji langsung |
| Render vertikal | MP4 H.264 1080 x 1920, 30 fps, audio, durasi 18,5 detik | Lulus ffprobe/QC |
| Render horizontal | MP4 H.264 1920 x 1080, 30 fps, audio, durasi 18,5 detik | Lulus ffprobe/QC |
| Tipografi | Inspeksi gambar render; penyesuaian metrik PIL/libass | Frasa dua baris dan aksen serif/warna diperiksa secara visual |
| Komposisi video nyata | Render 4 detik dari contoh clip pengguna, 360 x 640 | Lulus teknis; sumber sudah memiliki subtitle, bukan contoh hasil editorial baru |
| Audio | Stem suara, musik, efek, mix; fixture suara dengan jeda | Musik pada jeda sekitar 5,3 kali RMS musik saat suara aktif |
| Native editor | XML: kontinuitas video/audio; JSON: dua timeline dan materi; sintaks Lua/Fusion | Lulus pemeriksaan struktur/sintaks; belum diimpor dalam aplikasi editor |
| Installer | Dry run, checksum, penolakan path keluar, backup, rollback, kegagalan copy, perlindungan edit baru | Lulus tes otomatis |

Render fixture 18,5 detik memerlukan sekitar 27 detik per rasio dengan CPU lingkungan
pengembangan. Fixture ini berisi pola gambar/audio sintetis, sehingga **tidak dapat
dipakai untuk memperkirakan waktu video podcast dua jam**.

## Yang masih memerlukan uji pada laptop pengguna

- Whisper `medium` dan Qwen `qwen3:8b` secara menyeluruh pada video berbahasa Indonesia
  1–2 jam; termasuk nama, angka, pembuka/penutup topik, dan kualitas kandidat.
- NVENC nyata pada RTX 3050, runtime CUDA, konsumsi VRAM/RAM, serta target 30 menit.
  Tes unit memverifikasi penanganan kegagalan dan fallback; tidak membuktikan kinerja GPU.
- Impor DaVinci Resolve **Free 21.0.4** dan CapCut **9.5.0**. Format native bersifat
  eksperimental. Gagal impor tidak membatalkan MP4 final yang telah dirender.
- Tampilan antarmuka pada browser pengguna dan semua kombinasi media/codec Windows.

## Batas hasil native

MP4 memuat komposisi akhir. Proyek editor mempertahankan sumber dan lapisan editable,
tetapi belum identik: warna Fusion statis, zoom Resolve berupa marker untuk pengaturan
keyframe, dan mode materi+pembicara perlu disusun ulang di editor. Metrik font juga bisa
berbeda. CapCut multi-timeline memiliki alternatif draft per clip.

Video sumber direferensikan dari path asli. Paket proyek membawa WAV dan font, tetapi
tidak menyalin video sumber panjang. Simpan sumber dan folder proyek di lokasi tetap.

Tidak ada klaim jaminan FYP atau akurasi editorial otomatis. Preview, koreksi manusia,
dan hasil uji pada media nyata menjadi dasar penilaian kualitas.

## Bukti pengujian paket

`PACKAGE_TEST.json` pada akar ZIP mencatat hasil pemasangan ke salinan instalasi,
pemeriksaan checksum semua file payload, dan pemulihan. Pengujian ini memakai
`--skip-deps`; instalasi paket Python melalui internet/Windows belum dijalankan di sini.
