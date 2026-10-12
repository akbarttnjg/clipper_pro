# Clipper Studio 4.0.11 — M0

Paket ini memasang fondasi M0 dari laporan arsitektur terpadu. Dasarnya Clipper
4.0.10 pada commit `6682f0b4e633af6ca830e63754ac3d46fc100bbf`.
Pemasang memeriksa isi berkas, bukan hanya label versi di browser.

## Pemasangan

1. Simpan backup proyek dari panel **Pemulihan & backup**. Hentikan pekerjaan
   aktif, lalu tutup server dengan Ctrl+C.
2. Ekstrak ZIP ke folder baru di luar `C:\AI\clipper`.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`; pilih folder instalasi lama berisi
   `app.py`, `clipper`, dan `.venv`.
4. Jika pemeriksaan lulus, jalankan `PASANG_M0_4_0_11.cmd` pada target yang sama.
   Pemasang membuat backup kode dan salinan SQLite konsisten sebelum menyalin.
5. Jalankan `JALANKAN_PRO.cmd` dari folder mesin, lalu Ctrl+F5 di browser.

Paket tidak mengunduh model atau memasang pustaka. `.env`, video sumber, data
proyek, model dan font pribadi tidak menjadi payload. Jika ada kode lokal yang
berbeda, pemasang berhenti sebelum penyalinan; simpan perbedaannya untuk ditinjau.

## Pemeriksaan pada laptop

Lakukan pada proyek uji dari salinan video asli, sebelum render panjang:

1. Di **Komponen & perangkat**, pilih sumber dan index track audio yang sama
   dengan proyek. Jalankan uji sampel ASR lokal pada CPU, lalu CUDA jika tersedia.
   Centang **Wajib gunakan perangkat pilihan** untuk pengukuran CUDA yang ketat.
   Periksa perangkat aktual, fallback, track audio, dan hasil ucapan.
2. Buat preview serta render final 9:16 dan 16:9. Periksa audio, subtitle, fps,
   batas potongan dan resolusi. Hasil baru disimpan sebagai set immutable.
3. Simpan timing manual kata. Render ulang dan pastikan waktu tersebut bertahan.
4. Ubah `num_clips` saja, render ulang dan periksa receipt `cache_reused: true`;
   ubah warna subtitle lalu pastikan encode baru dipakai.
5. Batalkan satu render aktif. Tunggu status **Dibatalkan** dan pastikan proses
   anak berhenti, hasil lama tetap dapat dibuka, dan antrean dapat dilanjutkan.
6. Putuskan internet setelah model disiapkan. Ulangi render dan uji model lokal;
   model yang belum tersedia harus memberikan pesan, tanpa unduhan tersembunyi.
7. Ekspor hybrid ke CapCut 4.7.0 yang sudah digunakan. Buka, edit teks, simpan,
   buka kembali, dan bandingkan render. Catat bukti editor native tersebut.

Uji pengembangan mencakup Linux/CPU, FFmpeg nyata, SQLite nyata, render dua rasio,
cache, pembatalan proses, kegagalan penyimpanan, dan installer. Hasil itu tidak
membuktikan kualitas ASR video asli, CUDA RTX 3050, atau tindakan di editor
Windows. Resolve Free 18.6.6 mengikuti kebijakan penundaan pembenahan teks/font
dari laporan; sasaran CapCut utama tetap berlaku.

## Pemulihan

Tutup server, lalu jalankan `PULIHKAN_M0_4_0_11.cmd`. Rollback memulihkan kode
yang dicadangkan dan menghapus modul baru dari pemasang. Edit proyek setelah
upgrade tetap berada dalam database; kolom tambahan SQLite kompatibel dengan
kode 4.0.10. Salinan database sebelum pemasangan berada di folder backup untuk
pemulihan terpisah yang dipilih secara sadar.

Kegagalan render tidak mengganti pointer hasil lama. Staging yang terputus
dipertahankan untuk diagnosis. `clipper.artifact_store.recovery(root)` melaporkan
set tidak lengkap atau sealed yang belum diketahui referensinya; tidak
mempromosikan hasil tanpa transaksi proyek.

## Batas milestone

M0 berisi enam paket fondasi. Pencarian teks koreksi (X06) berada di M1.4;
pengukuran raster glyph/kontras dan perombakan komposisi menyeluruh berada di M5.
Perbaikan batas blur legacy pada rilis ini mempertahankan validator ketat,
dan tidak menyatakan seluruh audit geometri selesai.
