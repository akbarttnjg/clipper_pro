# Perbaikan panel antrean 4.0.2a

Panel 4.0.2 hanya menggambar delapan pekerjaan terbaru. Saat banyak pemasangan
dimasukkan ke antrean, proses berjalan dan kegagalan sebelumnya tidak dapat
dijangkau. Pembaruan status juga mengganti seluruh baris pekerjaan.

Perbaikan ini menampilkan semua proses aktif dan maksimal 40 riwayat terakhir.
Proses berjalan tampil pertama, diikuti proses gagal/terhenti, antrean sesuai
urutan pemasangan, serta riwayat. Filter dan pencarian membantu memilih proses.
Header tetap tersedia saat isi digulir. Baris diperbarui tanpa mengganti tombol,
log, atau posisi gulir setiap kali status diperiksa.

Tombol **Batalkan proses aktif** hanya menyasar worker komponen yang berjalan.
Tombol **Batalkan antrean menunggu** hanya membatalkan pekerjaan yang belum
dimulai. Tindakan kedua dilakukan dalam transaksi yang sama dengan pengambilan
pekerjaan oleh worker. Pekerjaan selesai, data proyek, bobot, cache, dan data
unduhan parsial tidak dihapus oleh pembatalan.

Log mempunyai area gulir terpisah, diperbarui otomatis, serta dapat disalin atau
diunduh. Posisi pembaca dipertahankan jika sedang melihat bagian sebelumnya.
Log menampilkan hingga 100.000 byte terakhir, dengan kredensial disembunyikan.
Versi sebelumnya membatasi hasil log kembali menjadi 3.000 karakter.

## Mengakses log sebelum memasang perbaikan

Ekstrak paket, biarkan mesin lama berjalan, lalu jalankan
**KONTROL_ANTREAN.cmd**. Pilihan 2 membaca dan menyimpan log; pilihan 3
membatalkan satu proses yang dipilih. Alat ini memakai API lama yang sudah
tersedia dan tidak mengunduh dependensi atau model.

## Memasang perbaikan

1. Tutup terminal/server Clipper dengan Ctrl+C; tunggu terminal berhenti.
2. Jalankan **CEK_SEBELUM_PERBAIKAN.cmd** dan pilih folder mesin 4.0.2,
   misalnya `C:\AI\clipper`.
3. Jalankan **PASANG_PERBAIKAN_ANTREAN.cmd** dengan folder mesin yang sama.
4. Jalankan **JALANKAN_PRO.cmd** dari folder mesin, buka localhost:8765, dan
   tekan **Ctrl+F5**.
5. Buka **Komponen & perangkat**. Gunakan **Batalkan antrean menunggu** jika
   ingin menghentikan antrean tambahan, atau **Batalkan proses aktif** untuk
   worker yang sedang berjalan. Log tersedia pada tombol **Lihat log**.

Paket kecil ini memperbarui panel dan API pengelolaan antrean pada 4.0.2.
Tidak memasang ulang lingkungan utama atau model. Penghentian server saat
pemasangan dapat membuat job berjalan berstatus terhenti; rencana dan unduhan
parsial tetap tersedia. Antrean yang belum dibatalkan dapat berjalan kembali
saat mesin dihidupkan. Bobot medium dan small memakai rencana berbeda;
melanjutkan rencana lama tidak mengganti modelnya menjadi small.

Kode sebelum perbaikan dicadangkan otomatis. Untuk mengembalikan kode, tutup
mesin dan gunakan **PULIHKAN_PERBAIKAN_ANTREAN.cmd**. Pemulihan kode tidak
membatalkan/memulihkan status job yang sudah dipilih pengguna.

Uji regresi mencakup antrean melampaui batas riwayat, pembatalan menunggu yang
tidak menyentuh worker aktif, log panjang, redaksi kredensial, serta perilaku
panel dengan 30 pekerjaan. Adapter DOM digunakan untuk uji interaksi; tampilan
native Chrome/Windows dan model berat tetap memerlukan pemeriksaan di laptop.
Tahap 3 belum dikerjakan.
