# Laporan implementasi dan batas audit M8-M9 - 4.0.20

Tanggal laporan: 16 Oktober 2026. Dasar proyek adalah GitHub M7 `f6f1f6a11631f800c1749f8cb6fbcae6dfff384d`, dengan tree M7 yang telah diverifikasi. Kode M8 dipisahkan pada producer tetap `2126a46bb5e7b7202d8626677fcf2dc93782638c`; paket gabungan dibangun dari commit lokal penuh yang dicatat di manifest rilis. Kode tidak dipush dan tidak ada akun/post/broadcast dibuat selama pengerjaan ini.

## Keputusan penerimaan

Paket memuat M8 operasional lokal dan fondasi operasional M9 dengan adapter pilihan. **Seluruh milestone M8 maupun M9 belum dinyatakan lulus acceptance lengkap.** Status pada tracker mengacu perilaku implementasi, bukan janji mutu semua perangkat, bahasa, model atau platform.

| Modul | Lokal | Bersyarat | Sebagian | Terblokir/belum ada | Jumlah |
|---|---:|---:|---:|---:|---:|
| M8 | 26 | 8 | 9 | 1 | 44 |
| M9 | 7 | 9 | 18 | 11 | 45 |

Satu kebutuhan tidak diberi status lengkap hanya karena ada nama tombol, endpoint, manifest, atau fitur pembanding. Contohnya: unggahan tamu tersedia, tetapi WebRTC room belum; Piper CLI tersedia, tetapi voice cloning belum; full decode FX tersedia, tetapi mutu rambut/wajah/materi nyata belum terbukti.

Dasar normatif: `Arsitektur_Clipper_Pro_Terpadu_120_Halaman.pdf`, SHA256 `76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36`, terutama peta M8 halaman 54, M9 halaman 55 dan katalog kebutuhan. Rincian 89 ID disediakan pada `M8_REQUIREMENTS.json` dan `M9_REQUIREMENTS.json`.

## Perubahan penting M8

Enam paket M8 meliputi publishing/handoff, analytics, topic/feedback, automation, API/CLI/MCP, dan workspace/backup. Satu facade memeriksa peran dan project scope untuk jalur HTTP, CLI, Python dan MCP. Local mode membatasi peer loopback serta Host/Origin; mode server memakai bearer workspace dan menutup API lama untuk anggota jaringan.

Publishing membekukan revisi, M7 artifact, output SHA, profil akun, metadata dan jadwal. Approval hash diperiksa ulang sebelum mengirim. Resumable session disimpan terenkripsi sebelum byte; worker merekonsiliasi respons yang hilang dan menulis receipt tahan rollback sebelum percobaan upload. `handoff_ready`, `remote_scheduled`, `processing`, `published`, dan `needs_reconcile` mempunyai arti berbeda. ZIP handoff tidak disebut video yang telah terunggah.

Credential Windows memakai DPAPI user scope; non-Windows memakai AES-GCM dengan kunci eksternal. Raw token tidak masuk receipt command, event, diagnosis atau backup proyek. Google Desktop OAuth memakai loopback callback, state, PKCE dan timeout. Akun/role/proyek diperiksa lagi untuk replay receipt. Riwayat publikasi memblokir pemindahan workspace yang belum memiliki prosedur migrasi akun/history.

Analytics menyimpan provenance/period dan null reason. Watch folder berhenti pada review serta approval. Webhook mempunyai HMAC, retry/outbox, allowlist HTTPS dan DNS pin; plugin execution tidak diklaim aman/sandboxed jika belum mempunyai probe/isolation nyata. Backup proyek dapat di-restore sebagai clone dengan sumber/checksum, tanpa credential, sesi atau antrean publish diputar ulang.

Gap M8 utama: API Meta langsung, thumbnail/subtitle live, CMS vendor, tren otomatis, kalibrasi drop-off, training ranking otomatis, cloud sync, SSO, sandbox plugin tidak tepercaya dan penyediaan host selalu hidup. Uji YouTube live dan Windows DPAPI native tetap terbuka.

## Perubahan penting M9

### Recording dan pemulihan

Browser merekam layar/kamera/mikrofon/audio sistem terpisah, memakai izin eksplisit dan IndexedDB sebelum upload. Fragment besar dipecah sebagai byte, tidak dianggap file playable mandiri. Server memeriksa sequence/SHA/ukuran, menggunakan atomic replace dan fsync sebelum ACK. Upload ulang idempotent; sequence yang sama dengan isi/jam berbeda ditolak. Finalisasi memeriksa ulang daftar/versi track dalam transaksi agar race penambahan track atau perubahan offset tidak lolos.

Finalisasi berjalan di antrean berat serial yang sama dengan M0-M7, dalam proses worker terpisah. Semua fragment dirangkai sebelum remux/encode/full decode. Program, original track, manifest dan proyek editor diterbitkan dengan fence lease/revisi dan transaksi SQLite. Rekaman dapat dipulihkan sebagai prefix yang disebut parsial; data yang belum tersimpan tidak diklaim kembali.

Room tamu memakai capability hash/expiry/revocation yang hanya berlaku untuk track peserta/room terkait. Capability tidak dapat dipakai sebagai sesi workspace. Tamu berada backstage sampai interval onstage dibuka host. Audio program menonaktifkan tamu di luar interval; isolated originals tetap menyimpan backstage untuk host. Layout slide+camera memakai panel terpisah dengan fit/padding sehingga frame materi tidak dipotong.

Masih terbuka: native browser/device, quota browser, capture 1-2 jam, drift dan jaringan nyata; WebRTC monitoring/STUN/TURN; broadcast/multistream; buffer clipping saat capture. Rentang clipping rekaman final tersedia. Paket podcast WAV/chapters/notes/cover/stems terikat episode/revisi, tidak mengunggah episode otomatis.

### Kreatif dan provider lokal

Skrip/storyboard/copy merupakan draf sintetis terpisah. Ollama lokal mengembalikan referensi segmen/kata; co-editor dibatasi operasi tampilan/audio/timeline yang divalidasi editor inti. Apply tetap melalui review manusia dan revision guard. Tidak ada perubahan ucapan sumber dari instruksi model secara diam-diam.

Piper dipatok ke executable/model/config SHA, bahasa, lisensi, izin dan hash teks yang disetujui. Output WAV diperiksa sebelum menjadi proyek audio sintetis baru. ComfyUI dibatasi workflow text-to-image core nodes, checkpoint safetensors, ukuran/batch/steps/waktu/anggaran VRAM. Probe koneksi/node tidak diberi label inference berkualitas. Jika submission tidak pasti, resource hold persisten menghentikan tugas berat lain sampai provider terbukti idle dan direkonsiliasi. Tidak ada retry generatif otomatis yang berpotensi menggandakan inference.

CLI/HTTP provider diuji menggunakan fixture tone/PNG dan respons yang diberi label buatan. Bukti ini menilai protokol, izin, fingerprint, recovery dan publication; bukan performa atau mutu model neural. Model tidak disertakan, dipasang atau diunduh. Voice cloning, dubbing otomatis, lip-sync, gaze, avatar, video/fill/object generatif, musik generatif dan image animation belum mendapat adapter produksi. Impor media luar menyimpan label sintetis/provenance dan tidak diklaim inference Clipper.

### Efek dan reuse

M9 menambah salinan sumber untuk color EQ/curves/LUT, chroma, overlay, blur/mosaic ROI, denoise, upscale/interpolation, deshake/lens, fade dan static v360. Resep JSON tidak menerima filter arbitrary, perintah shell, path FFmpeg bebas, pan, atau hook tersembunyi. Sumber/revisi/hash/rentang, recipe dan output disimpan dalam manifest; sumber asli tetap utuh untuk A/B. Perubahan sumber/revisi, pembatalan atau lease hilang mencegah hasil diaktifkan.

Mask/overlay menolak area terlindungi; operasi geometri harus terakhir. Input HDR ditolak untuk jalur SDR, LUT diperiksa struktur dan SHA, upscale menjaga rasio, interpolasi mempunyai batas CPU/FPS/durasi. Full decode dan metadata diperiksa. Chroma diuji dengan piksel warna kunci/foreground/overlay, bukan sekadar exit code. Preset pack JSON v1 mempunyai lisensi, export/import dan batas aset.

Kinetic typography dan B-roll/split/crossfade menggunakan implementasi M4/M5 yang sudah ada. Pipeline render inti tetap 4.0.18-m7. Batas penting: tracking otomatis/feather mask, color wheels/HDR management, color match/relighting, neural enhancement, panorama keyframe, blend modes lengkap dan efek editor native belum tersedia. Hasil FX baked tidak disebut layer native yang dapat diedit pada editor target.

## Bukti pengujian

Hasil akhir mesin, JUnit dan status tiap pemeriksaan dimasukkan ke `HASIL_VERIFIKASI_M8_M9.json` serta arsip bukti QA. Angka pada JSON akhir menjadi acuan, bukan log percobaan yang sebelumnya gagal.

Pengujian mencakup kontrak/recovery M8, 13 skenario installer M8, backend adversarial, FFmpeg render M7 ke handoff, HTTP/CLI/MCP proses nyata, dan rangkaian tes M9. M9 mencakup capture fragment/restart/guest scope, worker subprocess tanpa proyek awal, suara backstage dengan analisis frekuensi, chroma/overlay pixel checks, mask/curves/LUT/interpolation, immutable source, stale/cancel fence, protocol provider, resource hold, serta pack round-trip.

Regresi pertama M8 menemukan 15 tes lama dengan Host/peer simulasi `testserver` yang ditolak kebijakan lokal baru. Fixture tes diubah ke loopback eksplisit; aturan akses produksi dipertahankan. Kelompok terkait kemudian lulus 246 kasus. Regresi final dijalankan ulang pada paket gabungan, bukan memakai angka lama tersebut sebagai bukti akhir.

Adapter DOM/Browser API memakai Blob/SHA nyata dan simulasi perangkat yang jelas. **Ini bukan native browser QA.** Pemeriksaan Linux installer menggunakan runtime yang tersedia; Windows `.cmd`, DPAPI/NVENC, perangkat RTX 3050 4 GiB serta model asli belum diuji di lingkungan ini. Skip historis dicatat dengan alasan, bukan dinyatakan pass. Peringatan deprecation dependensi dibedakan dari kegagalan tes.

## Risiko dan urutan penerimaan berikutnya

1. Pasang melalui installer pada salinan mesin M7; jalankan uji pendek lokal dan periksa backup/rollback.
2. Uji capture perangkat Anda, restart/putus jaringan, recovery dan drift awal-tengah-akhir sebelum rekaman panjang. Verifikasi kuota browser dan ruang disk.
3. Lakukan A/B FX pada ucapan, slide, papan/chart, wajah/rambut dan gerakan nyata. Dengarkan hasil program serta periksa backstage/isolated stem.
4. Pasang model lokal berlisensi dan ukur inference/VRAM aktual satu per satu. Terima per bahasa/tugas, bukan per nama backend.
5. Jika dibutuhkan, selesaikan RC05/RC06, WebRTC dan GN/FX yang masih terblokir melalui implementasi/probe terpisah; tidak cukup mengganti label status.
6. Teruskan penerimaan G6 real speech/Demucs dan G7 native CapCut 4.7.0/Resolve Free 18.6.6. EX05 text/font Resolve tetap backlog. Uji baru ini tidak menutup temuan lama tanpa bukti.

## Referensi teknis primer

- MDN, MediaRecorder `dataavailable` dan fragment timing: https://developer.mozilla.org/en-US/docs/Web/API/MediaRecorder/dataavailable_event
- MDN, MediaStream Recording API: https://developer.mozilla.org/en-US/docs/Web/API/MediaStream_Recording_API
- FFmpeg filter reference: https://ffmpeg.org/ffmpeg-filters.html
- ComfyUI self-hosted HTTP routes: https://docs.comfy.org/development/comfyui-server/comms_routes
- Piper CLI: https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/CLI.md
- Piper CLI argument source: https://github.com/OHF-Voice/piper1-gpl/blob/main/src/piper/__main__.py
- Referensi YouTube/OAuth/Analytics primer tambahan disertakan di laporan M8 internal.

Referensi dipakai untuk kontrak integrasi, bukan untuk menyatakan hasil benchmark pada perangkat Anda. Tracker JSON, source manifest dan bukti uji rilis menyediakan rantai verifikasi yang dapat ditinjau.
