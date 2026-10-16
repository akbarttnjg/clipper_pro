# Clipper Pro 4.0.21 — kelanjutan M9

Paket kumulatif ini memuat M8 dan fondasi M9 4.0.20, lalu menambahkan dubbing
satu suara dengan tinjauan A/B serta konteks tulisan per klip/rentang. M9 belum
selesai seluruhnya. Rincian 45 kebutuhan berada di `M9_REQUIREMENTS.json`.

## Dasar pemasangan

Installer menerima kode M7 GitHub `f6f1f6a11631f800c1749f8cb6fbcae6dfff384d`,
M8 antara `2126a46bb5e7b7202d8626677fcf2dc93782638c`, atau payload 4.0.20
yang persis cocok dengan checksum paket sebelumnya. Main GitHub diperiksa
kembali melalui konektor GitHub saat kelanjutan ini dimulai; masih M7 f6f1f6a.
Tidak ada push GitHub pada pengerjaan ini. Perubahan lokal yang tidak dikenal
akan menghentikan pemasangan sebelum file ditimpa.

1. Simpan pekerjaan editor. Hentikan capture dan unggah seluruh chunk. Pada
   sesi rekaman yang belum final, gunakan **Jeda sesi**. Rekonsiliasi reservasi
   ComfyUI yang masih terbuka setelah provider benar-benar berhenti.
2. Hentikan antrean berat, worker M8, dan server Clipper. Tutup jendela mesin.
3. Ekstrak paket ke folder baru **di luar** folder mesin lama.
4. Jalankan `CEK_SEBELUM_UPGRADE.cmd`, masukkan folder mesin, dan pastikan lulus.
5. Jalankan `PASANG_M8_M9_4_0_21.cmd`. Backup kode dan checkpoint SQLite dibuat
   otomatis sebelum perubahan.
6. Buka mesin melalui `JALANKAN_PRO.cmd` yang sudah ada, lalu Ctrl+F5. Buka
   **Rekaman & studio M9 → Dubbing & tinjauan A/B**.
7. Jalankan `CEK_M8_M9_RUNTIME.cmd`. Probe memeriksa import/filter; hasil ini
   bukan bukti model neural, perangkat rekaman atau akun live sudah lolos.

Paket tidak mengubah media/proyek, model, font pribadi, `.env`, atau `.venv`.
Tidak ada unduhan model, API berbayar, login, unggahan platform, atau siaran
yang dijalankan oleh installer. NumPy dan FFmpeg memakai dependensi mesin
M6/M7 yang sudah ada. Piper dan model berlisensi harus disediakan sendiri.

## Dubbing dari terjemahan yang disetujui

1. Pada editor M2, buat/impor transkrip sumber, periksa bahasanya dan timing.
   Buat track terjemahan manual atau melalui antrean Ollama lokal. Periksa semua
   cue, angka, nama, negasi dan istilah/glossary, lalu setujui track.
2. Pada M9 **Model & kemampuan**, daftarkan Piper executable, `.onnx`, dan
   `.onnx.json` yang berdampingan. Cantumkan bahasa serta lisensi/izin. Bahasa
   terjemahan harus cocok dengan model; tidak ada fallback bahasa otomatis.
3. Pada **Dubbing & tinjauan A/B**, pilih proyek, lalu **Muat klip, terjemahan
   dan suara**. Pilih klip sumber, track disetujui, serta satu suara.
4. Buka rencana dan baca sumber/terjemahan tiap cue. Centang tiap cue dan dua
   pernyataan review fakta/hak. Mengganti pilihan membatalkan rencana lama.
5. **Buat kandidat dubbing**. Antrean serial yang sama mengerjakan Piper per
   cue dan FFmpeg. Periksa tugas, lalu **Buka hasil tugas dubbing terakhir**.
   ID kandidat dapat disimpan untuk dibuka kembali setelah menutup tab.
6. Dengarkan **A — audio asli** dan **B — suara terjemahan sintetis**, serta
   kandidat video. Periksa seluruh ucapan, jeda, nama, angka dan negasi.
7. Setelah puas, isi pernyataan dengar/timing/pengucapan dan tekan **Terima hasil
   ini dan buat proyek editor baru**. Tugas penerimaan memeriksa kembali SHA
   semua media dan revisi sumber. Proyek sumber tetap utuh.
8. Pilih proyek baru di editor dan lakukan analisis sumber sintetis secara
   eksplisit. Transkrip/word alignment sumber lama tidak dipindahkan sebagai
   bukti ucapan hasil sintetis.

Output kandidat meliputi video/audio sintetis, `original.wav`, `dubbed.wav`,
SRT terjemahan pada jam output, WAV tiap cue, manifest provenance dan ZIP
checksummed. Manifest menyimpan teks sumber/terjemahan, origin word IDs,
model/config/executable SHA, izin, review, kecepatan serta posisi sampel.
Persetujuan dengar tersimpan terpisah sebagai `listening-review.json`.

### Batas yang harus dipahami

- Rentang kontinu sumber 0,15–300 detik; 1–40 cue, masing-masing 0,15–60 detik;
  teks terjemahan total maksimal 12.000 karakter. Batas klip harus memuat cue
  utuh. Cue tidak boleh overlap dan seluruh ucapan pada rentang harus tercakup.
- Satu model suara untuk seluruh speaker. Tidak ada voice cloning atau lip-sync.
- Ini turunan sumber **sebelum** cut, speed, freeze, rasio, caption atau efek
  timeline editor. Hasil dapat diedit kembali sebagai proyek baru.
- Audio hasil hanya suara sintetis dan keheningan di antara cue. Musik/latar
  asli tidak dipertahankan. Audio asli tersedia sebagai pembanding A/B.
- Suara lebih pendek diberi ruang hening. Percepatan maksimum default 1,15×,
  dapat dipilih 1–1,25×. Ekor suara tidak dipotong untuk memaksa muat. Cue yang
  terlalu panjang ditolak; ringkas dan setujui ulang terjemahan/timing M2.
- Anggaran proses 900 detik, Piper maksimal 120 detik per cue, CPU dua thread.
  HDR ditolak. Ruang bebas minimal 1 GiB ditambah cadangan 2 MiB/detik klip.
- Tinjauan manusia adalah pernyataan eksplisit pengguna. Program tidak dapat
  membuktikan kualitas pengucapan hanya dari keberhasilan CLI atau metadata.
- Kualitas bahasa/model neural asli dan operasi Windows nyata masih memerlukan
  acceptance pada perangkat pengguna. Fixture uji berupa nada buatan, bukan
  bukti suara neural yang alami.

## Tulisan dari video panjang

Pada **Tulisan & narasi**, tekan **Muat klip untuk konteks video panjang**.
Pilih klip, atau isi awal/akhir pada detik sumber. Filter diterapkan sebelum
batas 30.000 unit transkrip/40.000 karakter; sumber panjang tidak lagi ditolak
karena bagian di luar klip. Unit transkrip yang menyentuh batas diikutkan
secara utuh beserta waktu asalnya, dan kebijakan ini tertulis di provenance.

Co-editor wajib memakai klip. Usulan hanya dapat diterapkan sebagai draft pada
klip dan rasio asal; target lain memerlukan usulan baru. Sumber tidak diubah
otomatis dan klaim tambahan tetap memerlukan review.

## Pulihkan versi lama

Hentikan mesin dahulu, lalu gunakan `PULIHKAN_M8_M9_4_0_21.cmd` dengan folder
backup yang dipilih. Pemulihan kode saja ditolak jika database memakai fitur
yang tidak dikenali versi tujuan, termasuk kandidat/tugas dubbing saat kembali
ke 4.0.20. Jika memang ingin kembali ke checkpoint sebelum upgrade, jalankan
rollback dengan `--restore-project-state`. SQLite terbaru disalin menjadi
`studio4-latest-before-rollback.sqlite3` sebelum checkpoint lama dipulihkan.
Proyek yang dibuat setelah checkpoint tidak muncul pada state lama; salinan
SQLite terbaru tetap tersedia. Media sumber dan model tidak dihapus.

## Pekerjaan M9 selanjutnya

Prioritas setelah rilis ini: acceptance Piper/Ollama dengan bahasa nyata dan
rekaman Windows, dubbing multi-voice/latar yang terpisah, pemulihan ucapan
berbasis teks, monitoring room/live buffer, serta adapter generatif khusus.
Multistream, lip-sync, gaze, avatar dan generasi video tetap belum tersedia.
G6 uji dengar asli M6 dan uji native CapCut/Resolve M7 tetap terbuka.
