# Clipper Pro 4.0.16.1 - Perbaikan kumulatif M0-M5

Paket ini menggabungkan 18 perbaikan M0-M4 dengan delapan temuan audit M5. Basis utamanya M5 4.0.16 GitHub `9dd8e73d11c8612a365d3ea96c59b969131307a2`. Anda tidak perlu memasang paket perbaikan M0-M4 terlebih dahulu. Fitur M3, M4 dan M5 ikut disertakan untuk dasar lebih lama yang terverifikasi.

## Mulai dari sini

1. Selesaikan atau batalkan antrean, lalu tutup server dengan **Ctrl+C** pada terminal mesin.
2. Ekstrak ZIP ini ke folder baru di luar folder Clipper yang sedang dipakai.
3. Jalankan **CEK_SEBELUM_UPGRADE.cmd**. Isi lokasi mesin lama yang berisi `app.py`, folder `clipper`, dan `.venv`. Contoh: `C:\AI\clipper`.
4. Jika pemeriksaan lulus, jalankan **PASANG_PERBAIKAN_4_0_16_1.cmd** dengan lokasi yang sama.
5. Jalankan **JALANKAN_PRO.cmd** dari folder mesin, kemudian **Ctrl+F5** pada browser. Header seharusnya menunjukkan **4.0.16.1 - Perbaikan M0-M5**.
6. Buka satu proyek uji, tinjau pengaturan dan draf yang dipulihkan, kemudian buat preview pada setiap rasio sebelum render final.

Installer memeriksa checksum kode sebelum menulis, mencadangkan kode dan SQLite, lalu memeriksa impor modul setelah pemasangan. Pemasangan ulang paket yang sama tidak mengulang perubahan. Jika ditemukan kode lokal yang tidak dikenal, pemasangan dihentikan sebelum penyalinan. Jangan menghapus berkas untuk memaksa pemeriksaan lulus dan jangan menyalin folder `payload` secara manual.

## Dasar yang didukung

Pemeriksaan mendukung dasar M0, M1, M2/Fix1, M3, M4 asli, M4 dengan perbaikan 4.0.15.1, serta M5 4.0.16 yang tercatat pada manifest. Pengujian instalasi menggunakan tujuh snapshot nyata yang dibekukan. Nama versi saja tidak cukup; checksum berkas harus cocok. Modifikasi lain pada mesin perlu digabungkan secara terpisah.

Paket ini tidak memasang dependensi dan tidak mengunduh model. Environment `.venv`, berkas `.env`, media sumber/hasil, model, serta font pribadi tetap dipertahankan. Arsip lokal `docs/releases/m0_fixture.zip` juga dipertahankan dan tidak menjadi prasyarat checksum upgrade ini.

## Perubahan yang terasa saat dipakai

- Perubahan caption, suara, ilustrasi dan kamera menghormati lock track yang memiliki field tersebut. Penerapan kit ke seluruh proyek diperiksa untuk semua tujuan sebelum mengubah dokumen.
- Draf saat penyimpanan berlangsung tetap tersimpan jika nilainya belum ikut dikirim. Draf yang tersisa memakai revisi hasil penyimpanan. Draf proyek lain dan perubahan setelah snapshot tetap tersedia.
- Transkrip JSON harus konsisten antara words/cues. Timing manual, speaker, ekspor, assembly dan rasio tambahan mengikuti kata efektif. Impor proyek/take/words dipublikasikan bersama dalam satu transaksi.
- Negasi dan angka tetap utuh sebagai unit makna, dengan batas pembicara dan asal sumber yang terjaga. Kata speaker berikutnya tidak mewarisi speaker pertama.
- Bleep hanya memakai waktu kata yang cocok dengan kamus yang disetujui. Untuk cue beberapa kata tanpa alignment kata, bleep sebagian cue ditolak: lakukan alignment/tinjau timing dahulu, atau gunakan mask teks.
- Diagram angka memerlukan label dengan nilai yang cocok pada kutipan sumber. `A 5 B 50` menerima A=5/B=50 dan menolak A=50/B=5. Kutipan ambigu, angka alternatif, atau hubungan yang tidak dapat dibuktikan harus diperjelas dahulu. Teks/angka tidak dihapus diam-diam.
- ASS memilih nama lengkap face font, sehingga Regular/Medium/SemiBold/Bold/Italic dalam family yang sama tetap berbeda. Font fallback dan font judul/diagram diperiksa dengan cmap sebenarnya; glyph yang tidak ada ditolak sebelum render. Font yang dipakai render disalin ke ArtifactSet.
- Safe area, head protection subjek terpilih, batas reverse, cache offset kamera, dan ruang ink/stroke caption mengikuti perbaikan M0-M4.

## Uji cepat pada mesin Anda

1. Buka draf lama. Pastikan cakupan koreksi dan format subtitle sesuai. Jika draf lama tidak menyimpan cakupan kata, pilih kembali cakupannya sebelum menyimpan.
2. Kunci illustration, lalu coba menerapkan kit dengan layer. Operasi harus ditolak sampai track dibuka. Kunci voice, lalu coba mengubah bleep: hasilnya juga harus ditolak. Warna caption biasa masih dapat diubah ketika voice terkunci.
3. Pada proyek uji, aktifkan M5 pada rasio yang diinginkan. Ubah warna dan simpan. Periksa bahwa rasio lain tidak ikut berubah kecuali dipilih.
4. Pilih font yang tersedia, render preview, dan periksa kata beraksen/fallback. Font custom tetap memerlukan asal, lisensi, dan izin penggunaan.
5. Pada contoh dua pembicara, periksa warna/label di batas pembicara. Dengarkan negasi, angka, satuan, dan kata di dekat bleep.
6. Render setiap rasio, periksa area aman, kepala, materi sumber, subtitle, suara, dan cover. Hasil lama dapat tetap tersedia tetapi render baru diperlukan untuk melihat perbaikannya.

Untuk suite otomatis, jalankan **JALANKAN_UJI_PERBAIKAN.cmd** pada environment uji. `pytest` dan dependensi tes opsional harus tersedia. Fixture font tambahan menggunakan FontTools bila terpasang. Uji browser membutuhkan Chromium/Playwright; paket ini tidak memasangnya.

## Rollback

Hentikan server, kemudian jalankan **PULIHKAN_PERBAIKAN_4_0_16_1.cmd**. Cadangan berada di `steezy_backups`; installer memilih cadangan aktif terakhir atau gunakan `--backup` untuk cadangan tertentu.

Rollback ke M5 mempertahankan data M5 yang masih kompatibel. Rollback ke M4/M3/M2 atau lebih lama ditolak bila proyek, registry aset/kit, atau antrean sudah memakai fitur milestone yang tidak dikenali kode lama. Jika memang perlu kembali beserta state sebelum upgrade, jalankan dari folder paket:

```bat
py -3 complete_installer.py --target "C:\AI\clipper" --rollback --restore-project-state
```

Pilihan ini mencadangkan SQLite terbaru sebagai `data/studio4-latest-before-rollback.sqlite3` pada cadangan upgrade, kemudian memulihkan state pra-upgrade. Perubahan proyek setelah upgrade tidak muncul pada state lama yang dipulihkan; checkpoint terbaru tetap tersedia untuk pemulihan terpisah. Media sumber, hasil render dan model tidak dihapus.

Jika pemulihan otomatis melaporkan `rollback_required`, simpan folder cadangan dan pesan kesalahan. Gunakan cadangan yang ditunjuk; jangan menimpa kode secara manual.

## Batas verifikasi

Status 26 temuan adalah diperbaiki dalam regresi yang tercatat. Ini belum merupakan kelulusan corpus asli G2/G3/G4/G5, kualitas makna/estetika seluruh video pengguna, Windows browser dua tab/zoom, RTX3050/NVENC, Remotion M5, atau kompatibilitas native CapCut/Resolve. Uji Linux dengan FFmpeg/ASS/raster dan snapshot installer dibedakan dari penerimaan pada laptop Anda. Lihat laporan serta bukti pada `verification`.
