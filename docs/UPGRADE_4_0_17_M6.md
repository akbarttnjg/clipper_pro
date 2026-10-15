# Clipper Pro 4.0.17 · M6

Paket ini melanjutkan **perbaikan M0–M5 4.0.16.1** pada GitHub `9681af5fdb4529e7da96212fbdc6bd48ef905dd4`. Installer membandingkan isi kode; perubahan lokal yang tidak dikenal dihentikan sebelum penyalinan. Ini paket upgrade kode, bukan installer Python/model baru.

## Pasang

1. Ekstrak ZIP ke folder baru di luar folder mesin.
2. Selesaikan/batalkan antrean, lalu tutup server dengan Ctrl+C.
3. Jalankan **CEK_SEBELUM_UPGRADE.cmd**, masukkan folder mesin yang berisi `app.py`, `clipper`, dan `.venv`.
4. Setelah lulus, jalankan **PASANG_M6_4_0_17.cmd** dengan folder yang sama.
5. Jalankan `JALANKAN_PRO.cmd` dari mesin, lalu Ctrl+F5 di browser. Header menampilkan 4.0.17 M6.
6. Pilih proyek, klip dan rasio; buka **EDIT → Audio → M6 · Audio, musik dan mix**. Setelan M6 berlaku per rasio. Aktifkan M6 dan simpan secara eksplisit.

Kode dan database SQLite dicadangkan di `steezy_backups/complete-*`. Video sumber, hasil lama, `.env`, `.env.pro`, environment, font pribadi dan model dipertahankan. Paket tidak mengunduh musik, model, atau memasang dependensi. Jangan menyalin `payload` manual untuk melewati pemeriksaan.

## Mulai dengan setelan ringan

| Kontrol | Awal yang disarankan | Kegunaan |
|---|---|---|
| Normalisasi mix final | Aktif; −16 LUFS | Menyamakan mix setelah seluruh track dan sensor |
| Limiter | Aktif; −1,5 dBTP | Menahan puncak; tersedia terpisah dari normalisasi |
| Gain sumber | 0 dB | Pertahankan dahulu sebelum mendengar A/B |
| Denoise | Nonaktif; coba FFT 6–8 dB bila perlu | Hindari pemrosesan berat pada suara bersih |
| Hum | Nonaktif | Pilih 50/60 Hz hanya jika dengung memang terdengar |
| Enhancement, WPE, compressor, pitch | Nonaktif | Aktifkan satu per satu dan bandingkan suara |
| Ducking | Aktif; −14 dB, attack 80 ms, release 350 ms | Menurunkan musik selama ucapan efektif |
| Musik tambahan | Mulai gain −24 dB | Naikkan setelah mendengar kata pelan |
| Microfade sambungan | 5 ms | Hanya pada jeda yang terukur di dekat cut |
| Ekspor stem WAV | Aktif | Menyimpan master dan track pada clock output yang sama |

Mix M6 maksimal 600 detik per klip; video sumber dapat lebih panjang. Nilai ini titik awal untuk penilaian dengar, bukan janji hasil terbaik untuk semua rekaman. Ketika normalisasi off, target LUFS tersimpan tetapi tidak mengubah PCM. Limiter masih dapat aktif secara mandiri. Meter membaca WAV master dan audio MP4 hasil encoding; sumber yang sunyi/terlalu pendek ditandai, tidak diberi angka LUFS palsu.

## Aset dan track

Daftarkan file lokal pada bagian aset, isi asal, lisensi/izin dan mood/tag. Pencarian tersedia menurut teks/tag serta durasi; tidak ada pencarian atau unduhan stock jarak jauh. Musik stock yang sudah Anda miliki dapat didaftarkan sebagai aset lokal.

Tambahkan track dan pilih peran **music / sfx / voiceover / reaction / dubbing**, lalu aset, mulai/akhir, gain dan fade. Clock **Output** mengikuti waktu video hasil edit. Clock **Sumber** mengikuti mapping M1 termasuk reverse/speed/reorder; freeze tidak menyalakan ulang audio. Snap beat memakai BPM dan offset yang diisi pengguna, bukan deteksi beat otomatis. Loop musik memakai crossfade nyata di sambungan.

Dubbing memerlukan bahasa, ID speaker dan review. Penggantian sumber hanya berlaku pada interval dubbing yang disetujui. Mesin tidak menulis ulang transkrip sumber dan tidak membuat TTS/voice clone pada M6. Kontrol pitch memakai Rubber Band FFmpeg bila build FFmpeg menyediakan filter itu. Mute/solo/lock M1 tetap berlaku; semua SFX off menghasilkan nol cue. Cue SFX di atas angka/negasi memerlukan review.

## Cleanup dan sumber asli

Usulan filler, jeda dan pengulangan belum mengubah video. **Jeda berasal dari celah waktu transkrip, bukan bukti rekaman benar-benar sunyi.** Dengarkan konteks, pilih usulan lalu centang persetujuan. Cleanup mengubah audio dan video melalui timeline M1 untuk kedua rasio secara default. Jika dua rasio sudah punya potongan editorial berbeda, tinjau terpisah; snapshot lama ditolak.

Negasi/angka tidak diusulkan sebagai retake berulang. Keputusan akhir tetap pada pengguna. Speed ramp yang berpotongan dengan cleanup perlu diedit manual agar kurva waktunya terjaga. Riwayat sebelum edit dan sumber asli dipertahankan. Microfade tidak menumpuk ucapan antarklip atau mengubah durasi; fade hanya ditempatkan pada jeda terukur di dekat cut.

## Demucs opsional

Fitur lain dapat dipakai tanpa Demucs. Pemisahan membutuhkan runtime `demucs` beserta PyTorch/audio yang cocok pada environment mesin dan **repo bobot lokal lengkap**. Pilih folder berisi YAML model, misalnya `htdemucs.yaml`, beserta semua `.th` yang dirujuknya; atau pilih nama signature satu model `.th`. Bobot berbeda tidak dianggap sebagai model terpilih. Tidak ada fallback ke repo remote atau unduhan otomatis.

Hasil vokal merupakan estimasi, accompaniment dihitung sebagai sumber dikurangi estimasi vokal. Sumber sebelum proses, hasil, identitas bobot dan provenance disimpan terpisah. Inference model asli belum diuji pada lingkungan pembuat paket ini. Dengarkan kebocoran musik, konsonan, angka dan kata pelan sebelum menerima.

## Sesudah pemasangan: uji kecil dahulu

1. Gunakan satu klip 15–30 detik dari rekaman asli berisi ucapan pelan, angka/negasi dan satu cut. Simpan setelan M6 pada rasio pertama.
2. Buat **A/B 8 detik**. Bandingkan sebelum, sesudah proses, dan mix final pada player yang sama. Antrean audio tidak mengganti MP4 final lama atau menjalankan ulang ASR.
3. Jika ada musik, pastikan kata pelan tetap jelas, attack/release tidak memompa dan loop tidak klik. Coba normalisasi off/on; simpan sebelum mengantrekan lagi.
4. Render kedua rasio. Dengar dan lihat sinkronisasi awal, tengah, akhir; periksa hasil MP4 final pada panel meter.
5. Kirim screenshot delapan kelompok kontrol M6, hasil meter final tiap rasio, log job jika gagal, dan potongan hasil 15–30 detik. Untuk penilaian cleanup, sertakan konteks sebelum dan sesudah cut. Tidak perlu mengirim seluruh video besar.

`JALANKAN_UJI_M6.cmd` menjalankan tes M6 jika pytest tersedia di environment uji. Bukti paket membedakan tes media sintetis, DOM adapter dan uji native; tes otomatis tidak menggantikan uji dengar G6 pada video asli.

## Ekspor dan pemulihan

Pilih ekspor **Tampilan terjaga** untuk menjaga suara dan gambar MP4 final. Unduh ZIP stem dari panel M6 untuk track WAV terpisah. Stem menjumlah menjadi premaster; normalisasi/limiter master nonlinear, sehingga `master.wav` menjadi acuan suara akhir. Hybrid/native M6 diblokir agar tidak mengaku identik dengan master. Format CapCut lama tidak ditulis ulang; teks Resolve tetap ditunda.

Untuk kembali ke versi sebelumnya, tutup server lalu jalankan `PULIHKAN_M6_4_0_17.cmd`. Jika proyek/antrean sudah memakai data M6, installer meminta pemulihan state secara eksplisit:

```text
PULIHKAN_M6_4_0_17.cmd --restore-project-state
```

Opsi ini membuat checkpoint SQLite terbaru dahulu, lalu mengembalikan kode dan state pra-upgrade. Pekerjaan sesudah upgrade tersedia pada `data/studio4-latest-before-rollback.sqlite3` di folder cadangan; jangan hapus checkpoint itu. Pemulihan tanpa data M6 mempertahankan perubahan proyek M0–M5 yang masih kompatibel.
