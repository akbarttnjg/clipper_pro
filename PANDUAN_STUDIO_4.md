# Clipper Studio 4 — gabungan A 01–22 dan B 23–43

Versi uji integrasi, 5 Oktober 2026. Mesin A kini tersambung ke penyimpanan, antrean, preview, render, dan antarmuka utama B. Daftar bukti serta pekerjaan verifikasi yang masih terbuka ada di `docs/handoff/B.md` dan folder `verification` dalam paket.

## Memasang pada Clipper yang sudah ada

1. Ekstrak seluruh ZIP upgrade ke folder tersendiri. Tutup server Clipper dengan Ctrl+C.
2. Jalankan `CEK_UPGRADE.cmd`, masukkan folder aplikasi yang berisi `app.py` dan folder `clipper`. Pemeriksaan ini tidak mengubah aplikasi.
3. Jika pemeriksaan berhasil, jalankan `PASANG_UPGRADE.cmd` dan pilih folder aplikasi yang sama. Dependensi tambahan dipasang pada `.venv` yang sudah ada. Dibutuhkan internet untuk paket Python yang belum tersedia.
4. Jalankan `CEK_PRO.cmd`, lalu `JALANKAN_PRO.cmd` **di folder aplikasi Anda**. Buka `http://localhost:8765`; tekan Ctrl+F5 jika tab lama masih terbuka.

Installer menerima Studio 3.3 asli, basis C0, paket A terakhir, dan pemasangan identik paket ini. Kode lain yang tidak dikenal akan ditolak sebelum penyalinan. Jangan memaksa menimpa konflik; bandingkan daftar file yang disebut agar perubahan lain tidak hilang. Opsi `--skip-deps` hanya untuk instalasi offline dengan seluruh dependensi yang diperlukan sudah tersedia.

Cadangan file yang diganti berada di `steezy_backups/<waktu>/`. `PULIHKAN_UPGRADE.cmd` memulihkan versi sebelumnya apabila file tersebut belum diubah lagi. Pemulihan ini mengembalikan kode, bukan paket Python yang telah dipasang. File kode baru yang ditambahkan paket akan dihapus saat pemulihan; database dan data runtime proyek tidak dihapus. Sesi JSON lama dipertahankan sebagai sumber pemulihan dan diimpor sekali ke database Studio 4.

Folder `payload` juga berisi kode aplikasi lengkap tanpa data pribadi. Untuk instalasi baru, salin isinya ke folder aplikasi baru dan jalankan `SETUP_STUDIO4.cmd`. Siapkan FFmpeg/ffprobe, Ollama beserta model pilihan, serta Python 3.10+ yang kompatibel dengan dependensi. Instalasi Windows dan NVENC perlu diperiksa di perangkat pengguna; pengujian rilis ini menggunakan Linux dan encode CPU.

## Cara memakai

**1. Sumber.** Pilih video atau isi lokasinya. Tentukan bahasa, jenis materi, track suara, dan istilah penting, misalnya `XAUUSD=hausd|xau usd`. Tekan **Analisis sumber**. Jumlah klip mengikuti cerita yang lolos pemeriksaan; tidak ada kewajiban menghasilkan 10 klip. Mengubah isi sumber atau track suara memerlukan analisis ulang.

**2. Pilih cerita.** Dengarkan pembuka/penutup, pilih **Edit klip ini**, atau gunakan **Cari pembahasan tambahan** untuk putaran pencarian baru. Klip manual tetap dapat ditambahkan. Jumlah kandidat bukan ukuran tunggal mutu; cerita yang sama tidak perlu diulang untuk memperbesar jumlah.

**3. Edit.** Pilih rasio 9:16 atau 16:9. Pemutar menyebutkan Sumber, Preview, atau Final serta revisi pembuatannya. Simpan koreksi sebelum menyiapkan preview. Kolom Asli mempertahankan hasil dengar; koreksi disimpan terpisah. Pilih cakupan satu klip atau ucapan yang sama pada klip terkait. Pengecualian manual di klip lain tetap dipertahankan.

Buka bagian pengaturan untuk membaca fungsi dan contoh efeknya. Resep gaya mengatur beberapa unsur sekaligus; opsi batch mempertahankan pengaturan manual kecuali Anda memilih menimpanya. Timeline memakai waktu sumber; rentang potongan yang dipertahankan dapat diubah di panel **Potongan & ritme**.

Di **Ilustrasi & bukti analisis**, siapkan ilustrasi dan periksa poster/video, asal aset, serta waktunya. Aset yang tersedia belum tentu dipakai: jadwal mencatat rentang aktual dan alasan dilewati. Anda dapat mengganti atau menonaktifkan aset. Setelah itu tekan **Preview cepat** atau **Preview detail** untuk melihatnya menyatu dengan klip. Preview cepat memakai sisi panjang 640 px, detail 1280 px; susunan potongan dan B-roll mengikuti jalur render final.

Posisi subtitle otomatis mempertimbangkan wajah, tulisan, dan materi yang berhasil dideteksi. Periksa hasilnya pada video asli: area penting yang gagal terdeteksi masih mungkin tertutup. Koreksi model dan OCR adalah bantuan tinjauan, bukan jaminan kata selalu benar. Angka, nama, dan negasi perlu perhatian khusus.

**4. Hasil.** Render masing-masing rasio lalu unduh MP4, SRT/ASS, kredit aset, atau paket editor. Hasil lama yang berasal dari pengaturan berbeda ditandai perlu diperbarui. Riwayat menampilkan perubahan, undo, dan perbandingan hasil yang masih tersimpan.

## Draf, proses terhenti, dan backup

- Jika dua tab mengubah proyek, simpan dari revisi lama ditolak. Draf tetap disimpan di browser. Muat revisi terbaru secara eksplisit, periksa perubahannya, lalu simpan kembali.
- Satu proses berat berjalan pada satu waktu. Antrean disimpan di disk. **Lanjutkan** mengulang tahap yang terhenti dengan cache sah yang tersedia; tidak melanjutkan tepat pada sampel audio/frame saat proses terputus.
- **Pemulihan & backup** membuat ZIP proyek beserta transkrip, koreksi, dan aset yang dirujuk. Video sumber dapat disertakan. Riwayat disertakan sebagai arsip; pemulihan membuat proyek baru.
- Sumber yang dipindah dapat ditautkan kembali jika isi identik. Sesi lama tanpa checksum sumber membutuhkan analisis ulang setelah ditautkan; hasil lama dipertahankan sebagai arsip.

## Folder dan tombol hapus cache

| Lokasi default | Isi | Pembersihan melalui UI |
|---|---|---|
| `work/studio4.sqlite3` | Proyek, kata asli, koreksi, revisi, antrean | Dilindungi |
| `work/<proyek>/cache/previews/` | Preview sementara dan data render preview | Dapat dipilih |
| `work/<proyek>/cache/canonical/` | Salinan media untuk menyamakan orientasi/waktu | Dilindungi |
| `work/<proyek>/` | Analisis, metadata, log proses | Dilindungi |
| `clips/<proyek>/video/` | Video final | Dilindungi |
| `clips/<proyek>/projects/` | Paket CapCut/Resolve | Dilindungi |
| `clips/<proyek>/backups/` | Cadangan proyek | Dilindungi |
| `uploads/` atau lokasi sumber Anda | Video asli | Dilindungi |

**Berkas & cache** memperlihatkan pemilik, jenis, ukuran, dan daftar pilihan sebelum penghapusan. Hanya cache preview milik aplikasi dapat dipilih. Tunggu antrean kosong sebelum membersihkan. Batas cache opsional menghapus preview yang paling lama digunakan saat antrean kosong. Jika beberapa proyek memberi batas positif berbeda, batas terkecil berlaku pada total cache preview. Gunakan tombol ini untuk membereskan preview; jangan menghapus folder `work` seluruhnya karena database dan koreksi ada di dalamnya.

## Status pengujian dan batas rilis

Catatan pengujian rilis awal 4.0 mencakup suite otomatis, uji dua tab browser, empat render media sintetis untuk dua rasio, geometri media, dan struktur ekspor. Untuk perubahan fondasi ekspor/revisi setelah rilis awal, baca [hasil pengujian dan batasnya](docs/studio4-foundation.md). Rekaman sintetis menguji integrasi teknis, bukan akurasi Whisper atau selera pemilihan cerita.

**B34 belum lulus impor native:** paket CapCut/DaVinci mempunyai laporan pemeriksaan struktur dan video referensi, tetapi belum dibuka pada aplikasi desktop tujuan. Efek tertentu tidak identik, terutama blur/fade teks; periksa `verification.json` dan `BACA_DULU.txt` dalam paket editor.

**B36 belum lulus benchmark video acuan:** alat pembanding WER/CER, istilah, negasi/angka, cakupan cerita, dan duplikasi tersedia. Penilaian manusia atas makna, tipografi, relevansi B-roll, serta waktu koreksi masih diperlukan. Belum ada dasar untuk menyatakan kualitas atau jumlah hasil setara Opus/Vizard.

Belum diverifikasi di perangkat pengguna: Windows/NVENC, suara asli dan model Whisper/Ollama, HDR/tone mapping, serta impor native CapCut/DaVinci. Gunakan satu sumber asli untuk uji penerimaan sebelum pekerjaan produksi dalam jumlah besar.

## Untuk pengembang

Basis 3.3: `b4772099c5591e8a83152a767ecb1004972b266b`; C0: `f67b03280774089f8f95ae8d94018377c4897b93`; A: `6d8c6dce97e77fd6b9be2e6ccc91132b05912d41`. Commit gabungan tercantum pada `manifest.json`. Paket berisi Git bundle sebagai alternatif integrasi dengan repository; jangan menerapkan bundle dan overlay dua kali pada pekerjaan yang sama.

```bash
python -m pytest -q
python -m clipper.tests.studio4_media_smoke --output /lokasi/uji-media
python -m clipper.tests.studio4_geometry_smoke --output /lokasi/uji-geometri
python -m clipper.benchmark acuan.json hasil.json --output laporan.json
```

Tes memerlukan `pytest` dan dependensi API pengujian selain requirements aplikasi. Uji media memerlukan FFmpeg/ffprobe. `studio4_ui_smoke.cjs` memakai Playwright dan server yang diarahkan ke folder uji media terpisah; jangan arahkan fixture ke proyek produksi. Jangan menjalankan browser/server pada port 8765 bersamaan dengan tes installer, karena installer memang menolak aplikasi yang masih berjalan.
