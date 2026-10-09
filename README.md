# Clipper Studio 4.0.8

Mesin pemotongan video lokal: transkripsi, pemilihan cerita, koreksi ucapan, framing, subtitle, audio, serta hasil 9:16 dan 16:9. Model ASR dan Ollama memakai instalasi lokal. Jumlah klip mengikuti pembahasan unik yang lolos tinjauan.

Gunakan paket Pembenahan Lengkap dan [panduan pemasangan](docs/PEMBENAHAN_LENGKAP.md). Dasarnya adalah kode 4.0.7 yang telah diverifikasi terhadap commit GitHub `9e0677c60605be0d16a6f19eebf8cb12094a3531`. Pemasang memeriksa checksum, mencadangkan kode dan database, serta menyediakan rollback.

Jalankan `JALANKAN_PRO.cmd`, lalu buka `http://127.0.0.1:8765` dan tekan Ctrl+F5 setelah pembaruan. Pada **Periksa / ekspor**, pilih klip, terapkan preset Adaptif atau Rapi bila diinginkan, lalu tekan **Render seluruh pilihan · 9:16 + 16:9**. Setelah seluruh final tersedia, satu paket dapat mencakup semua klip terpilih dalam kedua rasio.

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
