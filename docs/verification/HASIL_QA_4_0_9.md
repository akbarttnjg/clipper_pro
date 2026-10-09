# Hasil pengujian 4.0.9

Sumber dasar: GitHub `8f6450c0d24aaf9e217a551ed7edcd0a6f1fd59c` dan
unggahan main `1a6bcb82801c83d7bc19e00a18e125deb6c85454`.

## Regresi

- 347 tes Python dan 11 subtes lulus pada Python 3.12 Linux dengan OpenCV
  sebenarnya. Suite mencakup perbaikan lengkap, batch dua rasio, typography,
  workflow/evidence, visual geometry, runtime queue dan installer.
- Tujuh modul UI diuji melalui adapter DOM. Ini bukan uji browser native.
  Uji browser foundation belum dijalankan karena executable Chromium tidak
  tersedia pada host QA.
- Empat pengujian tambahan memakai payload kode lengkap dasar 4.0.8:
  preflight, install, idempotence, backup SQLite, rollback, penolakan perubahan
  lokal, pemulihan setelah kegagalan impor, dan impor dependensi utama nyata.
- Ada peringatan deprecation FastAPI/Starlette pada lingkungan QA; tidak ada
  kegagalan tes. Versi dependensi aplikasi pengguna tidak diubah oleh paket.

Fixture dasar disimpan bersama kode pengujian, dengan provenance dan checksum;
pengujian tidak bergantung pada SHA commit lokal atau riwayat clone lengkap.

## Render dan model

Replay memakai bagian 13.5 detik yang utuh dari plate lama. Container lama
mengiklankan 14 detik tetapi hanya mempunyai 410 frame video, sehingga bagian
akhir yang terpotong tidak dipakai. Transkrip serta observasi wajah lama
dipakai kembali, statistik gambar diukur ulang, dan model MediaPipe resmi
menjalankan inference CPU pada tiga frame sumber. Rasio kedua menggunakan
cache hasil segmentasi yang sama, dengan pemeriksaan checksum mask.

| Pengukuran | 9:16 | 16:9 |
|---|---:|---:|
| Resolusi | 1080 × 1920 | 1920 × 1080 |
| Durasi | 13.5 detik | 13.5 detik |
| Tinggi kapital terkecil pada asumsi lebar layar 360 px | 20.67 px | 14.44 px |
| Posisi caption | Satu area stabil | Satu area stabil |
| Pita kosong yang dialokasikan | 0 | 0 |
| Benturan area penting/keluar frame pada caption QC | 0 | 0 |

Satu frasa cepat, “Pokoknya pengennya”, masih memperoleh peringatan waktu baca
pada kedua rasio. Peringatan dipertahankan untuk ditinjau, bukan dinyatakan lulus
secara estetika. Pemeriksaan media dan caption lulus pada kedua hasil.

MediaPipe 0.10.21 diuji menggunakan model enam kelas versi 1 dengan SHA-256
yang dikunci. Uji sampel frame abu-abu membuktikan inference dan validitas mask;
replay manusia membuktikan adapter dipanggil oleh pipeline, hasilnya digunakan
oleh placement, dan cache dipakai lintas rasio. Ini tidak mengukur akurasi setiap
frame atau kompatibilitas Windows pada perangkat pengguna.

Konstruksi dan struktur paket **CapCut** serta **Resolve** lulus menggunakan
serializer dan media sebenarnya. Status native tetap `not_tested`: editor
Windows tidak dijalankan di host ini. Bukti satu timeline pada paket gabungan
diuji agar tidak meloloskan klip/rasio lain.

## Operasi dan batas

Reproduksi worker waveform yang sama menurunkan jumlah pembacaan penuh sumber
untuk hash dari **7 menjadi 4**. Ini hitungan pembacaan Python pada jalur uji
tersebut, bukan pengukuran I/O fisik atau kecepatan laptop pengguna. Validasi
segar tetap dilakukan sebelum dan sesudah tahap berat serta saat publikasi.

Dua video terbaru pada chat akun lain tidak dapat diambil; kualitas pada
video tersebut belum diverifikasi. ASR/CTC Indonesia, YuNet/OCR baru pada video
mentah, Remotion/Motion Canvas native browser, impor/edit/reopen pada CapCut
9.5.0/Resolve 21.x, serta target waktu penuh 30 menit untuk sumber 1–2 jam
tetap perlu diukur di perangkat sasaran. Tidak ada klaim bahwa semua itu lulus.

Log, checksum, dua MP4 replay, caption plan, laporan media/audio dan bukti
uji model tersedia dalam folder `verification/` paket upgrade.
