# Clipper Studio 4.0.6 — Tahap 6

Tahap 6 melengkapi backlog 51–60: penggunaan sehari-hari, pengelolaan gaya dan berkas, pilihan ekspor, serta pencatatan hasil evaluasi. Baseline adalah GitHub `akbarttnjg/clipper_pro`, commit `04213e284c744a16d722f6f9aafb15395396d33c` (Tahap 5). Kode paket dibuat sebagai commit lokal terpisah; paket tidak menyatakan sudah dipublikasikan ke GitHub.

## Memasang upgrade

1. Ekstrak seluruh ZIP ke folder baru. Jangan menempel isi `payload` secara manual.
2. Hentikan antrean, tutup server aplikasi dengan Ctrl+C, dan tutup jendela editor yang sedang memakai berkasnya.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`. Target biasa adalah `C:\AI\clipper`. Jika lokasi berbeda, gunakan parameter `--target "D:\lokasi\clipper"` yang sama pada pemeriksaan dan pemasangan.
4. Bila pemeriksaan lulus, jalankan `UPGRADE_TAHAP_6.cmd`.
5. Jalankan `JALANKAN_PRO.cmd` dari folder aplikasi, lalu Ctrl+F5 pada browser. Header harus menampilkan **4.0.6**.
6. Untuk memulihkan kode sebelumnya, tutup server lalu jalankan `PULIHKAN_UPGRADE_TAHAP_6.cmd` dengan target yang sama.

Installer memeriksa checksum baseline, mencadangkan kode yang berubah, melakukan pemeriksaan impor, dan memulihkan kode jika pemasangan gagal. Pemeriksaan menolak kode lokal yang berbeda agar perubahan Anda tidak tertimpa. Jangan memaksa pemeriksaan tersebut; pesan menyebut berkas yang perlu dibandingkan.

Paket memperbarui kode tanpa pip atau unduhan model. Folder `work`, `clips`, `uploads`, `.venv`, `models`, dan konfigurasi `.env` tetap dipakai. SQLite menambahkan tabel workspace ketika fitur baru digunakan. Rollback kode tidak menghapus proyek, brand kit, evaluasi, atau preferensi yang sudah disimpan.

## Alur empat langkah

**Sumber → Pilih klip → Tata gaya → Periksa / ekspor.**

- Sumber: pilih bahasa, track suara, dan kamus sebelum analisis. Angka serta negasi tetap perlu ditinjau.
- Pilih klip: dengarkan batas cerita, tinjau kandidat tertolak, atau tentukan rentang manual. Durasi 20–120 detik adalah batas lunak; tidak ada kuota tetap 10 klip.
- Tata gaya: sunting rasio aktif, simpan pengaturan, periksa keterbacaan, lalu buat preview/final.
- Periksa / ekspor: gunakan final revisi aktif; baca layer dan batas setiap mode sebelum membuat paket.

Pengaturan warna/font memerlukan preview dan final baru. Perubahan itu tidak menjalankan ASR atau pencarian cerita otomatis. Hash tugas sumber memisahkan pengaturan analisis dari gaya; cache ASR yang sama tetap bisa dipakai. Perubahan bahasa/track suara tetap memerlukan analisis terkait.

## Brand kit dan alternatif

Di **Tata gaya → Brand kit & alternatif**, simpan pengaturan yang sudah tersimpan sebagai kit baru. Kit memuat pasangan font, warna teks/aksen, intensitas, posisi/perataan, skala, preset dan aturan layout. Kit tersedia pada proyek lain dalam database aplikasi yang sama.

Pilih cakupan **klip dan rasio aktif** atau **semua klip dan kedua rasio**. Pengaturan yang sudah disimpan manual melalui editor dilindungi. Kit dapat memperbarui nilai yang sebelumnya berasal dari kit; koreksi kata, timing, potongan, B-roll dan area visual manual tidak ditimpa. Riwayat menunjukkan perubahan yang benar-benar diterapkan.

**Simpan alternatif seed** hanya mengganti seed desain. Pilih preset Rapi, Ekspresif atau Adaptif terlebih dahulu. Buat preview sesudahnya untuk melihat alternatif; tombol itu tidak menjalankan analisis sumber. Undo pada Riwayat membatalkan perubahan tersebut tanpa mengembalikan pengaturan lain yang disunting sesudahnya. Jika bagian yang sama sudah disunting lagi, undo memberi konflik.

## Berkas dan cache

**Berkas & cache** menampilkan ukuran dan kelompok berkas. Hanya cache preview yang dimiliki aplikasi dapat dipilih untuk dihapus. Sumber, final, paket editor, database/transkrip, model, musik/SFX per rasio, aset yang masih dirujuk final, dan dua video evaluasi tersimpan dilindungi. Ukuran total fisik menghitung berkas bersama sekali; daftar proyek dapat menampilkan referensi berkas bersama pada beberapa proyek.

Daftar mempunyai identitas revisi berkas dan status perlindungan. Pembersihan ditolak bila daftar berubah atau antrean aktif. Pemeriksaan referensi dan penghapusan cache berlangsung saat perubahan database ditahan, sehingga referensi baru tidak disimpan di tengah pembersihan.

Tombol **Unduh manifest proyek** pada Evaluasi mencatat folder, berkas/ukuran, identitas sumber, hash tahap dan varian, serta pengaturan manual. Manifest adalah inventaris saat tombol ditekan; gunakan backup proyek untuk pemulihan, bukan manifest saja.

Antrean menyediakan pembatalan dan **Lanjutkan**. Lanjutkan mengantrekan pekerjaan terhadap masukan terbaru serta menggunakan cache tahap yang masih sesuai. Proses FFmpeg/model yang terputus memulai tahap tersebut kembali; tidak ada klaim melanjutkan encoder dari frame terakhir.

## Pilihan ekspor

| Mode | Dapat diedit | Menyatu / batas |
| --- | --- | --- |
| Tampilan terjaga | MP4 sebagai satu video; SRT/ASS adalah berkas pendamping. | Semua efek/caption/mix menyatu di MP4. Paket menyalin MP4 dengan checksum yang sama; tidak menghasilkan draft native. |
| Hibrida | Teks, stem audio, track B-roll. | Framing/zoom sumber dan geometri plate ilustrasi menyatu. Blur/fade teks CapCut belum setara ASS; Text+/font Resolve perlu diperiksa. |
| Native dasar | Potongan sumber, crop statis, teks, stem audio, track B-roll. | Hanya shot crop tunggal tanpa zoom animasi dan tanpa tinggi fit khusus. Sumber utuh disertakan. Layout beberapa area memerlukan hibrida. Efek/font native tidak dijamin identik. |

Mode native dasar dibatasi berdasarkan rencana final. UI menjelaskan alasan bila belum tersedia; server juga menolak mode yang tidak sesuai. Status per editor membedakan pembuatan, pemeriksaan struktur dan impor native. Kegagalan membuat satu editor tetap muncul meskipun editor lain berhasil.

**Struktur lolos tidak membuktikan editor bisa membuka, mengedit, menyimpan, atau merendernya.** CapCut 9.5.0 memakai adapter format draft eksperimental yang diwarisi dari tahap sebelumnya. Resolve 21 menggunakan XML/Fusion/Lua. Jalur native tetap memerlukan pengujian pada aplikasi sasaran.

## Evaluasi & bukti impor

Tombol **Evaluasi & bukti impor** berada pada header. Pilih klip dan rasio di editor dahulu.

1. Buat baseline preview/final pada Tahap 6.
2. Ubah satu bagian desain atau renderer, simpan, dan buat variasi dengan kualitas preview yang sama.
3. Pilih dua hasil tersimpan dan kategori sumber; tekan **Ukur dua hasil tersimpan**. Antrean menjalankan perbandingan CPU tanpa memuat ASR/CV/model.
4. Tonton keduanya. Isi hasil peninjauan, alasan, koreksi manual, benturan area penting dan cerita dengan isi berbeda. Biarkan jumlah kosong jika belum diukur.
5. Simpan penilaian manusia. Preferensi awal tidak berubah otomatis.
6. Jika variasi dinilai lebih baik, tombol **Gunakan variasi terpilih untuk proyek baru** dapat menyimpan pengaturan gaya kandidat tersebut. Perlu tindakan eksplisit; proyek lama tidak diperbarui.

Pembanding harus mempunyai sumber, transkrip/kata, potongan, audio mix, rasio dan kualitas yang sama. Perbandingan ini ditujukan pada desain/renderer; tidak mengevaluasi perubahan transkrip atau cerita dengan SSIM. Hasil sebelum Tahap 6 tetap dapat ditonton, tetapi tidak dipakai sebagai pembanding interaktif karena konteks lengkap belum tersimpan.

FFmpeg menghitung SSIM/PSNR pada resolusi, FPS dan durasi yang sama, maksimal 60 detik pertama. Catatan menyebut jika hanya sebagian video diukur. Nilai ini mengukur perbedaan piksel; perubahan desain yang bagus dapat menurunkan SSIM. SSIM 1 juga tidak membuktikan estetika, deteksi visual, akurasi ucapan atau kejelasan dialog.

Dataset mempunyai lima kategori: pembicara, chart, papan, beberapa pembicara dan sumber bergrafis. Untuk evaluasi nyata, buat proyek dari sumber asli pada setiap kategori, pertahankan pembahasan yang sama, lalu simpan baseline dan variasi pada kedua rasio. Kumpulan yang sudah dijalankan dalam QA paket memakai grafis sintetis, kata fixture dan nada uji. Itu menguji regresi mekanis, bukan mutu model pada video manusia.

Tugas mencatat waktu, sampel RAM dan sampel VRAM jika tersedia. Tanpa psutil, RAM diukur pada proses worker saja (Windows: peak working set; Linux: sampel RSS). Jika psutil tersedia, anak proses ikut dijumlahkan. Sampel dapat melewatkan lonjakan singkat. VRAM adalah total perangkat bersama, bukan atribusi khusus worker. Nilai yang tidak tersedia tetap kosong, bukan nol. Pengukuran laptop RTX 3050 4 GB masih perlu dijalankan.

### Matriks impor native

Matriks awal mencakup CapCut 9.5.0 dan Resolve 21 pada 9:16 dan 16:9, semuanya **belum diuji** sampai bukti dicatat.

Untuk setiap paket/editor/rasio: buka paket, edit kata, simpan proyek, render dengan ukuran/durasi yang sama, lalu bandingkan font, framing, efek dan audio dengan MP4 Reference. Isi versi editor, lima langkah, lokasi MP4 hasil editor dan catatan pembandingan. Pilih paket yang pembuatan/struktur editornya sudah lolos.

Status disimpan sebagai **laporan pengguna**. Aplikasi memeriksa identitas paket, berkas render, ukuran dan durasi, tetapi tidak mengotomatisasi tindakan di editor. Bila isi paket atau render berubah, bukti menjadi lama. Bukti tidak diwariskan ke paket baru. Jadi formulir lengkap tetap bukan klaim bahwa QA server telah melakukan impor native.

## Verifikasi yang tersedia

- Uji SQLite/FFmpeg untuk kit, konflik revisi, undo, perlindungan cache, hash ASR, antrean, perbandingan, bukti dan preferensi.
- Regresi tipografi Tahap 5 serta kontrol UI melalui DOM adapter. DOM adapter tidak membuktikan tampilan/keyboard browser.
- Sepuluh pasangan video: lima kategori sintetis × dua rasio, kode Tahap 5 yang sama dengan GitHub dibandingkan dengan Tahap 6. Semua pasangan memberikan piksel yang identik.
- Paket tampilan terjaga memuat MP4 dengan checksum identik. XML/Fusion Resolve pada mode hibrida dan native dasar lolos pemeriksaan struktur pada fixture.
- Di lingkungan QA ini pycapcut tidak tersedia; kegagalan pembuatan CapCut dicatat, bukan diganti menjadi status berhasil.
- Uji berkas installer menjalankan dry-run, pemasangan, pengulangan, penolakan perubahan lokal, kegagalan salin/impor, rollback dan perlindungan data. Pemeriksaan impor runtime Windows disimulasikan pada uji berkas; impor aplikasi lengkap dan CMD belum dijalankan di laptop.

Untuk mengulang media QA, simpan salinan kode 4.0.5 sebelum upgrade lalu jalankan:

```text
python tools/verify_stage6_media.py --baseline-root "D:\kode-4.0.5" --output "D:\evaluasi-tahap6-baru"
```

Gunakan folder keluaran baru. Tool tidak memasang dependensi atau menjalankan model/editor.

| ID | Hasil Tahap 6 | Penerimaan yang masih perlu dilakukan |
| --- | --- | --- |
| 51 | Empat tahap, keterangan dampak, pilihan mode. | Browser/laptop dan kenyamanan penggunaan. |
| 52 | Kit lintas proyek; override manual dilindungi. | Tinjauan konsistensi gaya pada beberapa proyek nyata. |
| 53 | Variasi seed terarah, riwayat dan undo. | Tinjauan alternatif pada materi nyata. |
| 54 | Inventaris/manifest, ukuran, cache terpilih dan perlindungan referensi. | Periksa folder pengguna yang sudah besar. |
| 55 | Hash tahap sumber terpisah dari warna; cancel/retry memakai masukan terbaru. | Pembatalan dan resume proses berat pada Windows. |
| 56 | Tiga jalur ekspor aktual beserta daftar layer/batas. | Tampilan dan editabilitas di editor sasaran. |
| 57 | Matriks dan pencatatan bukti terikat paket/render. | **Belum lulus native: buka, edit, simpan, render, bandingkan di kedua editor/rasio.** |
| 58 | Lima kategori, fixture regresi dua rasio dan pembanding tersimpan. | **Koleksi lima kategori video manusia dan penilaian nyata belum selesai.** |
| 59 | Waktu/sampel RAM/VRAM, isu keterbacaan dan jumlah koreksi/cerita manual. | **Benchmark RTX 3050, akurasi ASR, dialog dan estetika belum diukur.** |
| 60 | Umpan balik dan preferensi dari variasi yang dipilih lebih baik. | Penilaian hasil manusia sebelum mengganti default. |

Implementasi Tahap 6 siap dicoba; seluruh enam tahap belum boleh dianggap lulus penerimaan hanya berdasarkan jumlah tes. Uji runtime Remotion/Motion Canvas, SigLIP2, TalkNet/SAM, native editor dan perangkat tetap mengikuti bukti masing-masing tahap.
