# Clipper Pro 4.0.15.1 - Perbaikan kumulatif M0-M4

Paket ini dibuat dari M4 4.0.15 yang sudah diunggah ke GitHub, commit `e6ed7006a67cf323b63eb943f3ff4924843e6e78`. Perbaikan M0-M2 lama **tidak perlu dipasang**. Satu pemasangan ini mencakup 13 perbaikan lama dan lima perbaikan baru M3-M4, dengan fitur M3/M4 tetap tersedia.

## Pemasangan

1. Unduh ZIP perbaikan dan cocokkan SHA-256 dengan berkas checksum yang diberikan. Ekstrak ke folder baru di luar folder mesin, misalnya `D:\Upgrade_Clipper_4_0_15_1`.
2. Selesaikan atau hentikan pekerjaan aktif. Tutup server Clipper dengan `Ctrl+C`; tutup jendela editor setelah menyimpan atau mengekspor draf penting.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`, lalu isi folder mesin Anda yang memuat `app.py` dan folder `clipper`. Pemeriksaan ini belum mengganti kode.
4. Setelah pemeriksaan lulus, jalankan `PASANG_PERBAIKAN_4_0_15_1.cmd` dan pilih folder mesin yang sama. Installer memeriksa hash kode, integritas payload, Python, FFmpeg, serta FFprobe; membuat cadangan kode dan snapshot SQLite; baru kemudian memasang perubahan.
5. Jalankan `JALANKAN_PRO.cmd` dari folder mesin. Tekan `Ctrl+F5` pada browser. Header harus menampilkan **4.0.15.1 - Perbaikan M0-M4**.
6. Buka proyek lama. Periksa transcript, timing, M3 dan kamera M4. Lakukan preview, lalu render uji pada rasio yang digunakan. Rilis ini mengganti signature timing/komposisi: kandidat M3 dan kamera M4 lama dapat menjadi usang dan perlu dianalisis serta diterima ulang. Riwayat lama tetap disimpan.

Contoh terminal, dari folder paket yang telah diekstrak:

```bat
py -3 complete_installer.py --target "D:\ClipperPro" --check
py -3 complete_installer.py --target "D:\ClipperPro"
```

Jangan menyalin isi `payload` secara manual. Jika kode lokal berbeda dari baseline yang dikenali, installer berhenti sebelum penggantian. Simpan modifikasi lokal untuk dibandingkan; jangan menghapus file hanya untuk melewati pemeriksaan. File historis `docs/releases/m0_fixture.zip` lokal tetap dipertahankan dan tidak dipakai sebagai syarat pemasangan.

## Yang diperbaiki

- Clock MKV menggunakan panjang konten, bukan penjumlahan origin dan durasi; offset kamera masuk ke identitas cache.
- JSON subtitle memiliki satu fakta untuk words/cues; assembly memetakan ulang nested alignment dan mempertahankan asal kata.
- Publikasi impor memakai transaksi dan identitas stabil; pembatalan, kegagalan, retry, dan resume tidak menerbitkan proyek ganda.
- Draf proyek, pilihan cakupan dan format ekspor bertahan saat pindah panel atau gagal simpan; konsumsi draf setelah commit hanya berlaku pada snapshot yang telah disimpan.
- Lock track berlaku pada field yang dimiliki track tersebut. Perintah kamera M4 juga memeriksa lock video; copy kamera memeriksa rasio tujuan.
- Keyframe yang dipulihkan mempertahankan atribut, dan pemetaan reverse pada batas slice tidak melompat ke slice berikutnya.
- Area teks memperhitungkan ink/stroke tanpa melonggarkan QC subtitle.
- Kandidat M3 dan kamera M4 memakai bounds alignment manual efektif serta membatalkan approval usang.
- Seluruh viewport M4 dan panel subtitle berada dalam safe area. Crop/keyframe yang menghilangkan kepala subjek pilihan ditolak.
- Timing M2 per rasio dapat disimpan untuk square, feed, dan custom yang benar-benar ada dalam clip.

## Sesudah upgrade

Untuk M3: analisis ulang seleksi bila teks, timing, atau speaker berubah. Periksa klaim, caveat, kesimpulan dan urutan sumber sebelum menerima kandidat. Skor mesin tidak menggantikan keputusan Anda.

Untuk M4: simpan pengaturan, analisis kamera, periksa speaker, materi/HUD, gerak, area aman dan urutan sumber; baru terima kamera. Periksa tiap rasio. Jika keyframe manual memotong kepala atau materi, perbaiki box dari sumber. Untuk mengubah kamera pada track video terkunci, buka lock video terlebih dahulu.

Rasio tambahan mempunyai draf dan koreksi masing-masing. Cakupan `variant` hanya mengubah rasio terpilih; cakupan `clip` atau `project` diperiksa terhadap seluruh lapisan timing turunannya agar tidak menimbulkan overlap pada rasio lain.

## Rollback dan data

Jalankan `PULIHKAN_PERBAIKAN_4_0_15_1.cmd`, atau:

```bat
py -3 complete_installer.py --target "D:\ClipperPro" --rollback
```

Rollback ke baseline M4 mempertahankan data M4 yang telah dibuat setelah upgrade; tidak perlu mengembalikan snapshot proyek pra-upgrade. Untuk kembali ke M3/M2/M1/M0 ketika sudah ada data milestone yang tidak dimengerti kode lama, rollback biasa berhenti. Jika Anda memilih mengembalikan state pra-upgrade, gunakan:

```bat
py -3 complete_installer.py --target "D:\ClipperPro" --rollback --restore-project-state
```

Mode tersebut mencadangkan database terbaru ke `steezy_backups\complete-...\data\studio4-latest-before-rollback.sqlite3` sebelum memulihkan snapshot pra-upgrade. Proyek/perubahan setelah upgrade tidak tampil pada kode lama, tetapi tetap tersedia dalam checkpoint terbaru. Pilih mode ini dengan memahami akibatnya; jangan mengganti SQLite secara manual.

Jika file kode diubah setelah pemasangan, rollback berhenti untuk mencegah modifikasi tersebut hilang. Semua file asli, payload dan cadangan diperiksa sebelum penggantian pertama. Pemasangan ulang payload yang sama bersifat idempoten.

## Pengujian dan batas penerimaan

Folder `verification` memuat JUnit, log pengujian, probe sebelum/sesudah, provenance sumber, pemeriksaan installer runtime, dan bukti render sintetis. `JALANKAN_UJI_PERBAIKAN.cmd` menjalankan suite pada mesin Anda bila pytest tersedia di environment uji.

Paket tidak mengunduh model dan tidak mengubah environment pribadi. Lulus tes kode tidak berarti akurasi ASR, diarization, pemilihan cerita, active speaker atau mask pada video asli sudah sempurna. G2, G3 dan G4 tetap memerlukan corpus asli, model nyata, review buta, serta Windows/browser/GPU laptop tujuan. Visual model yang tidak tersedia tetap memakai status/fallback yang jujur; CapCut/Resolve native dan provider/cloud live belum dinyatakan lulus.
