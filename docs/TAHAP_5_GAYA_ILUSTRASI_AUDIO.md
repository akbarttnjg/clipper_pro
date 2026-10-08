# Clipper Studio 4.0.5 — Tahap 5

Dasar: GitHub `akbarttnjg/clipper_pro`, commit
`a1a6e3a35842ef269196e819542617298c66b210` (Studio 4.0.4). Snapshot Tahap 5
dibuat lokal; SHA sumber lengkap tercatat di manifest paket. Panduan ini
melanjutkan backlog nomor 41–50. Kode tersedia, dengan batas pengujian di bawah.

## Memasang

1. Ekstrak seluruh ZIP ke folder baru.
2. Hentikan antrean dan tutup server Clipper lama dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd --target C:\AI\clipper`.
4. Jika pemeriksaan lulus, jalankan `UPGRADE_TAHAP_5.cmd --target C:\AI\clipper`.
5. Jalankan `JALANKAN_PRO.cmd` pada instalasi lama. Tekan Ctrl+F5 di browser.

Pemasang memeriksa kode dasar dan checksum payload sebelum menulis. Kode lokal
yang berbeda ditolak agar perubahan Anda dapat dibandingkan dahulu. Upgrade
tidak menyentuh proyek, video, unggahan, musik, `.env`, `.venv`, dan model.
Tidak ada pip, npm, atau unduhan model otomatis saat upgrade.

Rollback: tutup server, lalu jalankan
`PULIHKAN_UPGRADE_TAHAP_5.cmd --target C:\AI\clipper`. Cadangan berada dalam
`steezy_backups/stage5-*`. Pemulihan memeriksa integritas cadangan dan menolak
menimpa file kode yang telah diubah setelah upgrade. Data proyek tetap tersedia.

Jika instalasi Anda belum sesuai 4.0.4, gunakan paket Tahap 4 terlebih dahulu.
Paket Tahap 5 ini tidak menjalankan ulang instalasi awal atau menurunkan versi.

## Menggunakan gaya

Pada satu klip, buka **Edit → Gaya Tahap 5 & keterbacaan**. Pilih preset dan
klik **Simpan gaya Tahap 5**. Perubahan berlaku pada rasio yang dipilih.
Proyek lama mempertahankan gaya manualnya sampai preset dipilih.

| Preset | Perilaku |
|---|---|
| Rapi | Frasa tampil utuh, baseline stabil, penekanan seperlunya, tanpa pantulan. |
| Ekspresif | Hierarki ukuran, arah masuk dan perataan bervariasi per frasa. |
| Adaptif | Mengurangi gerak dan ukuran ketika materi atau kepadatan ucapan perlu diprioritaskan. |

Pemilihan preset baru menerapkan pasangan DM Sans / DM Serif Display dan
outline gelap. Font dapat diatur lagi di panel Tata teks. **Seed desain** yang
sama mempertahankan keputusan komposisi ketika preview diulang. Mengubah seed
memilih variasi baru tanpa mengubah transkrip. 16:9 dan 9:16 mengukur panel,
pemenggalan baris, ukuran font dan area aman masing-masing; keputusan desain
tidak diacak lagi saat final dirender.

Klik **Periksa keterbacaan klip** sebelum membuat final. Pemeriksaan masuk ke
antrean yang sama dengan pekerjaan lain. Laporan per frasa memuat kecepatan
baca, huruf yang terlalu kecil, kontras terhadap outline, tabrakan kata,
tabrakan dengan wajah/materi, serta seluruh rentang animasi. Setiap masalah
memiliki saran perbaikan dan tombol untuk mendengarkan waktu sumber. Laporan
ditandai lama setelah pengaturan atau bahan berubah. Draf bertahan jika ada
konflik revisi; muat revisi terbaru untuk meninjau draf, atau buang draf.

Penekanan menggunakan bukti makna/keyword yang sudah tersedia. Angka beserta
mata uang atau satuannya tetap satu unit tampilan; negasi tetap disertakan
dalam penekanan frasa terkait. Energi PCM per kata dicatat sebagai bukti
pendukung pada render. Energi lebih keras tidak dianggap sebagai bukti makna,
identitas pembicara, emosi, atau kebenaran klaim. Kata asli dan lineage tetap
tersimpan. Teks tidak diganti atau diperbaiki berdasarkan perkiraan intonasi.

## Renderer lokal dan Remotion

**Subtitle lokal** adalah bawaan. Preview dan final menjalankan CaptionPlan
terukur yang sama melalui ASS/libass. Font, warna, seed, panel, ukuran dan
sampel animasi disimpan pada rencana tersebut.

**Remotion bila siap** memakai komponen Remotion yang telah terpasang dan lulus
uji sampel, paket renderer/bundler dan browser lokal. Jika belum siap atau
gagal, render lokal tetap berjalan dan alasannya tersimpan. **Wajib Remotion
lokal** menghentikan proses jika persyaratan itu tidak dipenuhi.

Adapter produksi membundel React lokal, memasukkan font lokal, merender VP9
dengan alpha, PNG per frame dan concurrency 1. FFmpeg memakai decoder
libvpx-vp9 agar alpha dipertahankan sebelum overlay. Ukuran, durasi dan tag
alpha output diperiksa. Render tidak memasang paket atau mengunduh browser.
Pemasangan/uji komponen dilakukan secara eksplisit di panel Komponen.

Paket Remotion lama mungkin perlu dipasang ulang melalui pengelola komponen
untuk memperoleh `@remotion/renderer` dan `@remotion/bundler`. Perubahan
generation/receipt membatalkan cache output. Jika browser hasil uji lama belum
dikenali, jalankan uji sampel komponen kembali.

Kesamaan CaptionPlan dan keputusan seed telah diuji. Kesamaan piksel antara
libass dan font browser belum diuji; jangan menganggap pergantian engine
menjamin hasil piksel identik. Ekspor editor tetap memakai rencana teks
terukur. Pemetaan baru di CapCut/Resolve belum diuji melalui aplikasi desktop.

## Ilustrasi dan B-roll

**Kartu kutipan dari ucapan** bersifat opsional. Kutipan berasal dari frasa
sumber dan menyimpan referensi kata. Tidak ada angka, nilai grafik atau fakta
baru. Sisipan dibatasi di tengah klip, berjarak, paling banyak dua, dan tidak
menggantikan materi papan tulis. Jadwal mengikuti potongan yang benar-benar
dipakai; pembuka, penutup, materi dan subtitle dilindungi oleh jadwal/area aman.

Kartu memiliki proyek Motion Canvas 3.17.2 yang dapat diedit dan adapter browser
yang memanggil Renderer untuk mengambil frame. Jika lingkungan Node, adapter
Playwright dan browser lokal tersedia, frame dikodekan menjadi aset MP4.
Jika tidak, Pillow/FFmpeg membuat kartu lokal dan laporan menampilkan status
Motion Canvas sebenarnya. **Build proyek bukan bukti render browser.**

B-roll stok tetap memakai konteks kalimat, variasi kueri, metadata dan bukti
asal. Ranking **SigLIP2 bila siap** memproses dua frame per kandidat, pada CPU,
dalam lingkungan model lokal dan anggaran kandidat yang sudah dipilih.
Hanya bobot lokal dipakai, tanpa remote code atau unduhan saat inferensi.
Urutan, skor relatif, jumlah sampel dan provenance disimpan bersama aset.
Pemeriksaan visual selektif berjalan terpisah sesudah ranking. Skor tinggi
bukan pengesahan isi atau watermark. Mode **Wajib SigLIP2 lokal** melewati
kandidat jika model belum siap. Mode otomatis melanjutkan penilaian metadata
dan pemeriksaan yang tersedia, dengan catatan status. Aset tidak cocok atau
gagal mempertahankan gambar sumber.

## Audio

Panel **Suara & musik** menyediakan target LUFS, batas true peak, musik lokal,
SFX lokal, volume dan pilihan SFX nonaktif/jarang. Musik memakai sidechain
ducking terhadap stem dialog. SFX mengikuti zoom/pembuka atau awal frasa
penting, dengan batas enam, jarak minimal delapan detik (bawaan sepuluh), dan
tidak ditempatkan terlalu dekat awal/akhir. Fade potongan, volume dan limiter
tetap berjalan. Stem terpisah serta loudness terukur tercatat pada rencana.

Musik/SFX harus berasal dari koleksi yang berhak Anda gunakan. Paket tidak
mengambil atau membeli audio. Uji nada sintetis membuktikan jalur filter,
bukan kejernihan ucapan manusia; dengarkan preview pada sumber Anda.

## Bukti pengujian dan batas penerimaan

| Backlog | Kode dan verifikasi yang tersedia | Penerimaan yang masih diperlukan |
|---|---|---|
| 41 Rapi | Geometri terukur, baseline stabil, pasangan font, MP4 nyata dua rasio. | Review pada ponsel dan footage pengguna. |
| 42 Ekspresif | Seed stabil, variasi template/arah/perataan, tes cache dan MP4. | Review estetika animasi pada materi pengguna. |
| 43 Adaptif | Penurunan intensitas pada materi/ucapan padat, tes anchor dan MP4. | Adegan chart/papan tulis nyata di mesin pengguna. |
| 44 Penekanan | Lineage angka/satuan/negasi, keyword/makna, pendukung energi PCM. | Review makna dan intonasi ucapan nyata. |
| 45 Keterbacaan | Pemeriksaan sebelum render, antrean, revisi, saran tiap frasa. | QA browser nyata untuk laporan dan navigasi. |
| 46 Remotion | Adapter produksi + CaptionPlan/font/seed bersama, fallback/wajib diuji; overlay alpha FFmpeg diuji. | Render browser Remotion, parity font dan performa laptop. |
| 47 Motion Canvas | Proyek/adapter frame dan kartu kutipan lokal nyata. | Eksekusi browser Motion Canvas pada komponen asli. |
| 48 B-roll konteks | Kueri alternatif, sumber lokal, jadwal dan alasan relevansi tetap terhubung. | Relevansi pada footage dan koleksi pengguna. |
| 49 SigLIP2 | Worker lokal bounded + urutan/skor/sampel pada proposal; pemisahan verifikasi visual. | Inferensi bobot asli dan evaluasi ranking. |
| 50 Audio | Normalisasi, ducking, limiter, SFX jarang; loudness MP4 nyata. | Uji dengar dialog manusia dengan musik/SFX. |

Pengujian yang disertakan tidak mengklaim bahwa semua acceptance backlog telah
lulus. Enam MP4 memakai gambar dan waktu kata sintetis serta nada uji. Lima
frame sampel identik setelah render ulang. Pemasang diuji dengan salinan kode
4.0.4 nyata; probe import runtime dalam pengujian instalasi menggunakan stub
karena dependensi aplikasi Windows tidak tersedia di lingkungan uji ini.
Salinan, checksum, backup dan rollback memakai operasi file sebenarnya.

Windows CMD, RTX 3050/NVENC, render browser renderer opsional, bobot SigLIP2,
aplikasi desktop CapCut 9.5.0/Resolve 21, dan pengujian ucapan nyata masih belum
lulus acceptance. Uji 544 test Tahap 4 merupakan bukti historis, bukan hasil
suite penuh yang dijalankan ulang untuk Tahap 5. Bukti tepat ada di `verification`.

Perintah pengujian di instalasi dengan dependensi inti:

```bat
python -m unittest clipper.tests.test_style5 clipper.tests.test_style5_service clipper.tests.test_stage5_release
node clipper/tests/style5_ui.cjs
python tools/verify_stage5_media.py
```

Uji media membuat fixture di `work/stage5-verification`, menggunakan CPU dan
FFmpeg lokal; tidak memanggil ASR, Ollama, situs stok atau model eksternal.

Referensi implementasi primer:

- https://www.remotion.dev/docs/renderer/render-media
- https://www.remotion.dev/docs/bundle
- https://www.remotion.dev/docs/renderer/ensure-browser
- https://www.remotion.dev/docs/transparent-videos
- https://github.com/motion-canvas/motion-canvas/blob/v3.17.2/packages/core/src/app/Renderer.ts
- https://github.com/motion-canvas/motion-canvas/blob/v3.17.2/packages/core/src/app/Stage.ts
- https://huggingface.co/docs/transformers/model_doc/siglip2
