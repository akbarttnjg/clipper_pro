# Clipper Pro 4.0.12 M1

Paket ini melanjutkan M0 4.0.11 dan M1 awal. Dasar pengerjaan adalah **Arsitektur Clipper Pro Terpadu, 120 halaman**, terutama halaman 17, 19, 20, 24, 42–46, 94–95, 113–114, dan gate G1 pada halaman 120. SHA-256 PDF: `76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36`.

Implementasi enam paket M1 tersedia dalam rilis ini. Pengujian kode, API, SQLite dan media sintetis berbeda dari penerimaan pada Windows, laptop pengguna, video asli, dan aplikasi editor. **Gate lapangan G1 belum dinyatakan tertutup.** Typography profesional dan evaluasi estetika video tetap pekerjaan M4/M5, bukan hasil yang disimpulkan dari jumlah tes.

## Pasang

1. Ekstrak ZIP ke folder baru, di luar folder mesin. Hentikan antrean dan server.
2. Jalankan `CEK_SEBELUM_UPGRADE.cmd`, lalu masukkan folder mesin yang sudah bekerja.
3. Jika pemeriksaan lolos, jalankan `PASANG_M1_4_0_12.cmd` untuk folder yang sama.
4. Jalankan `JALANKAN_PRO.cmd` dari folder mesin. Buka halaman mesin dan tekan Ctrl+F5. Versi pada header menjadi **4.0.12 M1**.

Jangan menyalin isi `payload` secara manual. Installer memeriksa hash dasar, menjaga perubahan lokal, mencadangkan kode dan SQLite, serta memulihkan kode jika penyalinan atau pemeriksaan impor gagal. Dasar yang diterima adalah M0 GitHub `b8c4ce275021a7b09db2710939a4c063b754f35b`, M1 awal yang terverifikasi, atau berkas paket ini yang sudah terpasang. Kode dasar lain ditolak sebelum penimpaan.

Paket tidak memasang model atau mengubah `.venv`, `.env`, video sumber, font pribadi, dan direktori keluaran. Komponen inti yang sebelumnya bekerja tetap diperlukan. Berkas contoh dalam fixture pengujian berasal dari repo publik; fixture tidak berisi proyek atau video pribadi pengguna.

## Enam paket M1

| Paket | Fungsi yang tersedia |
|---|---|
| M1.1 | Alur **Buat → Pilih → Edit → Ekspor**, bahasa Indonesia, bantuan/satuan/cakupan, status dan tindakan pemulihan. |
| M1.2 | Registry draf sembilan panel, namespace per tab, pemulihan saat reload, snapshot server terpisah, dan preview snapshot tanpa mengganti final tersimpan. |
| M1.3 | Inspector **Teks, Potongan, Tampilan, Kamera, Audio, Ilustrasi**; diff sebelum preset/brand/copy-paste; override per kolom; reset ke induk; round-trip JSON kit. |
| M1.4 | Edit ejaan dan potong ucapan terpisah; timeline/storyboard; split/join/reorder; undo/redo; track mute/solo/kunci; pencarian efektif/asli dan frasa; penggantian dengan review; versi/komentar; clock untuk speed/ramp/reverse/freeze/keyframe/kamera. |
| M1.5 | Nama panel lama menjadi alias pencarian. Kontrol tetap memakai service dan validasi yang sama. Inspector lama masih dapat dipilih sebagai flag pemulihan antarmuka. |
| M1.6 | Mode Sederhana/Studio, enam profil footage, keyboard/fokus, ringkasan sebelum render, dan perbandingan dua rasio/versi dengan seek mengikuti waktu sumber. |

Register seluruh 252 kebutuhan tetap ada dalam `M1_REQUIREMENTS.json`. ID di luar M1 tidak disebut selesai hanya karena masuk register. TX15 dan BR01 adalah irisan gaya/brand yang dikerjakan dalam M1, sementara gate M5 lengkap tetap terpisah.

## Cara memakai editor

Mulai dengan **Mode Sederhana**. Beralih ke **Studio** hanya membuka kontrol lanjut; perubahan mode tidak mengubah nilai proyek. Profil Edukasi mematikan cold-open/hook, title card, punch zoom, dan pemotongan jeda otomatis; posisi caption berada di kiri. Profil lain: finansial, podcast, gaming, layar, dan footage grafis/generatif. Profil generatif tidak menjalankan generator baru.

Di Teks, pencarian dapat memilih **Teks tampil terbaru**, **Ucapan asli**, atau keduanya. Koreksi yang sudah disimpan dan frasa yang digabung masuk pencarian efektif; jumlah, halaman, scope, dan revisi dibaca pada snapshot yang sama. Query literal tidak ditafsirkan sebagai SQL atau regex. Penggantian batch menampilkan diff. Angka, unit, negasi, syarat, serta kandidat nama/istilah memerlukan review khusus. Pemeriksaan nama bersifat konservatif, bukan NER terukur.

Centang kata/frasa untuk menyembunyikan subtitle atau memotong ucapan. **Sembunyikan subtitle** mempertahankan suara. **Potong ucapan** mengubah durasi dan suara pada clock kedua rasio. Sumber dan transkrip asli tetap utuh. Undo tersedia di Riwayat. Waktu pada formulir batas adalah detik sumber; waktu kurva adalah tick mikrodetik pada keluaran, dengan `1.000.000 tick = 1 detik`.

Sebelum menerapkan resep, profil, brand kit, atau atribut, tinjau tabel sebelum/sesudah. Warna dapat disalin tanpa font, gerak, audio, atau batas klip. Kolom manual dapat kembali ke induk lewat **Nilai efektif dan asalnya**. Kit menyimpan policy template, font, warna, gerak dan revisi. JSON kit memuat identitas/digest font; belum membundel font atau aset seperti pack portable M5.

Perubahan yang belum disimpan memblokir render biasa. **Snapshot draft dan perbandingan → Buat snapshot semua draft** menerjemahkan seluruh registry tab ini menjadi command tervalidasi. Setelah review, buat preview 9:16/16:9 dari snapshot tersebut. Preview draft berada pada tab pemain tersendiri dan tidak mengganti final. Untuk final, simpan snapshot menjadi revisi lalu render. Konflik tidak membuang draf. Rebase server hanya menerima perubahan yang tidak bertabrakan; perubahan fakta dengan revisi transkrip baru harus ditinjau kembali.

Ringkasan render menyebut klip, rasio, revisi, dimensi, fps, gaya, policy, seed, font, normalisasi, pilihan backend dan biaya lokal yang belum diukur. Ringkasan ikut disimpan dalam manifest. Backend pilihan berbeda dari backend aktual, yang tercatat pada receipt hasil. Durasi dari batas sumber adalah perkiraan sebelum pemotongan jeda/hook otomatis; clock manual mencatat durasi/frame yang dipakai edit waktu.

## Kontrol lanjut dan batasnya

Clock memakai tick integer, rentang sumber half-open, dan jumlah frame keluaran yang sama untuk video, suara dan caption. Secara bawaan edit waktu diterapkan pada kedua rasio; versi editorial terpisah harus diminta eksplisit. Ramp memakai irisan sumber yang dibatasi dan rate terukur pada tiap irisan. Kurva mendukung scale, X, Y dan opacity sumber, dengan linear/hold/ease-in/ease-out/ease-in-out. Ini belum canvas animasi bebas untuk setiap elemen.

Speed, reverse, freeze, keyframe sumber, dan pergantian kamera memakai **source proxy yang sudah dirender**. Caption dan stems tetap mengikuti jalur ekspor yang dipilih, tetapi efek source tersebut berstatus **baked**, bukan kurva native editable di CapCut/Resolve. Native dasar ditolak untuk source layer lanjutan tersebut; pilih hibrida. B-roll video yang beririsan dengan reverse/ramp perlu dimatikan atau waktunya disederhanakan dahulu; mesin menolak remap aset yang belum aman. Proxy menambah pekerjaan CPU/disk; performa laptop belum dibenchmark.

Multi-camera memakai audio utama sebagai clock. Pengukuran otomatis menguji offset dan drift pada awal/tengah/akhir; sinyal lemah atau ambigu berstatus perlu review. Bukti pengukuran disimpan di server dan tidak menerima skor rekaan dari client. Offset manual diberi label **user confirmed, belum diukur**, dan perlu diperiksa pada tiga bagian. Kamera yang tidak dipakai tidak mengubah fingerprint render.

Mute/solo mengubah penggunaan track; kunci menolak suntingan. Mengubah kunci saja tidak mengubah piksel atau menggugurkan cache. Komentar terikat klip/waktu sumber/revisi; komentar lama perlu ditinjau sebelum diselesaikan.

CapCut yang sudah bekerja tidak diganti backend-nya oleh upgrade ini. Target regresi arsitektur adalah CapCut 4.7.0. Penerimaan impor native tetap memerlukan uji aplikasi target. Perbaikan teks/font Resolve 18.6.6 tetap ditunda sesuai permintaan Anda.

## Keyboard dan antarmuka

- Ctrl+K: temukan fitur dan alias panel lama.
- Ctrl+S: buka bagian penyimpanan snapshot/draf.
- Ctrl+Z / Ctrl+Shift+Z di luar kolom teks: undo/redo revisi, setelah draf disimpan.
- Spasi di luar input: putar/jeda video.
- Tab dan Shift+Tab: navigasi kontrol; fokus terlihat.

Layout berubah menjadi satu kolom pada viewport sempit, tabel dapat digeser, dan kontrol lanjut tersedia melalui mode Studio. Uji zoom 150% dan browser Windows belum diklaim lolos oleh DOM adapter. Galeri menyatakan dependensi dan fase untuk fitur yang belum diaktifkan, termasuk pose/gesture, finishing typography, Resolve, publikasi/analytics, serta recording/creative AI.

## Pengujian dan bukti

Run final: **924 lulus, 0 gagal, 0 error, 61 skip** dari 985 kasus. Di dalamnya termasuk **139 kasus M1** (111 kontrak/API/media, 18 regresi M1 awal, 10 installer), semuanya lulus tanpa skip. Sepuluh suite JavaScript/DOM adapter juga lulus. Skip suite penuh terdiri dari 17 kasus OpenCV/environment inti, 22 kasus pyCapCut, dan 22 fixture installer historis yang tidak tersedia.

`verification/M1-test-report.json` memuat hasil aktual run final, versi runner, scope, dan batas. JUnit/log mentah disertakan. Angka **824 tes M0** dari laporan akun sebelumnya tidak dijumlahkan dengan tes M1. Tes parameterized memeriksa kombinasi clock, fps, speed, kurva, kegagalan dan pemulihan; keberhasilan proxy FFmpeg tidak dianggap bukti ASR/model atau aplikasi editor.

OpenCV dan pyCapCut native belum tersedia pada host QA ini. Tes yang membutuhkannya diberi alasan skip; tidak diganti modul palsu agar tampak lulus. Placeholder geometri historis dibatasi pada fixture-nya. Builder historis M0 diuji terhadap sumber M0 yang dibekukan, bukan berkas M1 masa depan. Installer M1 sendiri diuji terhadap payload M1 dan kedua dasar pemasangan yang diterima.

Untuk menjalankan ulang pada mesin Anda: hentikan server, masuk folder mesin, lalu jalankan `JALANKAN_UJI_M1.cmd` dari paket. Runner memakai `.venv` mesin, data sementara terisolasi dan folder laporan baru. Jika pytest belum tersedia, runner memberi petunjuk; ia tidak memasang dependensi diam-diam. Pengujian tidak memakai sumber/video pribadi Anda kecuali Anda sendiri menjalankan tugas render melalui UI.

Penerimaan berikutnya dapat memakai satu cuplikan pendek yang sudah ada di mesin: ejaan → pencarian efektif/asli → satu warna → diff/reset → draf kamera/audio → snapshot dua rasio → simpan → final → undo → CapCut. Tidak perlu mengirim ulang video panjang untuk menjalankan paket.

## Pemulihan

`PULIHKAN_M1_4_0_12.cmd` memulihkan kode dengan pemeriksaan hash. Proyek, sumber, video, model dan font pribadi tidak dihapus. Bila tidak ada edit source M1 lanjutan, database terbaru tetap aktif.

Jika proyek memakai timeline/keyframe/track yang tidak dikenali kode lama, rollback biasa ditolak sebelum perubahan. Pilihan eksplisit:

```
python complete_installer.py --target "C:\folder\mesin" --rollback --restore-project-state
```

Perintah tersebut mencadangkan SQLite terbaru sebagai `studio4-latest-before-rollback.sqlite3`, memverifikasi integritas, lalu mengaktifkan SQLite pra-upgrade dan memulihkan kode. Pekerjaan baru tetap utuh dalam checkpoint; sumber serta video tidak dihapus. Untuk mengaktifkan pekerjaan baru lagi, pasang kembali M1 lalu pulihkan checkpoint melalui prosedur backup/restore yang ditinjau. Jangan menukar database saat server/worker berjalan.

Flag UI untuk diagnosis: pada console browser, `localStorage.setItem('clipper-m1-inspector','legacy')`, lalu reload. Kembali ke inspector enam bagian dengan `localStorage.removeItem('clipper-m1-inspector')`. Flag ini tidak membatalkan edit source M1 atau mengubah proyek.

## Pemulihan kesalahan umum

| Pesan | Tindakan |
|---|---|
| Kode lokal berbeda | Simpan perubahan lokal; cocokkan versi dasar. Installer belum menimpa kode. |
| Revisi berubah | Draf tetap tersedia. Periksa Riwayat/diff; gunakan rebase hanya jika perubahan tidak bertabrakan. |
| JSON timeline/kurva belum valid | Perbaiki JSON atau buang hanya draf itu. Salinan draf tetap dapat diunduh. |
| Track terkunci | Buka kunci track sebelum mengubah isinya. |
| Decoder/OpenCV/FFmpeg belum tersedia | Periksa komponen inti dan environment mesin; kegagalan ini bukan penilaian AI terhadap video. |
| Kamera tidak mencakup rentang/sync perlu review | Periksa offset serta awal/tengah/akhir; sumber utama tetap tersedia. |
| Ilustrasi bertabrakan dengan reverse/ramp | Nonaktifkan scene itu atau pakai time edit biasa. |
| Native dasar tidak tersedia | Pilih hibrida; baca matriks layer baked/editable. |

Tidak ada klaim “tanpa bug”, seluruh 252 fitur selesai, lima pengguna usability lulus, GPU dipakai, atau typography profesional tercapai tanpa bukti pengujian yang sesuai.
