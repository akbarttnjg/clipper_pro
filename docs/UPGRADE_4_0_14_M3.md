# Clipper Pro 4.0.14 — M3

Paket ini melanjutkan unggahan M2 GitHub `b8d12eb972b742a75379c39dc8fa7d35752b9e5e`. Enam paket M3 di halaman 48 arsitektur dihubungkan ke menu **Pilih**. Panduan ini juga berlaku pada M2 awal yang masih mempunyai masalah fixture installer; perbaikannya disertakan.

## Pasang

1. Ekstrak ZIP ke folder baru, **di luar folder mesin**.
2. Hentikan pekerjaan antrean. Tutup server lewat terminal dengan **Ctrl+C**.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`. Masukkan folder mesin lama, yaitu folder yang berisi `app.py`, `clipper`, dan `.venv`.
4. Setelah pemeriksaan lulus, jalankan `PASANG_M3_4_0_14.cmd` dengan folder yang sama.
5. Jalankan `JALANKAN_PRO.cmd` dari mesin lama. Tekan **Ctrl+F5** di browser. Header harus menampilkan **4.0.14 M3**.

Installer memeriksa hash sebelum menulis, mencadangkan kode dan SQLite, serta memulihkan kode jika penyalinan atau pemeriksaan sesudah pemasangan gagal. Video, hasil lama, model, `.env`, `.env.pro`, environment dan font pribadi tetap tersedia. Arsip lokal `docs/releases/m0_fixture.zip` tidak dibaca atau diganti. Jangan menyalin isi `payload` secara manual.

Tidak ada instalasi dependensi maupun unduhan model otomatis. M3 memakai Python/FFmpeg dan komponen yang telah tersedia. Jika kode lokal berbeda, daftar file tampil dan pemasangan berhenti sebelum menimpa file tersebut. Simpan perubahan lokal untuk dibandingkan dengan paket; jangan menghapus data atau mengubah hash agar pemeriksaan lewat.

## Pakai M3 pada proyek yang sudah ada

1. Buka proyek yang transkripnya sudah tersedia, lalu **Pilih → M3 · Pilih cerita dan momen**.
2. Isi instruksi, topik, jumlah, durasi dan rentang sumber. Pilih **AI lokal yang sudah Anda pilih** untuk proposal semantik dari Ollama.
3. Pilih pencarian **Otomatis · E5 jika tersedia**. Jika E5 belum tersedia, index teks digunakan dan jenis pencarian terlihat. Pilihan **E5 lokal wajib tersedia** berhenti jika model belum siap.
4. Klik **Cari / cari ulang tanpa ASR ulang**. Pantau antrean lalu klik **Muat hasil seleksi**. Hasil sebelumnya tetap tersedia selama proses baru berjalan.
5. Dengarkan **segmen, klaim, caveat, dan penutup** melalui tombol waktu sumber. Periksa angka, satuan, negasi dan urutan. Isi alasan, centang pemeriksaan yang benar-benar dilakukan, lalu **Terima kandidat** atau **Tolak kandidat**.
6. Setelah seluruh rekomendasi yang diinginkan diterima, klik **Gunakan rekomendasi yang diterima untuk render**. Kandidat alternatif dapat diterima dan diedit melalui **Edit klip yang diterima**. Susun set alternatif dari klip yang Anda pilih bila diperlukan.
7. Atur tata gaya, preview dan render melalui alur mesin yang sudah ada. Klip M3 mempunyai varian **portrait dan landscape**. Hasil proposal belum dihitung sebagai MP4 selesai.

Untuk proyek baru, kotak **Seleksi M3 setelah transkrip siap** aktif secara awal. ASR/koreksi berjalan dahulu; M3 masuk ke antrean berikutnya. Proyek lama mempertahankan alurnya sampai M3 dipilih secara eksplisit. Mode video utuh tetap mengikuti alur video utuh.

## Pengaturan untuk percobaan pertama

| Kontrol | Nilai awal yang disarankan |
|---|---|
| Pembuat proposal | AI lokal yang sudah Anda pilih |
| Pencarian | Otomatis · E5 jika tersedia |
| Profil | Sesuai sumber: Umum / Edukasi / Finansial / Podcast / Layar |
| Jumlah | 2 |
| Durasi | 30–120 detik, selama panjang sumber mencukupi |
| Rentang | Seluruh sumber terlebih dahulu |
| Teks | Teks sumber yang disetujui |
| Ukur gambar/suara | Aktif |
| Model pembacaan frame | Frame bukti saja; pilih VLM hanya jika komponennya sudah teruji |

Contoh instruksi: `Cari dua penjelasan yang bisa dipahami sendiri tentang pengelolaan modal. Sertakan alasan, syarat, risiko, dan kesimpulannya.` Isi topik terpisah bila membutuhkan cakupan, misalnya `modal, pengeluaran, risiko`. Frasa wajib mencocokkan frasa utuh; speaker memakai label transkrip/diarization yang telah Anda tinjau.

Jika Ollama belum berjalan atau model belum tersedia, kegagalan ditampilkan. **Aturan sumber · perlu penilaian manusia** merupakan pilihan eksplisit untuk memeriksa alur tanpa model tersebut. Index teks/rules tidak membuktikan pemahaman semantik setara model. Jika jumlah kurang atau suatu topik tidak terwakili, alasannya tetap terlihat; mesin tidak mengisi target dengan klip yang gagal pemeriksaan cerita.

## Gabungkan beberapa segmen

Centang **Tambahkan ke susunan cerita** sesuai urutan yang ingin digunakan. Pilih sedikitnya dua kandidat tanpa overlap, isi judul, lalu **Review gabungan kandidat terpilih**. Proposal gabungan tetap harus ditinjau dan diterima. Segmen memakai clock sumber yang sama untuk video, audio dan teks; tidak ada ucapan penghubung hasil karangan. Menyusun ulang urutan perlu pemeriksaan manusia agar maksud sumber tetap benar.

## Momen visual, suara, dan gaming

Tombol **Tandai momen saat ini (M)** mencatat waktu player sumber. Hotkey M diabaikan saat mengetik di formulir. Cue suara seperti `clip that` diambil dari unit transkrip tersimpan; waktunya tidak dikarang menjadi timing per kata jika sumber hanya memberi timing cue.

Energi suara diukur dari track sumber yang dipilih; perubahan frame berasal dari frame yang disampel. Keduanya merupakan petunjuk momen, bukan bukti emosi, kemenangan, atau kelengkapan cerita. Frame menyimpan waktu dan hash. Label objek memerlukan model visual lokal; bila model tidak dipakai, objek tetap kosong.

Profil gaming menerima nama game dan frasa HUD yang memang Anda gunakan. Pembacaan HUD memerlukan OCR lokal yang tersedia. **Belum ada game yang dinyatakan lulus corpus event gaming.** Uji masing-masing game secara terpisah sebelum mengandalkan deteksi otomatis. Sumber audio tidak diberi wajah/frame rekaan. Seleksi tanpa transkrip dapat menghasilkan proposal momen untuk ditinjau; mesin tidak melaporkannya sebagai ASR sukses.

## Draf, perubahan sumber, dan hasil lama

Draf query, alasan, checklist dan susunan cerita disimpan terpisah per tab. Saat revisi konflik, **Bandingkan revisi terbaru** dahulu. **Gunakan revisi terbaru untuk draf ini** mempertahankan teks draf dan mengganti basis revisi secara eksplisit. Byte draf yang rusak tetap dapat diunduh sebelum dibuang.

Perubahan teks/timing/speaker membuat hasil seleksi perlu diperiksa kembali. Pencarian ulang memakai transkrip dan index yang valid; tidak memanggil ASR. Perubahan isi file atau track suara memerlukan analisis sumber yang sesuai. Keputusan historis tidak diganti oleh skor baru. Klip M3 yang ditolak/usang tidak ikut final/batch.

## Uji setelah pemasangan

Anda dapat langsung mencoba satu sumber pendek. Buka Pilih, cari dua kandidat, periksa sumber, terima keduanya, preview kedua rasio, lalu render. Bukti pengujian paket tersedia di folder `verification`; batas pengujiannya dijelaskan dalam `LAPORAN_M3.md`.

`JALANKAN_UJI_M3.cmd` menjalankan seluruh pytest bila pytest sudah tersedia di environment mesin. Skrip tidak menginstalnya otomatis. Pengujian sampel model melalui pengelola komponen tetap terpisah. M3 tidak memerlukan unduhan baru hanya untuk membuka panel atau memakai index teks/rules.

## Pulihkan versi sebelum M3

Tutup server dahulu lalu jalankan `PULIHKAN_M3_4_0_14.cmd`. Jika proyek/antrean sudah menyimpan data M3, pemulihan kode saja ditolak agar data baru tidak dibaca oleh kode lama.

Untuk pemulihan state pra-upgrade yang disengaja, jalankan pada terminal folder paket:

```bat
py -3 complete_installer.py --rollback --restore-project-state --target "C:\AI\clipper"
```

SQLite terbaru dicadangkan sebagai `studio4-latest-before-rollback.sqlite3` sebelum state pra-upgrade dipulihkan. Pekerjaan M3 terbaru tetap berada dalam checkpoint tersebut. Index, video dan file kerja tidak dihapus. Font/typography, ekspor CapCut dan pembacaan teks DaVinci bukan fokus perubahan M3; penerimaan aplikasi native tetap perlu diuji pada mesin Anda.
