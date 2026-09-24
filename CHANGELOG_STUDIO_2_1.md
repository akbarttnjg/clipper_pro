# Studio 2.1.0

- Menguji sintaks filter-file modern dan lama secara nyata; mendukung FFmpeg yang
  sudah menghapus `filter_complex_script` tanpa mewajibkan downgrade.
- Preflight concat/subtitle/encode sebelum analisis panjang dan sebelum render.
- Retry CPU dibatasi pada kegagalan encoder/GPU; error opsi/filter mempertahankan
  penyebab aslinya.
- Progres encoding, log per clip, penulisan MP4 melalui file sementara, penyimpanan
  rencana sebelum render, serta kelanjutan batch dan skip hasil yang sudah selesai.
- Pemeriksaan kedua awal/akhir berdasarkan konteks tersimpan. Pemeriksaan mandiri
  mendeteksi batas kata, penutup menggantung, rincian daftar, dan ekspansi singkatan
  yang tidak didukung transkrip. Pembatasan padding mencegah setengah kata berikutnya
  ikut masuk. Tersedia review ulang kandidat sesi lama tanpa Whisper.
- Panel presentasi terang dapat dideteksi; mode materi/pembicara memakai region
  terpisah. Area manual dapat ditandai pada sumber dan dibersihkan kembali.
- UI tiga panel dengan preview mengikuti ruang layar, toolbar tetap terlihat,
  waktu jam:menit:detik, playback terbatas pada clip, transkrip berbentuk paragraf,
  penanda kandidat bermasalah, dan penambahan musik ke sesi lama.
- Nama asli file dipertahankan untuk unggahan baru. Kunci Pexels tidak dikirim
  melalui endpoint pengaturan editor.
- Installer pembaruan offline secara default. Profil lokal dan data pekerjaan
  tidak menjadi payload pembaruan; backup serta rollback kode tetap tersedia.

Perubahan tidak menjanjikan FYP, review AI sempurna, waktu batch 30 menit, atau
kesetaraan penuh proyek native dengan MP4. Lihat laporan pengujian.
