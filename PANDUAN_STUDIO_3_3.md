# Panduan upgrade Studio 3.3

## Pasang

1. Tutup server Clipper dengan Ctrl+C. Tutup pemutar yang sedang memakai hasil render.
2. Ekstrak ZIP sepenuhnya ke folder terpisah, misalnya Downloads/Clipper_Studio_Local_3_3. Jangan menjalankan installer dari dalam ZIP.
3. Jalankan PASANG_UPGRADE.cmd. Target bawaan C:\AI\clipper. Jika lokasi berbeda, isi lokasi ketika diminta atau jalankan:

   PASANG_UPGRADE.cmd --target "D:\AI\clipper"

4. Tunggu pesan pemasangan selesai. Jalankan CEK_PRO.cmd dan JALANKAN_PRO.cmd dari folder aplikasi.
5. Buka localhost:8765, tekan Ctrl+F5, lalu pastikan label LOKAL 3.3.

Installer membutuhkan Studio 3.2 dari commit 5b1020a600e7d7a5d3a97f92bacf996be0ee0f93, atau versi 3.3 paket ini. File baru dan file yang memang berubah saja dipasang. Tidak perlu pip install atau mengunduh ulang model. Jika muncul Kode lokal berbeda dari dasar paket, hentikan: simpan modifikasi Anda dan bandingkan file yang disebutkan. Jangan paksa menimpa kode tersebut.

## Gunakan sesi lama

Tidak perlu mengulang analisis 30 menit. Buka sesi tersimpan dan simpan dahulu koreksi yang belum disimpan.

- Jika istilah seperti XAUUSD masih salah, pilih Perbarui koreksi pada bagian Transkrip. Ini menjalankan kamus konteks, bukan Whisper atau model baru. Hasilnya tetap perlu didengarkan jika ejaan atau angka meragukan.
- Pilih clip, lalu Periksa AI. Versi ini meminta jawaban baru dan menunjukkan alasan jika jawaban tidak memenuhi syarat. Sesi lama yang berubah teksnya harus diperiksa kembali sebelum alur otomatis.
- Pada tab Visual, pilih B-roll Koleksi lokal atau Otomatis. Siapkan ilustrasi. Mode Otomatis memerlukan API key penyedia yang didukung atau koleksi lokal. Versi ini tidak menambahkan layanan berbayar.
- Periksa jumlah sisipan dan alasannya. Nol sisipan dapat benar bila materi/papan tulis terlihat, keputusan AI yang valid mempertahankan pembicara, aset tidak relevan, atau layanan belum tersedia.
- Untuk mengecek sisipan di tengah clip, geser sumber mendekati waktu sisipan, kemudian Preview. Preview hanya 12 detik, bukan ringkasan seluruh clip.
- Render satu clip dahulu. Setelah gambar, waktu subtitle, dan audio sesuai, render pilihan lain dan buat ulang Paket CapCut + DaVinci.

Posisi teks menentukan area blok, misalnya kiri atau kanan. Rata teks mengatur susunan kata di dalam blok. Mode Otomatis memakai area kosong atau menyediakan band terpisah jika materi terlalu padat; pilihan posisi manual tetap berlaku. Font utama dan font aksen tetap mengikuti pilihan Anda. Jangan mengaktifkan judul 3 detik jika tidak menginginkan teks judul tambahan.

## Cadangan dan pemulihan

Sebelum mengubah kode, installer menyimpan file lama dalam steezy_backups. Untuk kembali ke versi sebelumnya, jalankan dari folder paket:

PASANG_UPGRADE.cmd --target "C:\AI\clipper" --rollback

Rollback menolak file yang diedit setelah pemasangan agar perubahan baru tidak hilang. Cadangan transkrip dari tombol Perbarui koreksi tersimpan terpisah di work/<ID sesi>/session-history. Rollback kode tidak membatalkan koreksi transkrip atau menghapus hasil render.

File pribadi di work, clips, uploads, .env, .env.pro, .venv, brand.json, style-presets.json dan pengaturan stok tidak termasuk payload pemasangan. Jangan hapus folder lama untuk memasang patch ini.

## Ekspor dan batas pengujian

MP4 membakar tipografi melalui ASS/libass. Paket editor memisahkan video, audio, B-roll dan teks sesuai kemampuan eksportir. Resolve memakai XML/Fusion, sedangkan CapCut memakai draft dan layer teks; file ASS disertakan sebagai master. Efek blur/fade, font, zoom dan framing tidak selalu dapat diedit atau direproduksi persis sebagai efek native. Kompatibilitas CapCut 9.5 dan DaVinci Resolve Free 21.0.4 harus diperiksa pada komputer Anda.

Uji render dilakukan memakai CPU pada lingkungan pengujian, bukan RTX 3050 Anda. Tidak ada benchmark NVENC, Qwen atau Whisper laptop dari pengujian ini. Perbaikan validasi tidak menjamin AI selalu memilih cerita terbaik atau lengkap. Baca TEST_REPORT_STUDIO_3_3.md untuk hasil uji dan lingkupnya.
