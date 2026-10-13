# Clipper Studio 4.0.11 M1 — editor, pencarian, dan undo/redo

Paket ini meneruskan kode **4.0.11 M0** pada GitHub `akbarttnjg/clipper_pro`, commit
`b8c4ce275021a7b09db2710939a4c063b754f35b`. Sebanyak 360 berkas dasar telah
dicocokkan terhadap hash GitHub sebelum perubahan. `.env.pro` dan video uji
`test_nvenc.mp4` tidak diambil dan tidak disertakan.

**Batas acuan:** lingkup M1 dan audit sembilan panel dapat dibaca dari chat berbagi.
PDF 120 halaman yang disebutkan dalam chat tidak tersedia melalui tautan atau
berkas akun ini. Implementasi ini mengikuti lingkup yang dapat diverifikasi;
belum menyatakan seluruh butir dan penomoran enam paket M1 dalam PDF telah
terpenuhi. Pencocokan lengkap memerlukan PDF tersebut. Tidak ada ID persyaratan
baru yang dikarang untuk menggantikan dokumen itu.

## Apa yang berubah

| Bagian | Perubahan dan fungsi |
|---|---|
| Navigasi editor | Tombol menuju sembilan panel; membuka panel dan membawa kolomnya ke layar. |
| Draf dan revisi | Status draf terlihat; preview, render, batch, dan tahap analisis menolak berjalan ketika pengaturan terkait belum disimpan. Draf dapat ditinjau, disalin sebagai JSON, atau dibuang satu per satu. |
| Penyimpanan pengaturan | Tata teks, suara, dan gaya Tahap 5 mengirim hanya nilai yang berubah; satu perubahan warna tidak menandai seluruh pilihan sebagai manual. Nilai efektif dan asal beberapa pengaturan utama dapat ditinjau. Override yang dipilih dapat dipulihkan dari resep/proyek. |
| Pencarian teks koreksi (X06) | Mencari teks tampil setelah koreksi, ucapan asli, atau keduanya. Frasa tergabung muncul sekali, tetap membawa asal kata dan timing. Indeks SQLite turunan digunakan ulang; ucapan asli tidak ditulis ulang. |
| Riwayat | Undo memeriksa konflik per bagian. Redo tersedia untuk undo yang tercatat. Perubahan lain tetap tersedia dan penghitung revisi tetap bertambah. Hasil proses bukan perubahan edit yang dapat di-undo dari panel ini. |
| Antrean dan respons UI | Status dan tombol batal proses aktif tetap tersedia di bagian bawah layar. Respons kata/proyek lama diabaikan saat pengguna berpindah target. |

Kelompok di atas adalah ringkasan implementasi, bukan pengganti penomoran paket
pada PDF. Ini membenahi kejelasan dan keandalan editor; tidak mengklaim hasil
tipografi otomatis sudah setara dengan hasil editor profesional pada semua video.

## Sembilan panel

| Panel | Perilaku M1 |
|---|---|
| Kata & ejaan | Pencarian memakai teks terkoreksi; pilihan pencarian asli/tampil jelas; draf teks mempertahankan revisi halaman. Koreksi tetap memakai persetujuan perubahan fakta yang sudah ada. |
| Potongan & ritme | Draf batas dan susunan potongan ikut terdeteksi sebelum render. Pada panel Transkrip & cerita, batas manual dan pengisian usulan AI ikut disimpan sebagai draf. |
| Gaya keseluruhan | Resep yang belum diterapkan terdeteksi sebagai draf. Penerapan ke beberapa klip memakai pilihan klip yang disertakan; kedua rasio mengikuti pilihan tombol. |
| Tata teks & komposisi | Hanya kolom berubah yang dikirim. Kebijakan template otomatis/manual ditampilkan. Demo mengikuti keluarga gaya yang tersedia; demo disembunyikan jika video contoh khusus tidak tersedia. Demo bukan hasil dari sumber pengguna. |
| Gaya Tahap 5 & keterbacaan | Penyimpanan parsial. Penggantian preset menjelaskan pengaruhnya pada font, backdrop, dan gerak. Mengembalikan pilihan ke nilai tersimpan membersihkan draf. |
| Brand kit & alternatif | Kit menyimpan kebijakan template otomatis/manual. Kit tetap memakai nilai tersimpan; alternatif tetap mengganti seed seperti versi sebelumnya. |
| Kamera, pembicara & area aman | Draf area, kebijakan visual, pilihan pembicara, dan OCR terdeteksi, dipulihkan, serta dijaga dengan revisi. Analisis visual memerlukan draf terselesaikan. |
| Suara & musik | Sakelar normalisasi tersedia; LUFS/true peak bekerja sesuai normalisasi. Hanya perubahan suara disimpan; batas cache tetap pengaturan proyek. |
| Ilustrasi & bukti analisis | Draf alias, koreksi token, tag/kredit aset, lokasi aset, dan waktu pemakaian terdeteksi. Konflik tidak menghapus draf; muat revisi terbaru merupakan tindakan rebase yang disengaja. |

Penilaian manusia dan pilihan perbandingan pada panel Evaluasi dicatat sebagai
draf terpisah. Pilihan itu dapat langsung menjadi input proses evaluasi dan
tidak menghalangi render. Koreksi kata berlaku pada klip atau ucapan bersama;
pengaturan visual/gaya tetap per rasio.

## Memasang

1. Ekstrak ZIP ke folder baru, di luar folder mesin. Simpan folder paket untuk rollback.
2. Hentikan antrean aktif. Tutup server Clipper dengan **Ctrl+C**.
3. Jalankan **CEK_SEBELUM_UPGRADE.cmd**, lalu isi folder mesin yang berisi `app.py`, `clipper`, dan `.venv`.
4. Jika pemeriksaan lulus, jalankan **PASANG_M1_4_0_11.cmd** dengan folder mesin yang sama.
5. Jalankan **JALANKAN_PRO.cmd** dari folder mesin, lalu tekan **Ctrl+F5** di browser.
6. Pastikan tulisan versi menjadi **4.0.11 M1**.

Contoh dari terminal Windows, sesuaikan lokasi mesin:

```bat
CEK_SEBELUM_UPGRADE.cmd --target "C:\AI\clipper"
PASANG_M1_4_0_11.cmd --target "C:\AI\clipper"
```

Paket membutuhkan dasar M0 yang cocok dengan hash kode GitHub, atau kode paket
M1 yang sama bila sudah dipasang. Kode lokal yang berbeda ditolak sebelum
penyalinan. Jangan melewati penolakan dengan menyalin payload secara manual;
simpan pesan perbedaannya untuk dibandingkan.

Tidak perlu model baru untuk perubahan ini. Pemasang memeriksa `.venv` yang
sudah digunakan mesin dan mencadangkan kode serta SQLite. Video, `.env`, model,
font pribadi, dan data proyek tidak ditimpa. Pemasangan bukan pengganti fondasi
M0; paket ini tidak dipasang langsung di atas 4.0.10.

## Pemeriksaan kecil sesudah memasang

Gunakan satu klip pendek dari proyek yang sudah memiliki transkrip. Tidak perlu
mengunggah sumber video yang besar untuk pemeriksaan awal ini.

1. Pada Kata & ejaan, ubah satu ejaan menjadi teks yang mudah dicari, lalu simpan.
   Cari ejaan baru dalam **Teks tampil terbaru**. Cari ejaan lama dalam **Ucapan asli**.
   Screenshot kedua hasil untuk memastikan asal dan tampil berbeda dengan benar.
2. Ubah satu warna tanpa menyimpan. Pastikan status draf muncul dan preview/render
   terhalang. Pindah rasio dan kembali; periksa draf masih tersedia. Simpan warna,
   lalu lihat Pengaturan efektif: pengaturan lain tidak menjadi manual karena perubahan itu.
3. Gambar area aman tanpa menyimpan. Buka Draf tersimpan untuk meninjaunya.
   Simpan atau buang area tersebut; pastikan preview kembali dapat dijalankan.
4. Di Riwayat, undo satu perubahan warna, lalu redo operasi undo tersebut.
   Screenshot nilai dan revisi. Jika bagian yang sama sudah diedit lagi, konflik
   harus ditampilkan dan edit baru dipertahankan.
5. Buat preview cepat untuk 9:16 dan 16:9. Ambil screenshot sembilan panel,
   status revisi/draf, dan kirim dua preview pendek jika ingin penilaian hasil visual.

Untuk mencoba konflik dua tab, simpan perubahan warna di tab kedua saat tab
pertama memiliki draf. Penyimpanan tab pertama harus ditolak dengan draf tetap
tersedia. **Muat revisi terbaru** mempertahankan nilai draf dan mengizinkan
pengguna meninjaunya sebelum menerapkan pada revisi terbaru; ini bukan merge otomatis.

## Hasil verifikasi dan batasnya

Hasil eksekusi paket ini: **26 tes Python lulus**, **9 suite perilaku UI lulus**
(termasuk 12 kelompok pemeriksaan controller M1), serta pemeriksaan sintaks
**182 berkas Python** dan **10 berkas JavaScript** lulus.

Bukti eksekusi ada di `verification/` dalam ZIP. Pengujian menggunakan SQLite
nyata, service Python, dan fungsi/modul JavaScript yang dikirim dengan adapter
DOM. Pemeriksaan pemasang menggunakan salinan kode M0 yang dibekukan, database
nyata, backup, simulasi kegagalan salin, idempotensi, dan rollback. Pada uji
pemasang, pemeriksaan dependensi `.venv` di-stub karena dependensi server lengkap
tidak tersedia di lingkungan pengujian ini; langkah penyalinan dan database tetap nyata.

Suite pytest M0 lengkap tidak dijalankan ulang: `pytest` dan dependensi server
seperti FastAPI belum tersedia, dan pemasangannya dari registry tidak berhasil.
Angka 824 tes dari laporan M0 adalah hasil sesi sebelumnya, bukan hasil pengujian M1.

Belum diuji: server HTTP FastAPI penuh, browser Windows asli, GPU RTX 3050,
inference model lokal, sumber video asli, dan impor native editor. CapCut yang
sudah diselesaikan dipertahankan; pengenalan teks Resolve ditunda sesuai arahan.
Tidak ada paket model, perubahan algoritme segmentasi/SigLIP2/TalkNet, atau
perbaikan native editor yang diklaim sebagai bagian pekerjaan ini.

Indeks teks adalah cache turunan dengan maksimal empat versi per scope; ia
dibangun saat pertama dibutuhkan. Pencarian mencocokkan substring dalam satu
kata/frasa efektif, bukan pencarian kalimat lintas baris atau makna semantik.
Draf browser masih memakai penyimpanan per proyek dari arsitektur sebelumnya;
dua tab yang menyunting draf lokal sama bukan sistem kolaborasi draf penuh.
Penulisan proyek di server tetap dilindungi revisi. Menutup tab dianjurkan setelah
menyimpan atau menyalin draf penting.

## Rollback

Tutup server, lalu jalankan **PULIHKAN_M1_4_0_11.cmd**. Rollback memulihkan kode,
memeriksa integritas cadangan, dan menolak menimpa kode yang berubah lagi setelah
upgrade. Database tidak diputar mundur agar koreksi setelah upgrade tetap ada.
Tabel tambahan M1 bersifat tambahan dan dapat diabaikan kode M0.

```bat
PULIHKAN_M1_4_0_11.cmd --target "C:\AI\clipper"
```

Untuk memilih cadangan tertentu, tambahkan `--backup` dengan lokasi folder
`steezy_backups/complete-...` yang ditampilkan pemasang.

## Pemeriksaan ulang kode

Sesudah memasang, pengujian ringan dapat dijalankan dari folder mesin:

```text
python -m unittest clipper.tests.test_m1 -v
python -m unittest clipper.tests.test_m1_installer -v
node clipper/tests/m1_ui.cjs
node clipper/tests/m1_analysis_ui.cjs
```

Node hanya diperlukan untuk uji JavaScript pengembang; bukan dependensi baru
yang perlu dipasang untuk menjalankan perubahan UI ini di browser.
