# Clipper Studio Local 2.3.1

Pembaruan ini memperbaiki posisi subtitle yang ditimpa penempatan otomatis, menambahkan perataan baris, dan menghapus banner judul pembuka. Font dan preset 2.3 ikut disertakan. Tidak ada model/dependensi baru atau API berbayar.

## Pemasangan Windows

1. Tutup server Clipper dengan **Ctrl+C**.
2. Ekstrak seluruh `Clipper_Studio_Local_2_3_1.zip` ke folder baru.
3. Jalankan **PASANG_UPGRADE.cmd**. Target bawaan: `C:\AI\clipper`. Untuk lokasi lain, jalankan `PASANG_UPGRADE.cmd --target "D:\folder\clipper"` dari terminal di folder paket.
4. Dari folder instalasi, jalankan **CEK_PRO.cmd**, lalu **JALANKAN_PRO.cmd**.
5. Buka `http://localhost:8765` dan tekan **Ctrl+F5**. Pastikan label **LOKAL · 2.3.1** muncul.
6. Buka sesi tersimpan. Kandidat dan transkrip lama dapat dipakai tanpa analisis ulang.

Paket ditujukan untuk instalasi Clipper Studio 2.x yang sudah berjalan. Tidak perlu memasang ZIP 2.3 lagi sebelumnya. Installer memeriksa hash dan membuat cadangan di `steezy_backups`. Folder `work`, `uploads`, `clips`, `.venv`, konfigurasi `.env`/`.env.pro`, brand dan preset pribadi tidak ditimpa. Untuk pemulihan, tutup server lalu jalankan **PULIHKAN_PRO.cmd**. Pemulihan melindungi perubahan program yang dibuat setelah pemasangan.

## Posisi dan perataan

Pilih clip aktif, buka **Komposisi**, lalu atur dua kontrol berikut:

| Pengaturan | Fungsi |
|---|---|
| Posisi blok teks | Area seluruh frasa: otomatis, bawah, kiri, kanan. Area kiri/kanan digunakan pada 16:9. |
| Perataan baris | Tepi kiri, titik tengah, atau tepi kanan setiap baris di dalam area. Berlaku pada 16:9 dan 9:16. |

| Hasil | Posisi blok | Perataan baris |
|---|---|---|
| Teks di kiri, rapi rata kiri | Kiri · 16:9 · terkunci | Rata kiri |
| Teks di kanan, rapi rata kanan | Kanan · 16:9 · terkunci | Rata kanan |
| Subtitle bawah video vertikal, rata kiri | Bawah · terkunci | Rata kiri |
| Subtitle bawah video vertikal, rata kanan | Bawah · terkunci | Rata kanan |
| Posisi mengikuti adegan | Otomatis per adegan | Ikuti posisi blok atau pilihan sendiri |

**Ikuti posisi blok** memakai rata kiri untuk area kiri, rata kanan untuk area kanan, dan rata tengah untuk bawah. Sesi lama mendapat nilai awal ini.

Posisi manual dikunci; kontrol ruang otomatis dinonaktifkan dan tidak menggeser teks. Preset bawaan/pribadi dan salin gaya tidak mengganti posisi/perataan clip. Pilih area manual yang tidak menutupi wajah atau diagram. Animasi masuk masih boleh bergerak; perataan berlaku pada posisi akhir ketika teks sudah masuk.

## Judul pembuka dan hasil baru

Banner judul di awal video dihapus, termasuk pada sesi lama yang menyimpan `title_card=true`. **Nama clip** tetap dipakai untuk daftar dan nama berkas. Subtitle ucapan serta opsi kutipan pembuka dari sumber tetap terpisah.

Sesudah mengatur posisi, klik **Simpan koreksi → Preview dari sini → Render pilihan**. Output baru memakai akhiran `-v231`. MP4 lama yang teksnya sudah menyatu tidak berubah otomatis: render ulang dari sesi/sumber asli diperlukan, tanpa mengulang analisis topik. Render versi lama tidak memenuhi syarat untuk ekspor proyek baru.

Preview memakai resolusi lebih kecil dan analisis potongan pendek. Posisi manual memakai aturan yang sama; komposisi otomatis preview dan render penuh masih dapat berbeda. Periksa hasil final sebelum publikasi.

## MP4 dan editor

MP4 sudah berisi tipografi. ASS adalah master animasi untuk ASS/libass. Paket editor menyertakan video tanpa teks, suara/musik/efek terpisah, font, ASS/SRT, dan layer teks native berdasarkan rencana posisi yang sama. Satu clip menghasilkan satu timeline.

ASS tidak otomatis menjadi layer animasi native pada CapCut/DaVinci. Impor interaktif CapCut 9.5 dan DaVinci Resolve Free 21.0.4 belum terverifikasi di lingkungan ini; blur/fade atau ukuran native bisa berbeda. Coba satu proyek dahulu. Uji render pembaruan ini memakai CPU Linux; NVENC laptop belum diuji langsung.

Lihat `TEST_REPORT_STUDIO_2_3_1.md` dan `CHANGELOG_STUDIO_2_3_1.md` untuk rincian.
