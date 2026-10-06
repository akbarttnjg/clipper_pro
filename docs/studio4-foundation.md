# Fondasi ekspor dan revisi Studio 4

Perubahan ini memperbaiki kegagalan ekspor CapCut akibat pembulatan waktu, laporan paket yang keliru menyatakan lolos, dan hilangnya petunjuk penekanan subtitle setelah kata menjadi token tampilan. Basis kode: `20b45e89fd0f1362c37c2b9178493aec10b57ac2`.

Dua hasil video pengguna mempunyai rasio berbeda sesuai pilihannya. Klip berbeda boleh mempunyai durasi dan rasio berbeda. Pengujian dua timeline tidak mewajibkan setiap cerita dibuat dalam kedua rasio.

## Perubahan yang dapat diperiksa

| Bagian | Perilaku baru |
|---|---|
| Waktu video CapCut | Batas frame dikonversi menjadi mikrodetik dengan FPS rasional. Durasi dihitung dari dua batas yang sudah dikonversi. Track video harus tersambung tanpa celah atau overlap. |
| Teks dan audio | Batas teks memakai konversi endpoint yang sama; waktu subframe dipertahankan. Audio tidak dipaksa menjadi frame video. |
| Beberapa timeline | Setiap draft mendapatkan UUID baru. ID tetap dari template pycapcut tidak lagi menyebabkan folder timeline pertama tertimpa timeline berikutnya. |
| Paket lengkap | Validator memeriksa rencana, referensi MP4, media, stem, ASS/SRT, kredit, font, panduan, installer, XML/Fusion, draft dan wrapper CapCut. |
| Status per editor | Status pembuatan, struktur, dan uji impor native dicatat terpisah untuk CapCut dan Resolve. Kegagalan satu editor tetap terlihat saat editor lainnya berhasil. |
| Font | Berkas font yang digunakan harus ada, dapat dibaca, dan mempunyai family/style sesuai rencana. Ketersediaan font di aplikasi editor masih memerlukan uji lokal. |
| Taut ulang Windows | Path dengan backslash, backslash ganda, URI XML, dan JSON font di dalam JSON draft ikut diperbarui. Kasus lama dengan `created_root` sudah berpindah tetapi path media tertinggal juga ditangani. |
| Pemasangan draft | Paket versi 4 memerlukan laporan per editor. Struktur gagal, aset hilang, atau checksum media/font berbeda menghentikan pemasangan sebelum indeks proyek CapCut diubah. |
| Penekanan subtitle | Tanda tangan penilaian diperiksa terhadap konteks sumber lengkap yang sudah dikoreksi. Token tampilan tetap membawa identitas asal. Penilaian usang atau origin tidak valid tidak memberi penekanan. |
| Revisi aktif | API menolak ekspor sebelum masuk antrean jika final hilang, berubah, atau berasal dari masukan lama. UI menunjukkan tindakan render yang diperlukan dan menonaktifkan tombol paket sampai final sesuai. |
| Usulan ilustrasi | Usulan saat B-roll off dan aset yang dinonaktifkan tidak membatalkan final yang masih sesuai. Mengaktifkan atau mengubah bahan yang dipakai tetap membatalkannya. |
| Judul Resolve | Jika ada B-roll, judul memakai track video keempat, terpisah dari track teks utama. |

Manifest paket menjadi versi 4 dan laporan verifikasi menjadi schema 2. Mode ekspor tetap **hibrida**: teks, audio dan ilustrasi terpisah; framing dan zoom sumber menyatu pada video tanpa teks. Native import selalu berstatus `not_tested` sampai diuji di aplikasi tujuan.

Versi cache berubah menjadi `studio4-content-v2`. Final lama akan ditandai usang agar perbaikan konteks subtitle diterapkan pada render berikutnya. Video, koreksi manual, dan riwayat yang tersimpan tetap tersedia.

## Hasil pengujian pada perubahan ini

| Pemeriksaan | Hasil |
|---|---|
| Regresi terarah: ekspor, konteks kata, service Studio 4, installer dan kontrak | **71 passed** |
| Seluruh suite, dilanjutkan setelah kegagalan collection | **232 passed, 25 failed, 7 errors**. Semua kegagalan/error yang teramati berakhir pada `ModuleNotFoundError: cv2`; suite penuh belum lulus. |
| ZIP ekspor yang diberikan pengguna | Draft CapCut dan Resolve berhasil dibuat ulang; validator baru menyatakan struktur keduanya lolos. |
| Sambungan video kasus pengguna | 13 shot / 2.921 frame / 30 FPS / **97.366.667 mikrodetik**, tanpa overlap atau celah. Sebelumnya ada dua overlap dan tiga celah sebesar 1 mikrodetik. |
| Subtitle kasus pengguna | 47 kelompok dipertahankan. Kasus ini tidak dipakai untuk mengklaim penekanan semantik otomatis karena penilaian editorial awalnya masih membutuhkan tinjauan. |
| Dua klip dalam satu paket | Portrait 97,366667 detik dan landscape 52,466667 detik dapat diekspor bersama dengan ID timeline terpisah. Media pada unit test ini sintetis. |
| Fixture API/UI | API Studio, SQLite, berkas FFmpeg sintetis, penolakan ekspor usang, serta antrean render kemudian ekspor lolos. Penyelesaian worker berat disimulasikan khusus untuk fixture UI. |
| Pemeriksaan kode | Kompilasi Python, sintaks JavaScript dan `git diff --check` lolos. |
| Playwright | Belum berjalan: executable Chromium tidak tersedia. Runner browser disediakan untuk lingkungan yang mempunyai browser. |
| Editor Windows | CapCut 9.5, Resolve Free 21.0.4, NVENC dan perangkat pengguna belum diuji pada perubahan ini. |

PyPI tidak dapat diakses di lingkungan pengembangan ini. Dependensi pengujian Python yang tersedia disiapkan dari sumber resmi dan disimpan di lokasi sementara, tanpa perubahan requirements aplikasi. Serializer pycapcut memakai kode versi 0.0.3 dari commit `27480a1e954740af50363076e6fea94f2893ae93`. Library native MediaInfo tidak tersedia: unit test mengendalikan batas metadata, dan regresi ZIP memakai metadata FFprobe dari media nyata. Kelas material, segmen, track, dan serializer pycapcut tetap dijalankan. Ini membuktikan pembentukan draft serta struktur paket, bukan keberhasilan impor desktop.

## Mengulang pemeriksaan

Di lingkungan dengan dependensi aplikasi/pro terpasang, jalankan:

```bash
python -m pytest clipper/tests/test_export_foundation.py clipper/tests/test_studio_foundation.py clipper/tests/test_studio4.py clipper/tests/test_installer.py clipper/tests/contracts -q
python -m pytest -q
```

Fixture tambahan memakai folder uji tersendiri dan tidak menjalankan worker model:

```bash
python -m clipper.tests.studio4_foundation_server --output /lokasi/uji-fondasi --check
```

Untuk memeriksa UI di browser, jalankan fixture tanpa `--check`, lalu runner dari terminal kedua:

```bash
python -m clipper.tests.studio4_foundation_server --output /lokasi/uji-fondasi --port 8769
node clipper/tests/studio4_foundation_ui.cjs http://127.0.0.1:8769/ /lokasi/uji-fondasi
```

Runner memerlukan Playwright dan Chromium. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` dapat menunjuk executable yang terpasang. API `__test/complete-render` hanya ada pada server fixture ini; aplikasi produksi tidak menyediakan endpoint tersebut.

## Batas tahap pertama dan pekerjaan berikutnya

Bagian implementasi dari backlog awal mengenai waktu, interval, status editor, kelengkapan paket, font, path, lineage, dan alur revisi sudah mendapat perbaikan serta regresi. Validasi adapter CapCut 9.5 dan Resolve 21 di editor asli tetap terbuka. Verifikasi native perlu mencatat versi editor, jumlah timeline, media online, baseline font, animasi, offset B-roll, sinkronisasi audio, dan durasi, lalu membandingkan pembuka/tengah/penutup terhadap `Reference`.

Tahap berikutnya dalam laporan besar tetap mencakup katalog/installer 26 komponen, penjadwalan VRAM, pemilihan cerita, framing pembicara/materi, preset kreatif, dan relevansi ilustrasi. Perubahan fondasi ini belum menjadi bukti bahwa kualitas video asli, akurasi Whisper/Ollama, atau integrasi seluruh komponen tersebut sudah lulus.
