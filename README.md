## Upgrade 4.0.18 — perbaikan M6 + M7

Enam temuan audit M6 diperbaiki; M7 menambahkan delivery atomik lintas rasio,
lima sidecar, media/font portabel, kandidat editor CapCut 4.7.0 / Resolve 18.6.6,
XML/FCPXML/OTIO, clean/alpha/stem, publish kit dan tautan review lokal dengan
izin/expiry. G6/G7 native/human acceptance tetap pending; EX05 text/font backlog.
Baca [panduan pemasangan](docs/UPGRADE_4_0_18_M6_M7.md),
[laporan](docs/LAPORAN_M7.md) dan [trace EX01–13](docs/M7_REQUIREMENTS.json).

# Clipper Pro 4.0.17 · M6 audio, musik dan mix

M6 melanjutkan perbaikan M0–M5 4.0.16.1. Lima paket audio mencakup master loudness/limiter, restoration dan Demucs lokal opsional, musik/ducking, track SFX/voiceover/dubbing, serta cleanup yang ditinjau dan audiogram. Baca [panduan M6](docs/UPGRADE_4_0_17_M6.md), [laporan M6](docs/LAPORAN_M6.md) dan [AU01–AU15](docs/M6_REQUIREMENTS.json). G6 uji dengar video asli dan model/native target masih pending.

## Perbaikan audit M0–M4 · 4.0.15.1

Paket kumulatif memperbaiki 18 temuan yang direproduksi pada rilis GitHub M4. Paket lama M0–M2 tidak perlu dipasang lebih dahulu. Baca [panduan pemasangan](docs/UPGRADE_4_0_15_1_M0_M4.md). Acceptance G2/G3/G4 pada corpus asli dan perangkat tujuan masih perlu diselesaikan.

# Clipper Pro 4.0.15 M4

M4 menambah kamera/layout per shot, no-pan dan tracking opt-in, speaker fallback, grid/layar/PiP/gameplay, rasio tambahan, serta carrier mask kontinu ke compositor. Gunakan [panduan M4](docs/UPGRADE_4_0_15_M4.md), [laporan M4](docs/LAPORAN_M4.md) dan [register VF01–VF17](docs/M4_REQUIREMENTS.json). Komposisi perlu ditinjau sebelum aktif; G4 corpus/model native belum dinyatakan lulus. Paket kumulatif mengenali M3 serta M2 yang telah diverifikasi.


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


## Perbaikan audit kumulatif 4.0.16.1 (M0-M5)

Paket ini menggabungkan 18 perbaikan M0-M4 dan delapan temuan M5 pada basis GitHub 9dd8e73. Lihat `docs/UPGRADE_4_0_16_1_M0_M5.md` untuk pemasangan langsung, rollback, dan uji pada mesin pengguna. Ledger 26 temuan ada di `docs/M0_M5_REPAIRS_4_0_16_1.json`. Status perbaikan dibatasi pada regresi yang tercatat; corpus nyata, Windows/GPU dan G2-G5 masih perlu penerimaan.
