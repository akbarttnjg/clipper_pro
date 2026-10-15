# Laporan M6 · Clipper Pro 4.0.17

Tanggal: 15 Oktober 2026. Dasar: perbaikan M0–M5 4.0.16.1, GitHub `9681af5fdb4529e7da96212fbdc6bd48ef905dd4`. Lima paket M6.1–M6.5 mengikuti arsitektur 120 halaman, halaman 52, 63, 101–102; register AU01–AU15 tersedia pada `M6_REQUIREMENTS.json`. Gate G6 penerimaan suara asli belum dinyatakan lulus.

## Hasil yang tersedia

| Paket | Fungsi | Cara menilai |
|---|---|---|
| M6.1 · AU01/04/15 | Gain, normalisasi final on/off, EQ, compressor, limiter, meter WAV dan audio MP4 | LUFS/true peak, clipping, durasi dan hasil dengar |
| M6.2 · AU02/03/05 | FFT/NLmeans, hum 50/60 Hz, enhancement, WPE lokal; adapter Demucs opsional | Player A/B, sumber dan hasil terpisah; provenance model |
| M6.3 · AU06–08 | Musik lokal/stock milik pengguna, asal/izin/mood/durasi, ducking, loop crossfade, fade dan grid beat | Kata pelan, jeda, batas musik dan loop |
| M6.4 · AU09–11 | SFX editorial, voiceover, reaction, pitch dan dubbing dengan bahasa/speaker/gain/review | Track tersendiri, SFX off nol cue, source transcript tetap |
| M6.5 · AU12–14 | Usulan cleanup yang ditinjau, sambungan di jeda, audio-only/audiogram | Mapping audio-video M1 bersama, konteks dan sinkronisasi |

Panel M6 mempunyai delapan kelompok kontrol. Setelan opt-in per rasio; membuka panel tidak menyimpan atau merender otomatis. Menonaktifkan M6 menyimpan setelan agar dapat diaktifkan kembali. Draft menjaga angka belum lengkap, konflik revisi, perubahan saat save masih berjalan, dan draft antartab. Snapshot draft editor mengenali M6.

## Proses sebenarnya

Clock dan potongan M1 disiapkan dahulu; ucapan sumber sebelum proses disimpan. Pemisahan lokal opsional menghasilkan estimasi vokal dan accompaniment. Gain/restoration/EQ/compressor/pitch dan WPE menghasilkan file sesudah proses. Track narasi, musik dan SFX disejajarkan dalam sample 48 kHz. Musik mengikuti ucapan efektif dan interval narasi dengan attack/release.

Penggantian sumber hanya pada dubbing yang direview. Sensor M5 diterapkan pada seluruh stem tambahan sebelum penjumlahan, lalu bleep yang disetujui ditambahkan. **Normalisasi dua pass dan limiter berada setelah mix lengkap dan sensor.** Meter mengukur PCM master serta audio MP4 yang benar-benar diencode. Target tersimpan ketika off tidak dianggap target aktif.

Stem WAV berada pada clock output yang sama, diikat ke snapshot digest/revisi input. Stem menjumlah menjadi premaster; normalisasi dan limiter final nonlinear, sehingga master WAV menjadi acuan suara akhir. Raw source untuk A/B tetap tersedia; arsip stem hasil tidak mengembalikan ucapan yang disensor.

## Integrasi proyek

- Memakai revisi/CAS, history, scope, track lock dan mute/solo M0–M1. Pemeriksaan target lain selesai sebelum transaksi disimpan. Unmute/unsolo tidak menyimpan konfigurasi M6 yang mengaktifkan aset hilang.
- Track clock sumber mengikuti reverse, speed dan reorder; freeze menghasilkan keheningan. Narasi/dubbing tidak menulis ulang transkrip sumber atau terjemahan M2.
- Cleanup memakai timeline M1 untuk audio dan video bersama, dua rasio secara default. Proposal lama, clock rasio berbeda, track terkunci dan speed ramp yang belum ditinjau ditolak.
- Dependency mencakup byte aset dan seluruh isi repo model. Hasil stale/canceled tidak mengganti review/final sebelumnya. Pengecekan pada batas tahap; FFmpeg/model yang sedang berjalan dapat menyelesaikan tahapnya dahulu sebelum pembatalan terdeteksi.
- Audio job membuat A/B dan stem tanpa ASR ulang dan tanpa mengganti MP4 final. Render final menggunakan jalur M4/M5 dan artifact freeze bersama.
- Ekspor preserved menjaga MP4 identik. Hybrid/native M6 diblokir karena belum merekonstruksi master nonlinear secara identik; WAV stem terpisah tersedia. Format CapCut lama tidak ditulis ulang; teks Resolve tetap ditunda.

## Bukti pengujian

**98 tes M6 lulus**: 29 schema/clock, 7 DSP, 11 service/API, 16 safety/draft/cleanup, 24 media/FFmpeg dan 11 installer. **10 kelompok perilaku UI M6 lulus**. Regresi 16 suite DOM adapter lulus; dua script browser native tidak dapat berjalan tanpa executable Chromium. Uji gabungan installer/kontrak mencatat 31 lulus (termasuk 11 M6); uji installer lama M0–M2 mencatat 32 lulus dan 2 skip. Run terpisah saling overlap dan tidak boleh dijumlahkan. Angka/JUnit/log ada pada `verification/TEST_RESULTS.json`.

Tes mencakup schema/range/nonfinite, clock sample, reverse/speed/freeze, dubbing/review, lock kedua rasio, normalisasi off bit-identik, normalisasi mix dua target, puncak setelah gain besar, ducking kata pelan, seluruh jalur restoration lokal, sensor M5 sample-exact pada stem, MP4 dua rasio, audiogram dua rasio, queued audio, snapshot draft, dependency drift, pembatalan, serta installer/rollback dengan file dan SQLite nyata.

Smoke mix empat detik dengan target **−16 LUFS** terukur **−16,05 LUFS**, tanpa clipping, dengan 192.000 sample per channel pada 48 kHz. Ini sinyal sintetis, bukan penilaian ucapan manusia. Uji MP4 memeriksa decode, meter setelah encoding dan durasi audio-video dalam toleransi frame/AAC. Keselarasan makna tetap memerlukan video asli.

Installer diuji pada baseline frozen dari byte sumber GitHub yang diverifikasi: check tanpa mutasi, checksum payload, kode lokal berbeda, kerusakan payload, kegagalan copy/post-probe, idempotensi, pemulihan setiap byte kode, file pribadi dipertahankan, dan checkpoint SQLite sebelum downgrade M6. Probe dependensi native memakai double yang dinyatakan jelas; import modul M6 dari hasil instalasi Linux juga dijalankan sungguhan.

Regresi runtime luas mencatat **1.521 lulus, 35 skip, 2 tertahan lingkungan**, sebelum penambahan tes akhir M6. Yang tertahan: `test_frozen_aud06_fullhd_render_keeps_original_ids_and_qc` karena fixture arsip historis tidak tersedia; `test_actual_render_freezes_fallback_font_used_only_by_decoration` karena OpenCV native tidak tersedia dan tes warisan memasang stub. Assertion/checksum lama tidak diubah untuk memaksa lulus.

Tujuh fixture historis tidak dapat dimaterialisasi: `m0_m2_aud06_fixture.zip`, `m0_m2_repair_m2_fixture.zip`, `m0_m4_repair_m4_fixture.zip`, `m0_m5_repair_m4_fixed.zip`, `m0_m5_repair_m5.zip`, `m4_m3_producer.zip`, `m5_m4_producer.zip`. Semuanya bukan syarat runtime/pemasangan M6. Rangkaian installer historis M3–M5/perbaikan kumulatif tidak diklaim diuji ulang penuh. M6 mempunyai fixture baseline baru dengan provenance/checksum sendiri.

## Penerimaan yang masih pending

1. **G6 ucapan asli:** Indonesia/code-switch, angka, negasi, nama, konsonan, kata pelan, jeda bermakna, artefak denoise/WPE, dan sync awal/tengah/akhir. Tone sintetis tidak membuktikan ucapan manusia sempurna.
2. **Demucs:** adapter lokal, validasi model terpilih dan kegagalan tanpa download diuji. Inference runtime/bobot asli dan kualitas separation pending. Vocals merupakan estimasi; accompaniment = source − vocals. Tidak ada download model otomatis.
3. **Cleanup:** jeda adalah celah transkrip yang perlu didengar, bukan classifier silence akustik. Filler/retake konservatif tetap perlu konteks. Microfade di jeda dekat cut; ucapan tidak ditumpuk untuk memaksakan crossfade.
4. **Musik:** katalog aset lokal/stock yang telah dimiliki dan diberi metadata. Tidak ada API stock berlangganan. BPM/offset diisi pengguna; deteksi beat otomatis belum ditambahkan.
5. **Native/perangkat:** Windows, browser visual/zoom/two-tab, OpenCV native, GPU/NVENC, CapCut native dan kinerja perangkat tujuan belum dinyatakan lulus. DOM adapter bukan browser visual. Mix dibatasi 600 detik per klip untuk penggunaan memori.
6. **Generatif:** TTS/voice clone mengikuti M9. M6 menerima file narasi/dubbing terpisah. Pitch membutuhkan FFmpeg dengan Rubber Band.

Perilaku teknis E06 diverifikasi pada **M6 aktif**: target off tidak mengubah PCM, target on memengaruhi mix final, meter membaca output sebenarnya. Jalur legacy ketika M6 dinonaktifkan mengikuti mesin sebelumnya. Penerimaan dengar E06/G6 tetap pending.

## Rujukan

- Arsitektur pengguna: SHA-256 `76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36`.
- [FFmpeg filters resmi](https://ffmpeg.org/ffmpeg-filters.html): loudnorm, alimiter, afftdn, anlmdn, equalizer, compressor, rubberband.
- [Demucs resmi](https://github.com/facebookresearch/demucs): pretrained/repo/apply/audio; repo lokal eksplisit dan resampling convert_audio.
- [NARA-WPE](https://github.com/fgnt/nara_wpe): metode delayed linear prediction. Implementasi NumPy lokal M6 tidak mengklaim paritas penuh paket tersebut.
