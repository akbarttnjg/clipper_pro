# Perubahan Studio 2.0

Basis: akbarttnjg/clipper_pro @ 7d74f843e7a851fb88af8bf66d0dc7d311a5c2ae.

- Analisis dipisah dari render; review kandidat sebelum ekspor final.
- Seleksi topik lokal menggunakan segmen sumber, konteks bertumpang tindih, rubrik
  0–5, verifikasi kutipan penutup, dan pengurangan kandidat yang berulang.
- Durasi default 30–120 detik; jumlah adaptif sampai 10 kandidat berkualitas.
- Fallback kegagalan model ditandai sebagai pilihan manual, tanpa angka virality palsu.
- Kamera dikunci per adegan, dengan deteksi cut dan perlindungan komposisi materi.
- Renderer FFmpeg menggantikan pengiriman setiap frame 1080p lewat pipe Python.
- Probe NVENC 720p, log kegagalan nyata, retry CPU dan peringatan bila diperlukan.
- Output 1080p 30 fps, pilihan 9:16 / 16:9, preview singkat beresolusi kecil.
- Tipografi dua baris, ukuran berdasarkan metrik font, baseline tetap, font/warna aksen.
- Hook berupa kutipan asli dan judul awal; jeda panjang dirapikan secara konservatif.
- Musik lokal dengan ducking, efek suara opsional yang jarang, stem WAV terpisah.
- Editor batas, kata, judul, emphasis, framing, audio, dan riwayat proyek tersimpan.
- Revision ID mencegah ekspor proyek dari render yang sudah kedaluwarsa.
- Proyek DaVinci melalui XML + Lua/Fusion; CapCut draft multi-timeline eksperimental.
- Installer overlay dengan checksum, backup, transaksi pemulihan, dan rollback terjaga.

Tidak menghapus intelligence lama, sumber video, unggahan, atau hasil render sebelumnya.
Tidak ada API berbayar. Internet diperlukan untuk memasang dependensi/model yang belum tersedia.
