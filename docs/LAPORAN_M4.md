# Laporan implementasi Clipper Pro 4.0.15 M4

Dasar kode M3: commit lokal **11d34a18351997d01c99a397ccc2bce41839885a**, paket M3 SHA256 **03a1e39e9a14d3777b2baa3a3c08004a367ee1b20edf7d4b948d75cb417ae153**. GitHub terakhir yang diperiksa masih M2: **b8d12eb972b742a75379c39dc8fa7d35752b9e5e**. M4 dibuat sebagai overlay kumulatif untuk dua dasar yang dikenal tersebut.

Spesifikasi: Arsitektur_Clipper_Pro_Terpadu_120_Halaman (2).pdf, 120 halaman, SHA256 **76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36**. M4 halaman 49; VF01–VF17 halaman 92–94.

## Cakupan enam paket

| Paket | Persyaratan | Implementasi |
|---|---|---|
| M4.1 | VF01, VF02, VF09, VF12 | Scan cut FFmpeg, frame bertimestamp aktual, detektor lokal dengan digest bobot, asosiasi track konservatif, OCR/area manual dan protected geometry |
| M4.2 | VF03, VF15 | ASD lokal opsional + suara/diarization, hubungan suara-wajah yang ditinjau, overlap/off-screen/occlusion/no-face/frozen-evidence fallback |
| M4.3 | VF04, VF05, VF13 | No-pan, tracking opt-in dengan deadzone/smoothing/speed cap, source keyframe dan lock manual |
| M4.4 | VF07, VF08, VF10, VF11 | Grid hingga empat orang, layar/PiP/gameplay, dominasi materi dan scene continuity dengan layer pixel yang sama di final |
| M4.5 | VF06, VF14, VF16 | Dua rasio utama + 1:1/4:5/custom, blur/pillarbox, LK/RANSAC object/planar tracking, drift stop dan attachment |
| M4.6 | VF17 | Validasi propagasi SAM, carrier kontinu lossless, alpha di compositor final dan source-clock mapping |

**Implementasi workflow berbeda dari penerimaan corpus. G4 masih pending.** Tidak ada klaim bahwa deteksi wajah/ASD/tracking/SAM sudah lulus video asli atau bahwa hasilnya otomatis setara editor profesional. Unknown confidence tidak dibuat menjadi angka nol/peluang pasti.

## Perubahan konkret

- API camera4, job camera_m4 dan panel M4 terhubung ke SQLite/CAS/lease/histori. Proposal membutuhkan keputusan manusia terpisah sebelum aktif.
- Canonical camera cut dipisahkan dari perubahan layout/voice. Shot ID bersumber dari identitas dan waktu sumber.
- Frame sampel menyimpan waktu decoded yang diukur, waktu permintaan, path dan hash. Sampel terakhir mengambil frame sebelum waktu yang diminta, termasuk dekat EOF.
- Track geometris tidak menjadi identitas suara otomatis. Asosiasi ambigu/cut tidak menggabungkan ID wajah berbeda. Largest-face bukan pemenang speaker ketika ASD tidak tersedia.
- Pin/area manual lama diwariskan saat masuk M4. Crop terkunci dan keyframe tidak boleh menyembunyikan materi/HUD penting.
- Komposisi memakai source crop, viewport, platform safe rectangle, protected output dan caption band. Scene/crop per rasio tidak mengubah source spans atau ucapan.
- Reorder/rate/reverse/freeze mengikuti clock M1. Alternate camera atau kurva transformasi M1 memerlukan scope analisis tersendiri dan tidak digabung diam-diam.
- Gerak/mask/attachment diproses menjadi source layer melalui stream CPU dengan memori frame terbatas; graph FFmpeg tidak tumbuh satu branch per frame.
- Object/planar tracker mengukur fitur dan reverse-flow consistency serta RANSAC; cut/drift/occlusion menghentikan attachment.
- SAM diagnostik satu frame tidak cukup untuk carrier kontinu. Semua timestamp/source/ukuran/sample diverifikasi. Carrier full-rate memakai sample hold dan tidak disebut neural 30 fps.
- Perubahan source, clock, speaker, kontrol, attachment atau bukti mask memengaruhi validitas/cache. Style yang tidak mengubah input kamera tidak memaksa analisis kamera ulang.
- Cancel/gagal/conflict mempertahankan laporan dan final sebelumnya. Copy ke rasio lain tetap memerlukan review serta coverage/speaker yang sesuai.
- Rasio tambahan eksplisit; default M3 tetap dua hasil. Ekspor M4 memakai baked source layer pada Hibrida/Tampilan terjaga; native dasar yang belum memetakan geometri ditolak.

## Bukti pengujian

Regresi final: **1.399 tes terkumpul; 1.338 lulus, 61 dilewati, 0 gagal, 0 error**. Seluruh **95 tes khusus M4** lulus. **13 suite UI** lulus, termasuk **12 kelompok perilaku panel M4**. Rincian berada di **verification/summary.json**, log dan JUnit. Tes mencakup kontrak/geometry, API/SQLite/queue/CAS, fallback speaker, cache/digest/bukti, lima rasio, source color/order, full decode, no-pan, motion, matte/freeze, attachment warp, core caption pipeline/ArtifactSet, UI DOM dan installer.

Media uji adalah **sintetis** dengan warna/nada dan timing/geometry authored. Sampel mask merupakan protocol double yang diberi label; bukan inference SAM nyata. Uji core menggunakan renderer caption sebenarnya dan pemeriksaan artifact, bukan MP4 kosong. Shot scan, decode, matte carrier dan streaming layer memakai FFmpeg/Pillow/NumPy nyata.

UI menggunakan DOM adapter Node. Neural provider lokal dan OpenCV tracking native pada video asli belum diuji di host ini. Lingkungan tidak menyediakan wheel OpenCV yang diminta; tes lama yang memerlukan native CV/pyCapCut/corpus lama tetap memakai gate yang jujur. Kegagalan fungsi tidak dipindahkan menjadi skip.

Pemasangan, reinstall idempotent, preservasi file/SQLite dan rollback byte-for-byte lulus pada tiga dasar: GitHub M2 (413 file publik terverifikasi, tanpa membaca .env.pro privat), M2 awal (396 file), dan M3 yang dikirimkan (426 file). Runtime probe native memakai double eksplisit.

Historical installer M3 dibangun dari producer frozen dengan setiap teks dan archive yang diikat hash asli. Ini mencegah paket bertanda M3 memasukkan import M4 yang tidak lengkap. Archive historis tetap immutable; arsip lokal m0_fixture.zip tidak diperiksa/diganti.

## Status yang belum dinyatakan lulus

- Corpus G4 dua/tiga orang, papan/layar, occlusion, overlap/off-screen, no-face/no-pan dan gestur nyata.
- Detektor/ASD/OCR/SAM dan object/planar tracker native pada model serta sumber pengguna.
- Mesin i5/RTX pengguna, Windows browser/zoom, NVENC dan import CapCut native.
- Alpha temporal gesture quality; sample hold dapat memperlihatkan stepping pada gerak cepat.
- Geometri kamera/mask/attachment sebagai efek native yang dapat diedit di editor tujuan.
- Pembacaan teks DaVinci tetap ditunda; typography M5 dan audio M6 belum dikerjakan dalam M4.

Sumber teknis primer: [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html), [OpenCV tracking](https://docs.opencv.org/4.10.0/dc/d6b/group__video__track.html), dan adapter model lokal yang sudah ada pada repository. Ini mendukung protokol implementasi, bukan angka akurasi corpus.

