# Clipper Pro 4.0.13 · M2

Paket ini menerapkan enam paket M2 dari halaman 47 arsitektur terpadu 120 halaman. Paket bersifat kumulatif atas M1 lengkap: editor, draft, riwayat, timeline bersama, dan perlindungan publikasi M0/M1 tetap dibawa.

## Pasang

**Paket Installer Fix 1** memperbaiki penolakan arsip pengujian lokal `docs/releases/m0_fixture.zip`. Arsip lama dipertahankan persis dan tidak diperiksa sebagai kode dasar. Jangan menghapusnya atau menyalin payload secara manual. Snapshot pengujian bawaan M2 memakai nama terpisah dan checksum sendiri. Baca `LAPORAN_AUDIT_INSTALLER_M2_FIX1.md` di folder paket.

1. Ekstrak ZIP ke folder baru di luar instalasi mesin.
2. Hentikan semua antrean, lalu tutup server dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`, masukkan folder mesin yang berisi `app.py`, `clipper`, dan `.venv`.
4. Jika pemeriksaan lulus, jalankan `PASANG_M2_4_0_13.cmd` dengan folder yang sama.
5. Jalankan `JALANKAN_PRO.cmd` dari mesin, kemudian Ctrl+F5 di browser. Header menjadi **4.0.13 M2**.

Dasar yang diterima: M0 GitHub b8c4ce2, M1 awal yang cocok dengan whitelist, M1 lengkap 3f6a8a1 termasuk unggahan GitHub main 4529c82, atau M2 awal 2df0ce5. Kode lokal yang berbeda ditolak sebelum ditimpa. Installer mencadangkan kode dan SQLite. Video, output, upload, environment, model, konfigurasi akun, dan font pribadi tidak diganti. Paket tidak mengunduh model/dependensi.

## Enam paket dan cara memakai

| Paket | Fitur yang terhubung | Cara mencoba |
|---|---|---|
| M2.1 | Audio/video lokal, metadata stream, VFR/HDR/rotation/SAR, subtitle sumber, proxy | Pilih WAV/MP3/FLAC atau video. Buka **Impor, bahasa & transkrip M2**. |
| M2.2 | Batch 1–50, URL/playlist/VOD, resume HTTP, monitor, konektor pilihan, multi-sumber | Panel **Impor beberapa sumber** pada Sumber. Kesalahan impor tampil per item. |
| M2.3 | Faster Whisper lokal, VAD tunggal, waktu jeda, receipt ASR | Pilih provider dan VAD, simpan, lalu **Jalankan ASR & analisis**. |
| M2.4 | Kamus/fakta, koreksi proyek/klip/rasio/frasa, waktu manual, confidence kritis | Periksa waveform dan kata; pilih cakupan; simpan teks atau waktu. |
| M2.5 | Alignment CPU lokal, timing lemah, speaker audio/manual, backend pilihan, matriks bahasa | Alignment tetap melalui panel timing M1; **Ukur speaker dari audio** memakai pipeline lokal. |
| M2.6 | Proposal terjemahan manual/Ollama, persetujuan semua cue/fakta, bilingual, 4 ekspor | Review terjemahan; setujui; pilih tampilan sumber/terjemahan/bilingual pada rasio aktif. |

### Subtitle impor dan subtitle creator

Pilih file SRT/VTT/JSON, nyatakan bahasa subtitle dan bahasa yang terdengar pada sumber. Periksa offset pada awal, tengah, dan akhir; centang pemeriksaan yang benar-benar Anda lakukan, lalu **Review subtitle**. Hanya proposal yang lolos dapat dipakai. Subtitle teks bawaan media juga dapat diambil dari pemilih stream. Subtitle gambar tidak dianggap sebagai teks.

Setiap cue SRT/VTT tetap satu unit timing cue. Tidak dibuat confidence ASR atau timing kata palsu. Cue overlap memerlukan review tambahan. Track lama tetap tersimpan dan penggantian pointer dapat di-undo. JSON menggunakan `schema_version:1`, `source_id`, `timebase:source_seconds`, `language`, dan `words`. Cue, speaker, metadata, serta probability null dipertahankan.

### Antrean, resume, folder dan channel

Impor lokal/URL menghasilkan proyek setelah media lengkap, ukuran/hash sesuai, dan probe sukses. ASR mempunyai antrean/status terpisah. Satu sumber gagal tidak menghentikan item berikutnya. **Lanjutkan impor** memakai rencana yang sama. HTTP resume memakai ETag kuat atau Last-Modified serta Range/If-Range; perubahan identitas atau respons 200 memulai ulang dengan aman. Partial tidak dianggap sumber lengkap.

Folder menunggu ukuran/mtime stabil sedikitnya 2 detik di antara scan. Histori dan deduplikasi tersimpan di SQLite. Profil analisis ikut menentukan identitas pekerjaan. Monitor channel mendukung filter judul/tanggal/channel dan histori; saat ini kepemilikan channel berupa **pernyataan pengguna**, belum verifikasi akun OAuth. IN10 tetap parsial untuk bagian OAuth.

Multi-sumber menerima JSON segmen `{project_id,revision,start,end}`. Gunakan daftar proyek untuk memperoleh ID/revision. Gabungan selalu proyek baru, seluruhnya audio atau seluruhnya video. Tiap kata/segmen membawa source/project/word ID asli dan mapping waktu; sumber semula dapat dibuka kembali. Segmen yang memotong kata memerlukan review.

### Komponen pilihan

Core lokal memakai environment mesin yang sudah tersedia. Untuk URL platform: pasang `yt-dlp` di environment mesin jika belum ada; format tertentu juga memakai FFmpeg. Cookie pilihan disediakan melalui `CLIPPER_YTDLP_COOKIE_FILE`, tidak dimasukkan paket.

Google Drive memakai `CLIPPER_DRIVE_ACCESS_TOKEN`; Zoom memakai `CLIPPER_ZOOM_ACCESS_TOKEN`. Adapter memeriksa identitas akun dan izin/rekaman selesai melalui API provider. Token disiapkan oleh Anda; login/OAuth terpadu belum dibundel. Receipt tidak menyimpan token. Pengujian akses akun hidup belum dilakukan.

ASR HTTP pilihan memakai `CLIPPER_ASR_ENDPOINT` (HTTPS atau localhost) dan, bila diperlukan, `CLIPPER_ASR_API_KEY`. Provider harus mengembalikan verbose JSON dengan timestamp kata. Confidence yang tidak dilaporkan tetap null; score segmen tidak diklaim sebagai probability kata. Provider remote tanpa model/device/generation yang dilaporkan tidak memperoleh receipt perangkat lokal.

WhisperX pilihan memerlukan generation/bobot ASR lokal yang cocok, Wav2Vec2 CTC lokal untuk bahasa sumber, serta repository Silero Torch yang telah di-cache saat instalasi/uji komponen. Adapter menolak unduhan otomatis ketika job berjalan. Alignment memakai CPU. Jika score rendah, timing perlu ditinjau. Ketersediaan model belum membuktikan bahasa/corpus tersebut akurat.

Diarization memakai pipeline YAML pyannote lokal beserta bobot lokal dalam environment core atau managed pyannote. Jika belum tersedia, pesan menyebut komponen/model yang dibutuhkan. Speaker audio, speaker manual, overlap, dan wajah aktif merupakan identitas berbeda.

### Koreksi, draf, dan waveform

Koreksi teks mempunyai empat cakupan: proyek, klip pada kedua rasio, rasio aktif, atau frasa pada rasio. Patch lebih spesifik menang atas patch yang sama pada scope lebih luas. Timestamp memakai detik sumber, menolak bounds negatif/terbalik/di luar media/klip dan overlap kata pada speaker yang sama. Speaker manual merupakan label kata sumber bersama; tidak mengenali wajah.

Draf dimiliki tab browser dan target proyek/klip/rasio. Nilai waktu yang diketik disimpan persis; konflik tidak menghapus kolom. Menyimpan satu kelompok hanya menghapus draf kelompok itu. Draf rusak tetap dapat diunduh sebelum dibuang. Untuk membandingkan revisi terbaru, buka ulang panel, periksa nilai sumber dan draf, kemudian terima revision terbaru secara eksplisit.

Jalankan **Ukur waveform**, tunggu job selesai, lalu buka ulang panel M2. Klik batang waveform atau **Dengarkan** di baris kata. Jeda VAD disimpan sebagai informasi; sumber audio tidak dipangkas otomatis berdasarkan noise. Edit manual timeline tetap eksplisit. Edit M1 speed/reverse/freeze pada audio dirender ke WAV dengan clock bersama; freeze/mute suara menjadi hening.

### Terjemahan dan render

Unduh JSON sumber, terjemahkan `cues` sambil menjaga cue_id/angka literal, lalu tempel JSON cue terjemahan manual. Alternatif: antrekan Ollama; setelah selesai tekan **Muat proposal antrean**. GPU mengikuti antrean mesin. Tidak ada inferensi Ollama langsung dari endpoint review.

Periksa semua cue dan setiap nama kandidat, negasi, angka/satuan yang ditandai. Track terjemahan disimpan terpisah setelah persetujuan. Perubahan teks/waktu sumber membuat terjemahan usang dan render meminta review ulang. Bahasa keluaran pada pengaturan adalah deklarasi tujuan; tidak mengubah ASR source menjadi terjemahan secara diam-diam.

Bilingual memakai dua pita terukur dengan coverage dan collision check terpisah. Pilih tampilan pada 9:16 dan 16:9 sesuai kebutuhan, lalu preview dan render. Sumber audio menghasilkan audiogram hanya pada tahap render; pipeline ASR tidak menggunakan video palsu atau deteksi wajah. Kedua rasio memakai audio dan clock sumber yang sama. Penilaian estetika tipografi pada video asli tetap perlu dilakukan setelah render.

TXT/JSON/SRT/VTT memakai source_seconds. Sidecar memuat track/revision/source, speaker, chapter, kata kritis dan lineage. Ekspor klip mencatat batas dan scope; ekspor JSON dapat diimpor kembali.

## Bukti dan batas pengujian

Baca `verification/test-summary.json`, JUnit, log regresi dan `M2_REQUIREMENTS.json`. Pengujian media menggunakan FFmpeg nyata, sumber sintetik yang dinyatakan jelas, SQLite, HTTP lokal dengan Range/validator, dan artefak final. Pengujian protokol ASR, pyannote/Ollama/cloud tertentu memakai double yang diberi label; tidak dihitung sebagai inferensi model nyata atau akses akun hidup. UI menggunakan DOM adapter; ini tidak menggantikan uji browser Windows/zoom/perangkat keras.

**Gerbang G2 belum diklaim lulus.** Perlu ucapan asli Indonesia bercampur istilah Inggris pada awal/tengah/akhir, model/generation aktual terpasang, review isi oleh pendengar, WER/timing/speaker error terhadap reference, dan bukti laptop Windows i5-12500H/RTX3050 4 GB. Matriks tanpa corpus selalu `not_tested`; score alignment dan confidence ASR bukan kepastian kebenaran. Peak RSS proses dapat direkam; peak GPU yang tidak terukur tetap null.

CapCut pada video yang sebelumnya bekerja perlu diuji ulang di versi pengguna. Pembenahan pengenalan teks DaVinci tetap ditunda sebagaimana permintaan Anda. Paket ini tidak menyatakan seluruh 252 persyaratan arsitektur selesai.

## Uji dan pemulihan

`JALANKAN_UJI_M2.cmd` menjalankan suite di environment mesin jika pytest sudah tersedia; tidak memasang pytest otomatis. Hasil baru tidak menimpa hasil lama.

Rollback: tutup server, jalankan `PULIHKAN_M2_4_0_13.cmd`. Jika proyek/antrean telah memakai data M2 atau edit lanjutan yang tidak dikenali kode lama, rollback kode saja ditolak. Pilihan `--restore-project-state` terlebih dahulu mencadangkan SQLite terbaru ke `studio4-latest-before-rollback.sqlite3`, lalu mengembalikan snapshot pra-upgrade. File sumber/output tidak dihapus. Baca lokasi cadangan pada output installer; jangan menyalin payload atau menghapus database secara manual.
