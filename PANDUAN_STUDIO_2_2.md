# Clipper Studio Local 2.2 — tipografi bergerak

Upgrade untuk instalasi Studio 2.0/2.1 yang sudah berjalan. Semua pemrosesan tetap
lokal. Tidak ada API berbayar, model baru, atau dependensi Python tambahan.

## Pasang

1. Tutup server Clipper dengan **Ctrl+C** pada terminalnya.
2. Ekstrak seluruh ZIP ke folder baru, di luar `C:\AI\clipper`.
3. Jalankan **PASANG_UPGRADE.cmd**. Target default `C:\AI\clipper`.
   Jika lokasi berbeda, jalankan `py -3 steezy_pro_installer.py --target "D:\AI\clipper"`.
4. Di folder aplikasi jalankan **CEK_PRO.cmd**. Pastikan font, galeri tipografi,
   serta filter + subtitle + encode dilaporkan OK.
5. Jalankan **JALANKAN_PRO.cmd**, buka `http://localhost:8765`, tekan **Ctrl+F5**.
   Label versi menjadi **LOKAL · 2.2**.

Installer mencadangkan kode lama ke `steezy_backups`. `.env`, `.env.pro`, brand,
`work`, `clips`, `uploads`, dan modul `intelligence` tidak ditimpa. Instalasi ini
tidak menjalankan pip secara default. Untuk kembali ke kode sebelumnya, tutup
server dan jalankan `PULIHKAN_PRO.cmd`.

## Gunakan hasil analisis yang sudah ada

1. Buka sesi lama di kolom kiri; klik **Pulihkan sesi** jika masih berstatus error.
2. Pilih satu clip, kemudian **Pilih template bergerak** pada panel kanan.
3. Putar contoh gaya dan klik **Gunakan template**. Atur intensitas, warna, ukuran,
   dan kata penting bila perlu.
4. Klik **Preview 12 dtk**. Setelah selesai, lihat komposisi, gerak, dan ucapan.
5. Bila sesuai, centang clip yang diinginkan. Gunakan **Terapkan gaya ke clip terpilih**
   untuk menyalin gaya teks, lalu **Render ... pilihan**.

Mengganti template tidak menjalankan Whisper/Ollama, mengubah batas topik, atau
menghapus koreksi transkrip. Hasil lama disimpan; keluaran baru memakai akhiran
`-v22.mp4`. Kandidat dan transkrip lama tetap dipakai, sehingga tidak perlu analisis
ulang 30 menit hanya untuk mengganti gaya subtitle.

## Lima template

| Pilihan | Tampilan |
| --- | --- |
| Narasi bertingkat | Putih–kuning, susunan frasa bertingkat, variasi blur/geser/pop per frasa. Titik awal yang disarankan untuk podcast. |
| Pop lembut | Gerak skala singkat yang menetap, dengan kata penting besar. |
| Geser terarah | Masuk dari kiri, kanan, atas, dan bawah secara bergantian per frasa. |
| Fokus tajam | Blur menjadi tajam, dengan skala dan hierarki ukuran. |
| Angka & penekanan | Ukuran aksen lebih besar, cocok untuk angka atau pokok pembahasan. |

**Tenang** mengurangi jarak/gerak; **Seimbang** adalah default; **Dinamis** menambah
intensitas. Gerak berhenti setelah masuk agar teks tetap terbaca. Teks pendukung
memakai sans regular; penekanan memakai bold dan variasi italic saat opsi variasi
font aktif. Editorial klasik dan Clean tetap tersedia.

Galeri menampilkan video contoh yang dirender dengan mesin subtitle yang sama,
bukan simulasi CSS. Kata muncul per baris/frasa mengikuti waktu ucapan, kemudian
bertahan hingga frasa selesai. Tata letak tidak bergeser saat kata berikutnya muncul.

Nominal yang terpecah oleh ASR, seperti `Rp`, `2`, `,5`, `juta`, disatukan untuk
tampilan menjadi `Rp2,5 juta`. Nilai angka tidak ditebak/diganti. Kesalahan ucapan,
nama, atau angka di transkrip tetap perlu dikoreksi melalui Edit kata.

## Komposisi yang lebih stabil

Deteksi materi kini lebih tahan terhadap tulisan yang memecah panel putih dan
gradasi gelap di bawah papan. Untuk 9:16, materi terang dengan area pembicara di
samping dapat disusun menjadi materi di atas dan pembicara di bawah, meskipun
wajah sedang menunduk. Bila ada ruang cukup di bawah materi, ruang itu dipakai
untuk tipografi sehingga teks tidak menutupi wajah atau papan.

Framing dikunci per adegan. Untuk slide gelap atau tata letak yang gagal dikenali,
pilih **Materi + pembicara**, lalu **Tandai materi** dan **Tandai pembicara** pada
frame sumber yang dijeda. Kotak manual berlaku sepanjang clip. Gunakan Preview
untuk memeriksa hasil, terutama ketika sumber berpindah ke adegan lain.

Ini deteksi geometri, bukan pembacaan isi slide atau identifikasi pembicara aktif.
Diagram sangat padat tetap mungkin lebih mudah dibaca dalam 16:9. Tidak ada efek
transisi acak; pemotongan dan zoom lama tetap mengikuti rencana edit.

## MP4, ASS, dan proyek editor

Setiap render menyimpan **MP4 + ASS + SRT** dalam `clips`. Tombol MP4 dan ASS tersedia
untuk render 2.2. MP4 sudah memuat seluruh animasi, tipografi, dan audio hasil edit.

**Paket CapCut + DaVinci** membuat satu timeline per clip. Paket berisi video tanpa
teks, font, audio terpisah, master ASS, SRT, dan keputusan edit terhadap sumber.
Ekspor menambah satu render video tanpa teks per clip; hasilnya dipakai kembali
selama rencana dan sumber tidak berubah.

| Komponen | MP4 final | CapCut | DaVinci |
| --- | --- | --- | --- |
| Framing, materi/pembicara, zoom | Sudah diterapkan | Menyatu pada layer video tanpa teks | Menyatu pada layer video tanpa teks |
| Kata, warna, ukuran, font | Sudah diterapkan | Track teks editable | Fusion Text+ editable |
| Geser dan skala teks | Lengkap | Keyframe native | Kurva native |
| Blur dan fade teks | Lengkap | Belum dipetakan pada teks native | Kurva opacity/blur, perlu pemeriksaan di editor |
| Suara, musik, efek | Campuran final | Track terpisah | Track terpisah |

**ASS tidak otomatis menjadi layer animasi editable yang identik di kedua editor.**
Master ASS disertakan untuk mempertahankan animasi lengkap; teks dikonversi menjadi
track teks CapCut atau Text+ Resolve. SRT adalah cadangan teks biasa tanpa styling.

Ekstrak paket proyek ke folder permanen. Baca `BACA_DULU.txt` di dalamnya:

- Resolve: jalankan `SIAPKAN_DAVINCI.cmd`, instal font, buka Console Lua, lalu
  jalankan `dofile([[C:/path/paket/DaVinci/IMPORT_RESOLVE.lua]])`.
- CapCut: tutup aplikasinya, jalankan `PASANG_CAPCUT.cmd`. Tersedia satu draft
  multi-timeline serta fallback draft per clip melalui opsi `--individual`.

CapCut memakai format draft tidak resmi. Impor di **CapCut 9.5 dan Resolve Free
21.0.4** belum diuji langsung di lingkungan pengembangan. Periksa satu proyek
sebelum memakai banyak clip; posisi baseline/font native dapat berbeda dari MP4.
Untuk mengubah framing yang sudah menyatu pada video, ubah di Clipper dan ekspor ulang.

## Batas hasil

Template ini mengambil pendekatan visual contoh yang Anda berikan; bukan salinan
persis seluruh editing suatu akun. Pemilihan isi, waktu kata, dan kejernihan sumber
masih memengaruhi hasil. Tidak ada jaminan FYP atau waktu total 30 menit. Upgrade
ini terutama memperbaiki tipografi, keterbacaan, dan ekspor, tanpa mengganti model
seleksi topik yang sudah berhasil di laptop Anda.

Jika bermasalah, kirim `.render.log`, `edit-plan.json` clip terkait, atau
`manifest.json` dari paket proyek, beserta screenshot. Jangan kirim `.env`/API key.
