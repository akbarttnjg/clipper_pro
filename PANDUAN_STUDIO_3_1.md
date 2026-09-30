# Clipper Studio Local 3.1 — Editorial Core

Upgrade dari Studio 2.4 pada commit `4886fd044fa7a8912ac77c3e9cba60c2338e8849`.
Disusun dari percakapan PDF yang berakhir dengan keputusan: otomatis, bisa
dilanjutkan di CapCut/DaVinci, B-roll boleh ditolak, gaya Shorts dinamis, Qwen lokal.

## Pasang pada Windows

1. Tutup server Clipper dengan **Ctrl+C**.
2. Ekstrak seluruh `Clipper_Studio_Local_3_1.zip` ke folder baru di luar folder aplikasi.
3. Jalankan **PASANG_UPGRADE.cmd**. Pilih folder instalasi yang berisi `app.py` dan
   folder `clipper`, misalnya `C:\AI\clipper`. Lokasi lain dapat diberikan dengan
   `PASANG_UPGRADE.cmd --target "D:\AI\clipper"`.
4. Dari folder aplikasi, jalankan **CEK_PRO.cmd**, lalu **JALANKAN_PRO.cmd**.
5. Buka `http://localhost:8765`, tekan **Ctrl+F5**, pastikan label **LOKAL · 3.1**.

Installer memeriksa checksum seluruh payload sebelum menyalin dan membuat backup.
Video, hasil lama, transkrip, cache, API key, `.env`, `.env.pro`, preset pribadi, dan
`.venv` tidak dimasukkan ke payload. Tidak ada model atau dependensi wajib baru.
Pemasangan ini untuk aplikasi Studio yang sudah bekerja, bukan instalasi dari nol.
Untuk membatalkan upgrade, tutup server lalu jalankan **PULIHKAN_PRO.cmd** dari folder
aplikasi. Rollback menolak menimpa kode yang telah Anda ubah lagi setelah upgrade.

## Sesi baru: proses otomatis

- Pilih **Video baru → Otomatis sampai MP4 + paket editor**.
- Pilih rasio, jenis sumber, penonton, jumlah maksimum clip, dan gaya awal.
  **Shorts dinamis** memakai Montserrat/Bebas Neue dan penekanan pop; gaya editorial
  tetap tersedia. Rasio 16:9 maupun 9:16 tetap didukung.
- B-roll menggunakan koleksi/API yang sudah Anda konfigurasi. Key diisi sendiri di
  dialog **B-roll & API**. Model boleh memilih untuk tetap menampilkan pembicara.
- Tekan **Mulai proses**. Whisper dan Qwen bekerja bergiliran. Pemeriksaan cerita
  menggunakan panggilan Qwen pemeriksaan batas yang sama, dengan jawaban lebih rinci.
- Kandidat yang lolos pemeriksaan AI dirender dan, bila dipilih, dibuatkan paket editor.
  Kandidat yang belum lengkap tetap ditampilkan; aplikasi tidak memaksakan jumlah clip.

Pilih **Tinjau kandidat sebelum render** jika ingin memeriksa semuanya dahulu.
Mode **Video utuh + tipografi** mengikuti pilihan eksplisit Anda untuk memproses
seluruh sumber dan tidak menjalankan gerbang kelengkapan cerita.

## Sesi lama: gunakan transkrip yang sudah ada

1. Buka sesi tersimpan. Transkripsi tidak perlu diulang.
2. Pilih kandidat, lalu **Periksa AI** atau **Periksa cerita semua** untuk memperoleh
   keputusan 3.1. Ini menjalankan penilaian Qwen pada konteks kandidat, bukan Whisper.
3. Di tab **Cerita**, lihat bukti pembuka, isi, jawaban/penutup, pilihan hook, dan alasan
   B-roll. Tombol waktu memutar bagian sumber yang menjadi bukti.
4. Pilih kandidat lalu **Selesaikan otomatis**, atau tetap gunakan Preview/Render pilihan.
   Selesaikan otomatis memeriksa ulang kandidat yang keputusannya belum valid.

**Render pilihan** tetap mengizinkan keputusan manual, termasuk kandidat yang
ditandai meragukan. **Selesaikan otomatis** hanya memproses kandidat lolos pemeriksaan.
Mengubah teks, judul, batas atau sasaran penonton membuat keputusan lama kedaluwarsa.
Mengubah font/warna/posisi tidak mewajibkan analisis cerita ulang.
Output baru memakai akhiran `-v31`; hasil 2.4 tetap tersedia sebagai hasil sebelumnya.

## Yang berubah pada keputusan edit

| Bagian | Perilaku 3.1 |
|---|---|
| Cerita | Qwen harus menyertakan kutipan sumber untuk pembuka, isi dan payoff, beserta hubungan di antaranya. Kutipan yang tidak ditemukan, urutan bukti keliru, akhir menggantung, risiko yang dilaporkan, atau angka/waktu ASR mencurigakan menahan render otomatis. |
| Hook | Satu kalimat utuh 1–6 detik dapat dipindah ke awal. Rentang itu dihapus dari posisi lama, sehingga tidak diputar dua kali. Hook fragmen atau yang mengambil penutup ditolak. Banner judul tetap dihapus. |
| Caption | Frasa penekanan Qwen dicocokkan ke ucapan dan waktu sumber, misalnya “jangan jualan outcome”. Pengelompokan berusaha mempertahankan frasa dan negasinya; ukuran tetap diukur agar muat. Aturan lama menjadi fallback. |
| B-roll | AI dapat mempertahankan pembicara. Bila perlu ilustrasi, kandidat dibandingkan dengan makna kalimat dan metadata aset; pilihan boleh kosong. Aset tidak lagi langsung dipakai hanya karena menjadi hasil pertama. |
| Otomatis | Seleksi → pemeriksaan cerita → render kandidat lolos → paket editor. Kegagalan satu render tidak menghapus hasil lainnya; kegagalan ekspor tidak menghapus MP4. |

## Berkas hasil

MP4 siap digunakan tersedia di UI/folder `clips`. ASS dan SRT pendamping tetap ada.
Paket editor tetap memisahkan video dasar, B-roll, teks dan audio; keputusan sumber
disimpan di `edit-plan.json`. Laporan QC juga menyimpan penilaian cerita.

CapCut memakai draft eksperimental melalui pycapcut; DaVinci memakai XML dan Lua/Fusion.
**ASS bukan layer animasi native yang otomatis identik di kedua editor.** Blur/fade
teks CapCut belum sepenuhnya dipetakan. Framing/zoom tetap menyatu dalam video dasar.
Pembuatan paket berhasil diuji secara terstruktur, tetapi impor interaktif pada
CapCut 9.5 / Resolve Free 21 belum diverifikasi di sesi pengembangan ini.

## Batas upgrade dan kelanjutan

Ini implementasi tahap Editorial Core, belum keseluruhan visi AI editor dalam PDF.
Penilaian model tetap bisa keliru: kecocokan kutipan membuktikan asal teks, bukan
kebenaran semantik atau jaminan retensi. AI tidak memperbaiki angka dengan menebak.

B-roll dinilai dari **metadata**, belum dari frame video. CLIP/vision, pembacaan
papan tulis, identifikasi pembicara aktif, deteksi reaksi, dan pengukuran retensi dari
data publikasi belum ditambahkan. Framing papan/podcast memakai engine 2.4 yang ada.
Tidak ada klaim kualitas setara akun referensi atau jaminan FYP.

Pengujian memakai CPU/Linux, transkrip simulasi, dan video sintetis. Qwen/Whisper
nyata di laptop ASUS TUF i5-12500H/RTX 3050 4 GB belum dijalankan; waktu 30 menit
untuk sumber 1–2 jam belum dapat dijanjikan. Pemeriksaan stok menambah panggilan
Qwen lokal, dengan cache untuk menghindari pengulangan.

Langkah evaluasi berikutnya: proses satu sumber nyata, periksa satu kandidat lolos
dan satu kandidat ditahan, bandingkan pembuka/penutup, relevansi B-roll dan caption,
lalu coba impor satu paket editor. Gunakan hasil tersebut sebelum menambah vision
atau mengganti model. Untuk pelacakan lanjutan, kirim laporan seleksi,
`edit-plan.json`, dan satu MP4; jangan kirim API key atau file konfigurasi privat.
