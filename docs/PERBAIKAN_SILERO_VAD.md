# Perbaikan dependensi Silero VAD — Clipper Studio 4.0.2a

Laporan 7 Oktober 2026 menunjukkan PySceneDetect, YuNet, dan RapidOCR sudah
lolos sampel. Silero gagal dengan `No module named 'numpy'`. Resep sebelumnya
memasang Silero, Torch, dan TorchAudio, tetapi uji ONNX di mesin juga membutuhkan
NumPy dan ONNX Runtime CPU. Paket ini melengkapi kedua dependensi tersebut.

Sumber resmi dependensi ONNX: https://github.com/snakers4/silero-vad/blob/master/pyproject.toml

## Cara menjalankan

1. Ekstrak seluruh ZIP perbaikan ke folder terpisah.
2. Pastikan antrean komponen kosong. Hentikan server mesin melalui Ctrl+C pada
   terminal dan tunggu sampai berhenti.
3. Klik `CEK_PERBAIKAN_SILERO.cmd`. Pilih folder mesin yang berisi `app.py`,
   biasanya `C:\AI\clipper`. Pemeriksaan ini tidak mengunduh atau mengubah data.
4. Klik `PERBAIKI_SILERO_VAD.cmd` dan pilih folder mesin yang sama. Internet
   diperlukan untuk paket yang belum tersedia. Unduhan memakai cache pip lama.
5. Jalankan `JALANKAN_PRO.cmd` dari folder mesin, lalu pilih **Perangkat uji CPU**
   dan klik **Uji sampel** pada Silero VAD. Gunakan sumber video dengan audio.
6. Ekspor laporan komponen sesudah uji selesai. Status sampel lama sengaja
   dipertahankan sampai uji audio baru benar-benar selesai.

Perbaikan menambahkan paket ke **lingkungan Silero yang sudah aktif**. Versi
seluruh paket lama dikunci dari `pip freeze`; Torch, TorchAudio, dan bobot model
tidak diminta untuk diunduh atau dipasang ulang. `.venv` utama, pointer generasi,
video, antrean, dan proyek tidak disentuh. Katalog pemasangan baru diperbarui
agar NumPy dan ONNX Runtime ikut dipasang pada generasi Silero berikutnya.

Receipt dan lock Silero diperbarui setelah paket lama terbukti tetap sama dan
inference ONNX CPU pada 512 sampel hening berhasil. Pemeriksaan hening tersebut
hanya memeriksa dependensi; bukan pengujian deteksi ucapan pada video pengguna.
Laporan perbaikan disimpan di `work/runtime/repairs/silero-vad/`, termasuk lock
sebelum/sesudah dan hasil pip. Jika konfigurasi memakai path lain, gunakan
`--runtime "D:\lokasi\runtime"` pada kedua perintah pemeriksaan/perbaikan.

Jika perbaikan terhenti, jalankan kembali `PERBAIKI_SILERO_VAD.cmd`. Paket yang
sudah terpasang dan cache akan dipakai kembali. Jangan memilih pemasangan
generasi Silero baru untuk mengatasi error ini.

`PULIHKAN_KODE_SILERO.cmd` memulihkan overlay kode terakhir dari cadangan setelah
server dihentikan. Pemulihan kode **tidak menghapus** dependensi yang ditambahkan
ke lingkungan Silero; keduanya diperlukan oleh uji ONNX.

## Hasil laporan dan batas pengujian

- 9 komponen terpasang; 7 lolos sampel; 0 berjalan dan 0 menunggu.
- PySceneDetect: pergantian adegan buatan terdeteksi.
- YuNet: inference pada gambar kosong berhasil; deteksi wajah/framing video
  pengguna belum dinilai.
- RapidOCR: teks buatan `Clipper 2026` terbaca; teks grafik video belum dinilai.
- WhisperX: transkripsi sampel berhasil di CPU setelah CUDA gagal memuat
  `cublas64_12.dll`. Alignment dan diarisasi belum diuji.
- OpusClip skill: dokumentasi diperiksa; layanan API belum diuji.

Label CUDA pada uji visual 4.0.2a mengikuti pilihan panel. Kode uji PySceneDetect,
YuNet, dan RapidOCR menggunakan CPU, sehingga label itu belum membuktikan
akselerasi GPU. Untuk uji selanjutnya pilih CPU. Perbaikan CUDA Windows terpisah.

Paket ini meneruskan perbaikan tahap 2. Tahap 3 dan DaVinci Resolve tetap ditunda.
Pengujian paket dilakukan dengan fixture lingkungan dan pemeriksaan runtime
yang tersedia di workspace. Inference Silero pada Windows pengguna perlu
dibuktikan dengan menjalankan paket ini dan uji audio selanjutnya.
