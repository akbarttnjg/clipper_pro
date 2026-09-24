# Laporan pengujian Studio 2.2

24 September 2026. Pengujian lokal Linux dengan encoder CPU libx264.

## Sudah dijalankan

- **91 pengujian Python lulus**: seluruh regresi sebelumnya, integritas angka dan
  timestamp, batas kata pada pergantian bagian, lima template pada dua rasio,
  posisi teks sepanjang animasi, area tipografi khusus, deteksi panel terfragmentasi,
  headroom wajah, styling batch tanpa mengubah transkrip/batas topik, penolakan
  perubahan saat job sibuk, relink media paket, dan penulisan audio secara atomik.
- **Pengujian UI dengan jsdom lulus**: alur sumber lokal, kandidat, escaping teks,
  koreksi kata, timecode, playback berbatas, area manual, review, render, preview,
  lima kartu galeri, pemilihan gaya, intensitas, dan penerapan ke clip terpilih.
- **Lima preview template** 960×540, 30 fps, masing-masing 9,8 detik dirender memakai
  ASS dari engine yang sama. Frame diperiksa secara visual.
- **Render 1080×1920, 18 detik** dari area gambar yang diambil dari render pengguna
  sebelumnya. Area ini tidak memuat subtitle lama. Materi terdeteksi otomatis,
  komposisi materi/pembicara digunakan, teks berada pada ruang di antaranya,
  dan `2,5 juta` tidak terpecah ke frasa lain. Ini contoh tipografi/komposisi,
  bukan hasil seleksi AI baru atau evaluasi video sumber penuh.
- **Render 1920×1080, 18,5 detik** dengan pola uji: gerak geser teks, caption kiri,
  kutipan pembuka dari sumber, musik dan efek suara terpisah. QC durasi, resolusi,
  video dan audio lulus. Pola uji tidak menunjukkan kualitas editorial konten.
- **Paket proyek dua clip berhasil dibuat**: dua timeline XML Resolve, komposisi
  Text+ dengan spline, dua draft CapCut dan wrapper multi-timeline, keyframe
  gerak/ukuran teks, font, ASS/SRT dan video tanpa teks. Referensi media serta
  rentang keyframe diperiksa. Paket dipindahkan, kemudian relink berhasil.
- Satu percobaan ekspor mendeteksi WAV yang belum utuh. Penulisan audio kini
  melalui file sementara, error durasi diberi keterangan, dan perbedaan pembulatan
  metadata audio hingga 2 ms ditangani. Ekspor ulang paket dua clip berhasil.
- Uji installer pada salinan Studio 2.1 mencakup dry-run, hash payload, pemuatan
  sesi tersimpan tanpa analisis, pelestarian data/profil dan rollback. Hasil
  per paket tercatat di `PACKAGE_TEST.json` dalam ZIP.

## Belum diverifikasi langsung

- CapCut 9.5 dan Resolve Free 21.0.4 pada Windows. File native telah diperiksa
  strukturnya; tampilan/import di aplikasi belum dapat dipastikan identik.
- Blur dan fade pada track teks native CapCut belum dipetakan. MP4/ASS memakai
  efek lengkap. Framing dan zoom pada proyek menyatu dalam video tanpa teks.
- Chrome Windows dengan scaling layar laptop: UI diuji melalui DOM, bukan
  screenshot browser langsung. Galeri responsive tetap perlu dilihat di layar pengguna.
- FFmpeg 9/NVENC pada RTX 3050 pengguna. Pemeriksaan runtime yang sudah ada tetap
  menguji binary FFmpeg sebenarnya sebelum render; lingkungan uji ini memakai CPU.
- Analisis sumber 1–2 jam dan target total 30 menit pada i5-12500H. Transkrip,
  batas topik dan retensi penonton tetap perlu dinilai terhadap sumber sebenarnya.

Dua peringatan deprecation pada dependensi pengujian Starlette/httpx tidak
menyebabkan kegagalan. Tidak ada layanan berbayar atau dependensi runtime baru.
