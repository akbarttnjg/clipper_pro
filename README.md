# Clipper Pro 4.0.14 M3

Mesin video clipping lokal dengan seleksi cerita bersumber, query ulang tanpa ASR ulang, review kandidat, dan susunan beberapa segmen untuk dua rasio. M3 melanjutkan editor M1 serta ingest/transkrip M2. Proyek baru dapat mengantrekan M3 setelah transkrip tersimpan; proyek lama mempertahankan alur tersimpan.

Gunakan [panduan M3](docs/UPGRADE_4_0_14_M3.md), [laporan M3](docs/LAPORAN_M3.md), dan [register CL01–CL19](docs/M3_REQUIREMENTS.json). Installer memeriksa dasar M2, mencadangkan kode/SQLite, dan menyediakan pemulihan. Jalankan JALANKAN_PRO.cmd lalu Ctrl+F5. Kandidat M3 harus diterima setelah diperiksa pada sumber sebelum masuk final; skor model terpisah dari keputusan tersebut. Gate corpus nyata G3 dan model/GPU/native Windows tetap memerlukan penerimaan target.

Bukti kode/API/SQLite/FFmpeg dan batas lingkungan disertakan dalam paket. Gate Windows/GPU/video asli/native editor serta usability tetap memerlukan penerimaan target. Resolve teks/font ditunda; efek waktu/keyframe sumber M1 berstatus baked pada ekspor.

## Perilaku utama

- Crop pembicara memakai area kepala yang teramati. Tekstur latar tidak otomatis dianggap materi. Materi, OCR, dan area yang ditandai pengguna tetap dilindungi.
- Ruang subtitle dicari sebelum gambar diperkecil. Crop, strip subtitle dan zoom menggunakan geometri yang sama saat render.
- Footage dengan fakta ucapan sama dideduplikasi walaupun judul/kutipan intinya berbeda. Klaim dengan angka berbeda dipertahankan.
- Template manual dapat dikunci. Preset memakai font terukur, penekanan makna dengan negasi/angka utuh, gerak terbatas dan waktu baca pada jeda nyata.
- Diagram opsional berasal dari perbandingan atau daftar singkat yang lengkap dalam ucapan. Ucapan biasa tidak dibuat menjadi kartu kutipan berulang.
- Dialog dinormalisasi dan di-cache lintas rasio. Musik lokal memakai ducking; SFX dibatasi jumlah dan jaraknya.
- Paket hibrida memisahkan caption, stem audio dan ilustrasi. Media identik dipakai bersama. Video tanpa teks dan media paket diperiksa dengan checksum.

## Mode editor dan batas pengujian

**Tampilan terjaga** menyalin MP4 final persis. **Hibrida** mempertahankan framing dalam video tanpa teks dan menyediakan teks/audio terpisah. **Native dasar** tersedia untuk crop statis yang didukung. CapCut memakai format draft tidak resmi; Resolve memakai XML dan script Lua/Fusion. Blur/fade/font native dapat berbeda dari MP4 rujukan.

Struktur paket dan impor editor merupakan pengujian terpisah. Impor, edit, render, simpan dan buka ulang pada CapCut 9.5 / Resolve 21 harus diperiksa di perangkat sasaran. Remotion dan Motion Canvas digunakan bila runtime lokal siap; renderer subtitle FFmpeg tetap tersedia.

## Diagnosis dan performa

`CEK_PEMBENAHAN.cmd` membuat laporan modul, font, runtime, model alignment dan perangkat. Setelah server ditutup:

```bat
CEK_PEMBENAHAN.cmd --alignment --project ID_PROYEK
CEK_PEMBENAHAN.cmd --benchmark --project ID_PROYEK
```

Alignment mengukur koreksi tersimpan tanpa menerapkan timing hasil uji. Benchmark merender klip terpilih dalam kedua rasio, kemudian mengukur pemakaian ulang final. ASR/discovery dan impor editor tidak dihitung; waktu 30 menit untuk pemrosesan penuh belum dijamin.

## Pengembangan

Uji utama memakai `unittest`; pengujian HTTP/SDK tambahan memakai `pytest` pada lingkungan aplikasi yang lengkap. Fixture geometri terkontrol dipisahkan dari bukti detektor sebenarnya. Laporan QA dan alat replay berada dalam `docs/verification` dan `tools`.

Model, video, runtime, `.venv`, `node_modules`, `.env.pro` dan cadangan lokal diabaikan oleh Git. Jangan memasukkan bobot model atau rahasia ke riwayat repository.
