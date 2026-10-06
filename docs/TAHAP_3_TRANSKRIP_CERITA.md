# Clipper Studio 4.0.3 — Tahap 3: transkrip dan cerita

Upgrade ini menerapkan pekerjaan 21–30 pada laporan upgrade 6 Oktober 2026.
Paket memperbarui kode secara offline. Video, hasil, proyek SQLite, lingkungan
Python, model, pengaturan pribadi dan komponen yang sudah dipasang tetap disimpan.
Paket juga membawa kode perbaikan antrean dan dependensi Silero dari Tahap 2.

## Memasang pada mesin yang sudah ada

1. Ekstrak seluruh ZIP ke folder baru, misalnya `C:\AI\upgrade_tahap3`.
2. Hentikan pekerjaan aktif dan antrean. Tutup server mesin dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`. Pilih **folder mesin lama** yang berisi
   `app.py` dan folder `clipper`, bukan folder paket upgrade.
4. Jika pemeriksaan lulus, jalankan `UPGRADE_TAHAP_3.cmd` dengan folder mesin yang sama.
5. Jalankan `JALANKAN_PRO.cmd` dari folder mesin lama. Buka
   `http://localhost:8765`, lalu tekan Ctrl+F5. Header menunjukkan **4.0.3**.
6. Buka proyek lama, lalu tombol **Transkrip & cerita** pada Sumber/Edit,
   atau **Transkrip, bab & kandidat ditolak** pada Pilih cerita.

Installer menerima dasar AB, fondasi 4.0.1, Tahap 2 4.0.2, perbaikan antrean
4.0.2a, dan perbaikan Silero. Berkas dengan kode kustom yang tidak dikenal
ditolak untuk mencegah penimpaan. Installer tidak memasang ulang dependensi
atau mengunduh model. Catatan dan checksum paket ada dalam `manifest.json`.
Jangan menyalin folder `payload` secara manual bila pemeriksaan melaporkan konflik.

## Pekerjaan dan hasil yang tersedia

| Nomor | Fungsi | Perilaku upgrade |
|---|---|---|
| 21 | Kamus proyek dan pengucapan | Ejaan, nama dan akronim dapat ditulis sebagai `benar=alias1\|alias2`. Alias ambigu antarkamus/memori ditolak. Kamus tetap mengikuti konteks dan menjaga edit manual. |
| 22 | Uji ulang ASR terarah | Antrean baru memeriksa kata berkeyakinan rendah atau ucapan yang dipilih. Batas 1–24 rentang, maksimal 20 detik per rentang. Memakai model lokal, termasuk bobot ASR small dari lingkungan WhisperX yang sudah terpasang bila dipilih. |
| 23 | Perlindungan fakta | Koreksi otomatis tidak mengubah angka, satuan, bilangan terucap, negasi atau syarat. Koreksi manual yang mengubahnya memerlukan centang persetujuan khusus dengan bukti sebelum/sesudah. Persetujuan terikat teks, asal kata dan revisi, lalu disimpan dalam riwayat. |
| 24 | Teks tampil terpisah | Transkrip ASR asli tetap utuh. Teks koreksi berada pada lapisan terpisah; pecahan desimal seperti `0,01` tetap dilindungi oleh pembersih subtitle. |
| 25 | Timing dan asal kata | Timing manual/WhisperX disimpan terpisah, mempunyai asal kata dan riwayat. Kata yang diselaraskan memakai waktunya sendiri dalam caption/render. Frasa yang belum diselaraskan ditandai sebagai rentang frasa/asal. Tidak ada pembagian timing rata otomatis. |
| 26 | Seluruh sumber dan bab | Pemindaian memakai jendela bertumpang tindih dari awal sampai akhir. Laporan mencatat segmen yang selesai/belum diperiksa, rentang yang tertinggal dan bab berdasarkan transkrip/jeda. Label bab berasal dari teks sumber; ini bukan bab hasil verifikasi manusia. |
| 27 | Keragaman cerita | Pencarian pertama maupun tambahan meminta jawaban, contoh, kesalahan, perbandingan dan demonstrasi bila bukti sumber mendukung. Jenis cerita dan klaim berbeda dipertahankan saat deduplikasi. |
| 28 | Pembuka, penutup dan durasi | Konteks sebelum/sesudah klip dapat didengar. AI lokal memeriksa batas dengan segmen sumber. Batas yang diedit manual disimpan; pemeriksaan AI memberi usulan. Preset otomatis menjadi target 20–120 detik, dengan kelonggaran penutup sesuai pengaturan mesin. |
| 29 | Duplikat makna | Kutipan klaim, jenis cerita, angka, satuan, syarat dan bukti penutup dibandingkan. Klaim berbeda tidak dibuang hanya karena waktunya berimpitan. Perbandingan semantik memakai batch terbatas dengan wakil dari batch sebelumnya; ini bukan bukti semua duplikat telah ditemukan. |
| 30 | Kandidat ditolak dan transkrip penuh | Transkrip dibaca per halaman, dapat dicari dan dikoreksi tanpa mengirim semua kata ke DOM. Kandidat ditolak mempunyai identitas tetap dalam laporan aktif, alasan, audio sumber dan tombol pemulihan dengan batas pilihan pengguna. Klip dipulihkan sebagai klip manual dan dapat di-undo. |

## Pemakaian pertama yang disarankan

Mulai dari proyek yang transkripnya sudah tersedia. Buka panel Tahap 3, dengarkan
satu kata yang meragukan, simpan koreksi kecil, lalu periksa Riwayat. Coba
koreksi angka dengan sengaja untuk melihat tinjauan fakta, kemudian batalkan
bila angka sumber memang sudah benar. Pembatalan mempertahankan draf.

Untuk ASR ulang, pilih model yang **sudah tersedia lokal** dari dropdown. Model
small yang dipasang bersama WhisperX bisa dipakai untuk uji terarah tanpa
memasang ulang paket. Memilih model pengaturan proyek membutuhkan bobot model
tersebut dalam cache lokal. Bila belum ada, proses menjelaskan kebutuhan itu;
tidak mengunduh secara diam-diam. Hasil ASR alternatif beserta perbedaan fakta
tersimpan dalam laporan untuk didengar dan ditinjau. Tidak semua hasil ulang
diterapkan; ambang kemiripan/keyakinan serta edit manual membatasi penerimaan.

Tekan **Jelajah seluruh sumber & cari cerita berbeda** untuk memperoleh laporan
cakupan Tahap 3. Proyek lama tetap memiliki klip dan laporannya. Laporan lama
tidak dihitung sebagai pencarian baru. Setelah mengubah transkrip, laporan
ditandai usang sampai penjelajahan dijalankan lagi. Jumlah klip tidak dipaksa.
Pada Sumber, simpan preset otomatis bila ingin menerapkan target baru 20–120
detik pada proyek lama; pengaturan proyek lama tidak diubah tanpa penyimpanan.

## Alignment: pilihan manual dan model lokal

Timing manual dapat dipakai segera: simpan teks, buka **Atur timing kata**,
dengarkan audio, isi awal/akhir setiap kata lalu simpan. Aplikasi memeriksa
urutan, rentang dan kesamaan teks. Timing manual adalah keputusan pengguna,
bukan klaim hasil pengukuran AI. Timing yang tumpang tindih dengan kata tetangga
ditolak. Koreksi teks berikutnya menonaktifkan timing yang tidak lagi cocok.

Forced alignment WhisperX adalah pilihan tambahan pada **CPU** untuk profil
RTX 3050 4 GB. Memasang WhisperX dan lolos sampel transkripsi belum membuktikan
bahwa model alignment sudah tersedia. Isi folder model Wav2Vec2 CTC lokal yang
sesuai bahasa sumber, dengan `config.json`, bobot `pytorch_model*.bin` atau
`.safetensors`, `vocab.json`, dan `preprocessor_config.json`. Simpan lokasinya
lalu jalankan alignment. Paket ini tidak membawa atau mengunduh bobot itu.

Rujukan resmi WhisperX menggunakan `cahya/wav2vec2-large-xlsr-indonesian` sebagai
model bawaan bahasa Indonesia. Ini informasi kompatibilitas, bukan bukti model
tersebut sudah ada di laptop. Lingkungan WhisperX juga memerlukan data pemisah
kalimat NLTK (`punkt_tab` pada versi baru). Bila data itu belum ada, laporan
menjelaskan kegagalannya; pemasangan data otomatis diblokir. Timing manual tetap
tersedia, sehingga alignment tambahan boleh ditunda.

Hasil alignment parsial, tanpa waktu atau tanpa skor per kata tidak diterapkan.
Interpolasi waktu dinonaktifkan. Versi WhisperX lama yang menerima folder model
lokal juga didukung; variabel offline diterapkan pada proses anak.

## Kesinambungan dan pemulihan

Koreksi klip tetap lebih khusus daripada koreksi ucapan bersama. ASR ulang
melindungi asal kata yang sudah mempunyai edit manual pada klip mana pun,
dan memindahkan tautan patch ke take baru tanpa mengubah ASR asli. Timing
yang masih cocok ikut dipindahkan. Backup/pemulihan proyek menyertakan timing
dan menautkan ulang identitas take. Perubahan baru memerlukan revisi yang cocok;
hasil proses yang dibatalkan atau masukan yang berubah tidak diterapkan.

Riwayat memungkinkan undo teks, timing, batas dan pemulihan kandidat. Draf
dipertahankan saat konflik; draf dari transkrip sebelumnya ditampilkan terpisah
untuk disalin setelah meninjau sumber. Audio konteks berhenti pada akhir rentang
yang dipilih. Klik **Tutup** untuk kembali melihat antrean dan tombol pembatalan.

Untuk memulihkan **kode**, tutup mesin dan jalankan `PULIHKAN_UPGRADE_TAHAP_3.cmd`.
Cadangan berada dalam `steezy_backups` di folder mesin. Pemulihan kode tidak
menghapus video, model, lingkungan atau data proyek baru. Untuk mengembalikan
edit proyek gunakan Riwayat atau backup proyek; ini berbeda dari rollback kode.

## Bukti pengujian dan batasnya

Pengujian pengembangan memeriksa API/SQLite, fakta dan persetujuan, lineage,
timing yang sampai ke caption, patch lintas take, pembatalan/revisi usang,
pemulihan kandidat, backup timing, cerita berbeda dengan rentang sama, cakupan
akhir sumber, model lokal/offline dan potongan WAV FFmpeg sungguhan.
Adapter WhisperX diuji memakai keluaran CTC simulasi yang terukur/lengkap dan
parsial. Uji antarmuka menjalankan JavaScript asli dalam adapter DOM.

Jumlah kasus dan log final ada di folder `verification`. Uji tersebut tidak
membuktikan akurasi ASR/CTC pada video Anda, kualitas cerita LLM nyata, render
browser asli, eksekusi CMD Windows atau CUDA/VRAM laptop. Model berat dan native
editor tidak diuji ulang pada server pengembangan. Pengujian sampel WhisperX
CPU dan Silero CPU yang Anda kirim sebelumnya tetap merupakan bukti pengguna
dari Tahap 2, bukan hasil alignment baru Tahap 3.

Perbaikan teks DaVinci tetap ditunda. Backend CapCut yang sudah bekerja tetap
digunakan. Tahap 4/5 untuk visual dan gaya berikutnya belum dimulai.

Referensi API utama: [WhisperX alignment](https://github.com/m-bain/whisperX/blob/main/whisperx/alignment.py)
dan [interpolasi waktu WhisperX](https://github.com/m-bain/whisperX/blob/main/whisperx/utils.py).
