# Clipper Studio 4.0.10

Pembaruan 10 Oktober 2026. Kelanjutan dari GitHub main 4.0.9, commit
`2e5d97621be0d2576f62c13c4c04696c6cadef06`.
Perubahan 4.0.10 yang terhenti di percakapan lama tidak tersedia sebagai patch;
versi ini dibangun kembali dari 4.0.9 dan catatan audit terakhir.

## Perubahan yang sudah diterapkan

1. **Ukur frasa sebelum mencari ruang.** Mesin mengukur huruf, kebutuhan baris,
   dan geraknya terlebih dahulu. Bidang kosong yang lebih pendek dapat dipakai
   tanpa langsung mengecilkan pembicara atau menambahkan pita hitam besar.
2. **Konflik antaradegan dibatasi pada frasa terkait.** Jika tidak ada ruang aman,
   band tetap tersedia sebagai langkah terakhir. Tingginya mengikuti kebutuhan
   teks; konflik singkat tidak lagi memaksa band sepanjang kedua adegan.
3. **Huruf kecil ikut diperiksa.** Laporan mengukur H dan a pada tampilan setara
   lebar 360 piksel. Target minimum 14 piksel adalah aturan profil, bukan jaminan
   estetika atau standar semua platform. Frasa pendek dengan fokus di tengah
   tidak otomatis dipaksa menjadi tiga baris.
4. **Ukuran dan baseline berdasarkan glyph.** Pemeriksaan geometri dan render ASS
   memakai batas tinta huruf serta baseline font; kotak vertikal nominal yang
   berlebihan tidak lagi menghalangi susunan lanskap. Rencana lama tetap didukung.
5. **Kata bertanda hubung tetap utuh.** `terus -terusan` menjadi `terus-terusan`,
   `gara - gara` menjadi `gara-gara`. Tidak menambahkan kata/tanda hubung yang
   tidak ada. ID, rentang waktu, negasi, angka negatif dan transkrip asal dijaga.
6. **Variasi gerak otomatis bertambah.** Blur menjadi tajam, narasi, pop, serta
   empat arah masuk dipilih secara deterministik. Pilihan template manual tetap
   dihormati. Preset Rapi tetap tenang; preview dan final memakai keputusan desain
   pada resolusi acuan yang sama.
7. **Mask segmentasi memakai waktu yang cocok.** MediaPipe diminta pada waktu
   sampel statistik gambar. Mask tidak ditempelkan ke grid dari waktu berbeda.
   Anggaran tetap maksimal delapan frame; ini belum tracking seluruh frame.
8. **E5 masuk ke pembandingan cerita.** E5 lokal mengusulkan maksimal 16 pasangan
   dari maksimal 96 klaim tersampel untuk pemeriksaan kutipan lintas bab. Skor
   kemiripan tidak menghapus klip. Pemeriksaan kutipan, jenis cerita, angka,
   satuan, negasi dan syarat tetap berlaku. Model tidak siap: alur biasa berjalan.
9. **Alignment lokal pada klip terpilih.** Maksimal 24 kata/frasa yang dikoreksi
   atau memiliki keyakinan ASR rendah dapat diukur ulang memakai model CTC lokal.
   Hasil hanya diterapkan pada salinan untuk render, harus cocok dengan teks,
   skor dan batas tetangga. Timing manual dipertahankan. Cache bisa dipakai kedua
   rasio. Status/alasan tersedia dalam laporan gaya dan rencana edit.
10. **Pemasang dan identitas cache diperbarui.** Versi UI menjadi 4.0.10 dan hasil
    render lama tidak dianggap sebagai hasil mesin baru. Backup dan rollback
    kode mempertahankan koreksi proyek yang dibuat setelah upgrade.

## Pasang

Paket ini untuk mesin **4.0.9 yang cocok dengan commit dasar di atas**, bukan
installer awal. Python, FFmpeg, dan dependensi inti mesin lama harus tersedia.

1. Ekstrak ZIP ke folder baru di luar folder mesin.
2. Hentikan antrean, lalu hentikan server dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`; masukkan folder yang berisi `app.py` dan
   `JALANKAN_PRO.cmd`. Contoh folder hanya contoh; gunakan lokasi mesin Anda.
4. Jika lulus, jalankan `PASANG_UPGRADE_4_0_10.cmd` dengan folder yang sama.
5. Jalankan `JALANKAN_PRO.cmd` dari mesin, buka UI, tekan Ctrl+F5.

Alternatif PowerShell, dari folder paket:

```powershell
.\CEK_SEBELUM_UPGRADE.cmd --target "C:\AI\clipper"
.\PASANG_UPGRADE_4_0_10.cmd --target "C:\AI\clipper"
```

Jika pemasang menyebut kode lokal berbeda, simpan daftar file yang disebutkan;
jangan menyalin payload secara paksa. Pemasang memeriksa sebelum menimpa, membuat
cadangan kode dan database, lalu mengembalikan kode jika pemeriksaan akhir gagal.
Rollback: jalankan `PULIHKAN_UPGRADE_4_0_10.cmd`. Rollback ini mengembalikan kode,
bukan menghapus perubahan proyek setelah pemasangan.

## Pengaturan awal yang disarankan

| Pengaturan | Nilai awal |
|---|---|
| Preset | Adaptif; Ekspresif untuk pembicara tanpa materi padat |
| Font utama | DM Sans SemiBold |
| Font aksen | DM Serif Display Italic |
| Komposisi frasa | Otomatis |
| Pilihan template | Variasi mengikuti preset |
| Skala teks | 1,00 |
| Posisi dan perataan | Otomatis |
| Gerak | Balanced; Rapi memakai gerak tenang |
| Warna dasar / aksen | Putih / #F6CF69 |
| Outline / latar pelindung | Aktif |
| Renderer | Subtitle lokal / ASS |
| Seed | 2026 |
| Punch zoom | Nonaktif untuk pembandingan awal |
| Segmentasi | MediaPipe bila sudah siap |
| Selaraskan frasa klip | Otomatis bila model lokal siap |

Tidak ada pemasangan/unduhan model otomatis saat render. Perbaikan 1–6 berfungsi
tanpa model baru. MediaPipe dan E5 memakai komponen yang sudah dipasang dan lulus
uji sampel. Alignment membutuhkan WhisperX serta folder model **Wav2Vec2 CTC
bahasa sumber**, berbeda dari model Whisper ASR. Tentukan `alignment_model_path`
pada pengaturan analisis yang sudah tersedia, atau `ALIGNMENT_MODEL_PATH` pada
konfigurasi lokal. Untuk bahasa Indonesia pilih bahasa `id`; bahasa `auto` yang
belum diketahui dapat menyebabkan alignment dilewati. Tidak perlu mengunduh semua
komponen hanya untuk mencoba upgrade ini.

## Verifikasi dan batas bukti

Lihat `docs/verification/HASIL_QA_4_0_10.md` dan folder `verification/` dalam ZIP.
Dua render 62 detik menggunakan sumber sintetis, transkrip uji dan kotak objek
yang ditentukan, dengan renderer FFmpeg produksi. Bukti ini menguji jalur layout
dan encoding sampai kasus detik 50/53; bukan rekaman baru dari video pengguna.

Model E5, CTC dan MediaPipe belum dijalankan dengan bobot nyata pada rilis ini.
Dependensi OpenCV/FastAPI di lingkungan pembuat paket tidak tersedia; suite
aplikasi lengkap dan alur detektor langsung belum dapat dijalankan di sini.
Pemasang tetap mensyaratkan dependensi inti dan melakukan pemeriksaan impor di
mesin tujuan. Uji kontrak, fallback dan perlindungan data menggunakan fixture.

CapCut yang sudah berfungsi tidak diganti mekanisme ekspornya. Impor/edit/render
native CapCut dan Resolve tidak diuji ulang di Windows; masalah teks Resolve
tetap ditunda. Kecepatan video 1–2 jam selesai dalam 30 menit belum dibuktikan.
Rilis ini juga belum menyelesaikan seluruh 22 gagasan pengembangan pada chat lama.

Untuk pembandingan pertama, render ulang klip yang sama dalam dua rasio dan
periksa sekitar detik 11–23, 50, dan 53–54. Setelah itu nilai: ukuran pembicara,
huruf kecil, frasa utuh, posisi terhadap wajah/materi, dan variasi gerak.
