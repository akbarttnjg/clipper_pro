# Clipper Studio 4.0.4 Tahap 4 kamera dan area aman

Tahap ini menghubungkan pekerjaan 31–40 pada backlog dengan komposisi dan
render yang sudah ada. Mesin menganalisis frame sumber, menyimpan bukti wajah
dan tulisan, lalu membuat komposisi tersendiri untuk 16:9 dan 9:16. Koreksi
kamera disimpan pada proyek, sehingga analisis ulang tidak menggantinya.

Ini pembaruan kamera dan perlindungan materi. Pemilihan cerita dan template
tipografi yang ada tetap digunakan. Model visual tambahan membutuhkan
lingkungan dan bobot lokal yang lulus uji; paket ini tidak mengunduhnya.

## Memasang pada instalasi yang sudah digunakan

1. Ekstrak seluruh ZIP ke folder baru, misalnya `C:\AI\upgrade_tahap4`.
2. Hentikan antrean aktif dan tutup server Clipper dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`. Pilih folder mesin lama yang berisi
   `app.py`, `clipper`, dan `.venv`, biasanya `C:\AI\clipper`.
4. Jika pemeriksaan lulus, jalankan `UPGRADE_TAHAP_4.cmd` pada target yang sama.
5. Jalankan `JALANKAN_PRO.cmd` dari folder mesin lama dan tekan Ctrl+F5
   pada browser. Header menunjukkan **4.0.4**.
6. Buka proyek lama dan pilih satu klip. Di **Edit**, buka
   **Kamera, pembicara & area aman** lalu pilih **Analisis visual klip**.
   Transkripsi dan pencarian klip tidak perlu diulang.

Paket memuat perubahan Tahap 3 yang diperlukan, sehingga dapat diterapkan
pada kode `main` 2b02a58 atau instalasi Tahap 3 yang sesuai pemeriksaan.
Installer memeriksa checksum, membuat cadangan kode, lalu memeriksa impor.
Jika penyalinan atau pemeriksaan setelah pemasangan gagal, kode dipulihkan.
Kode kustom yang tidak dikenal ditolak sebelum penimpaan.

Video, hasil render, SQLite, `.env`, `.env.pro`, model, dan lingkungan komponen
tidak ditimpa. Paket tidak menjalankan pip. PyAV 18 pada resep faster-whisper
hanya berlaku untuk pemasangan komponen berikutnya; lingkungan ASR Anda yang
sudah lulus uji CUDA tetap digunakan.

Untuk rollback kode, tutup server lalu jalankan
`PULIHKAN_UPGRADE_TAHAP_4.cmd`. Berkas yang diedit setelah upgrade akan
ditandai dahulu, agar rollback tidak menimpa edit baru.

## Menggunakan koreksi visual

Pilih rasio sebelum mengedit. Kanvas menampilkan **frame sumber**, bukan
hasil crop. Gambar kotak dan atur waktu berlakunya dalam detik sumber.

| Jenis area | Pengaruh pada komposisi |
|---|---|
| Kunci crop | Menggunakan bagian gambar yang dipilih; isi kotak dipertahankan utuh dengan mode fit. |
| Area pembicara | Menentukan panel pembicara atau bagian gambar yang difokuskan. |
| Area materi | Menentukan papan, slide atau layar yang harus tetap terlihat. |
| Lindungi dari subtitle | Menambahkan area yang dihindari penempatan subtitle otomatis. |

Tekan **Simpan area pada rasio ini**, lalu **Analisis visual klip** atau
**Preview**. Koreksi pada 9:16 tidak diterapkan pada 16:9. Untuk kedua rasio,
ulangi koreksi pada masing-masing varian. Menghapus area memerlukan tombol
**Hapus area**; regenerasi tidak menghapusnya.

Draf kotak tetap tersedia setelah gagal simpan. Bila revisi proyek berubah,
pilih **Muat revisi terbaru untuk draf** untuk menambahkan kotak ke koreksi
terbaru, atau **Buang draf area** untuk membatalkannya. Koreksi yang sudah
disimpan tetap tersedia.

Pada **Tulisan sumber dan koreksi OCR**, Anda dapat memperbaiki teks OCR.
Teks itu menjadi bukti visual dan tidak mengganti transkrip ucapan. ID area
OCR tetap mengikuti wilayah sumber ketika koreksi kamera memecah adegan.

Rata kiri, kanan, tengah, dan otomatis tersedia pada pengaturan subtitle.
Posisi teks yang Anda pilih manual tetap dihormati. Perlindungan ruang teks
otomatis berlaku ketika posisi teks **Otomatis** dan area aman diaktifkan.

## Pekerjaan yang dihubungkan

| Nomor | Kemampuan | Ketentuan |
|---|---|---|
| 31 | Jenis adegan dan alasan komposisi | Wajah, panel materi dan geometri tulisan diperiksa. Chart/grafik dapat dikonfirmasi model visual lokal. Jenis yang belum pasti ditandai. |
| 32 | Lintasan wajah dan keyakinan | ID mengikuti geometri sepanjang sampel dan direset pada cut atau jeda panjang. Pilihan manual terikat pada bukti sumber; setelah rentang/detektor berubah, pilihan harus diperiksa ulang. Tidak mengenali identitas biologis orang. |
| 33 | Pembicara aktif selektif | TalkNet memakai audio dan crop wajah tersinkron pada bagian dengan beberapa wajah. Maksimal 60 detik audio per klip; bagian yang belum pasti mempertahankan tamu. |
| 34 | Tulisan berulang dan koreksi | RapidOCR lokal atau bukti OCR sumber dipakai jika tersedia. Hasil berkeyakinan tinggi mempunyai kotak, waktu, dan status berulang. |
| 35 | Konfirmasi model visual | SmolVLM/Qwen3 VL hanya diminta pada adegan meragukan, maksimal tiga frame per klip. Keputusan menyimpan waktu frame dan asal model. Default nonaktif. |
| 36 | Ruang subtitle sepanjang frasa | Menggabungkan lintasan area terlindungi dan batas zoom pada adegan yang disentuh frasa. Jika ruang kosong tidak cukup, gambar diperkecil untuk menyediakan pita teks. |
| 37 | Komposisi per rasio | Bukti sumber yang sama dicache; crop dan koreksi kedua rasio tetap terpisah. |
| 38 | Stabilitas tata letak | Crop ditahan ketika lintasan yang sama hanya bergeser sedikit. Posisi teks dipilih per adegan/frasa, bukan setiap kata. |
| 39 | Mask SAM selektif | Satu frame atau propagasi rentang maksimal enam detik pada 5 fps. Mask disimpan terpisah dan belum menjadi layer render/editor. Akurasi model belum diverifikasi pada sumber Anda. |
| 40 | Koreksi kamera yang tetap tersimpan | Crop, area pembicara, area materi, wilayah terlindungi dan pilihan lintasan disimpan per varian dengan pemeriksaan revisi. |

Kata sumber yang melintasi dua potongan bersebelahan sekarang ditampilkan satu kali. Ucapan berulang yang memang mempunyai asal kata berbeda tetap dipertahankan.

## Komponen dan batas pemakaian

Tracking dasar menggunakan YuNet yang sudah ada, atau Haar sebagai fallback.
RapidOCR adalah tambahan yang paling langsung berguna untuk sumber dengan
papan/slide. TalkNet berguna untuk podcast beberapa orang. SmolVLM atau
Qwen3 VL berguna ketika geometri belum memastikan jenis adegan.

Status paket terpasang saja tidak dianggap siap. Backend tambahan memerlukan
bobot lokal, interpreter lingkungan komponen, dan catatan uji sampel yang
lulus. Jika tidak siap atau inferensi gagal, komposisi dasar dan koreksi
manual tetap tersedia. Backend visual pada tahap ini menggunakan CPU agar
tidak berebut VRAM 4 GB dengan ASR.

SAM nonaktif sampai Anda menyimpan area prompt. Pilih frame sumber, gambar
area objek, lalu **Simpan area mask**. Untuk propagasi, pilih rentang paling
lama enam detik di dalam satu adegan dan frame prompt di dalam rentang itu.
Jalankan **Analisis visual klip**. Mask PNG dan timeline JSON disimpan pada
cache proyek. Mask 5 fps bukan matte video 30 fps dan belum digunakan untuk
efek teks di belakang orang atau sebagai layer CapCut/DaVinci.

Tidak ada jaminan seluruh proses satu atau dua jam selesai dalam 30 menit.
Model visual berat dapat menambah waktu. Uji pertama sebaiknya memakai satu
klip 30–60 detik dengan VLM dan SAM tetap nonaktif.

## Bukti pengujian

Folder `verification` di paket memuat ringkasan pengujian. Uji kode mencakup
hilangnya wajah, pergantian ID, ketidakpastian pembicara, batas audio terukur,
OCR berulang, koreksi per rasio, konflik revisi, cache, API, dan propagasi mask
dengan predictor tiruan. Predictor tiruan menguji alur data; bukan akurasi SAM.

FFmpeg, SQLite, worker, preview dan render kedua rasio diuji dengan video
sintetis serta struktur paket editor. Dua video render yang Anda unggah
digunakan untuk uji pembacaan frame dan tracking dasar, bukan untuk menilai
ASR atau kecocokan edit pada video mentah. Uji UI menggunakan adaptor DOM;
tampilan browser Windows belum diverifikasi di lingkungan ini.

Masih diperlukan penerimaan pada laptop Anda: TalkNet dengan podcast asli
bersuara sinkron, OCR tulisan sumber, keputusan VLM, kualitas/kecepatan SAM,
dan impor editor dari komposisi baru. Upgrade ini tidak mengklaim semua
model tersebut sudah diuji pada RTX 3050 Anda.
