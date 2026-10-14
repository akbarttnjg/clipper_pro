# Laporan M5 — Clipper Pro 4.0.16

Rilis mengikuti halaman 50 arsitektur terpadu 120 halaman, SHA256 76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36. Dasar M4 dipulihkan byte-identik dari 77 payload paket terdahulu setelah pemeliharaan ruang kerja. Commit sumber M4 asli b5426a754f86259d9e53e82bb77df323a72b68c9; arsip terverifikasi SHA256 3b58497405282bb6f6e4d101a2abede36e8bdbbb5f3a8376f1571ba792d88f5d. Commit pemulihan lokal 66785504e80786ca097d54a28ef89302c12360ee bukan klaim unggahan baru ke GitHub.

## Hasil implementasi

- M5.1: schema ketat, nilai efektif dan asal layer, override per field, reset/undo, import font TTF/OTF, Unicode cmap, family/style/weight/digest, fallback nyata. Family/style ambigu dan glyph hilang ditolak.
- M5.2: frasa semantik dan unit angka/negasi, final ink sebelum placement, ukuran minimum pada layar kecil, envelope paint dan motion setiap keyframe, hold kontinu dengan interpolasi yang sama dengan renderer. Tidak menghapus teks untuk membuat layout lolos.
- M5.3: karaoke, emphasis, emoji, warna/label speaker yang disetujui, sensor mask+bleep dengan review kamus, area subtitle sumber dari OCR M4/manual, dua band bahasa dan SRT terpisah. Emphasis off juga diperbaiki pada jalur legacy.
- M5.4: enam template, preset dengan diff, builder terbatas tanpa kode, galeri pada video sumber, renderer ASS dan Pillow Raster lokal dari satu plan. Parity diuji melalui raster sebenarnya; Wajib Remotion M5 gagal jelas karena parity belum dibuktikan.
- M5.5: kit/sub-brand berversi dengan parent revision dipin, history, logo/anchor/opacity, title/intro/outro/lower-third terjadwal, kamus aman dan penerapan eksplisit, indeks aset/koleksi/pencarian metadata, cover dari hasil rasio aktif, paket kit portable dengan aset/lisensi/digest.
- M5.6: compositing gambar/video, diagram dari seluruh item/nilai kutipan, transisi cut/fade/blur/glitch di dalam layer, budget area/layer/cache/durasi, sumber M1 untuk reorder/reverse/freeze. Required ranker tidak boleh berpura-pura mendapat skor. Efek lengkap di luar subset inti tetap M9.

## Integrasi dan pelestarian

M5 juga mempertahankan jalur audiogram M2 dengan backend caption aktual, termasuk Raster. M5 opt-in per rasio. Dua varian bawaan tetap potret dan lanskap. Gaya tidak menjalankan ASR baru dan tidak mengubah signature kamera M4. Draf string per tab bertahan pada konflik revisi, input angka/JSON yang belum valid, dan reload; draf rusak tidak ditimpa. Queue memakai lease, cancel, dependency dan publikasi atomik. Galeri/cover tidak menggantikan final yang sudah ada. Font/layer terpilih ikut pembekuan ArtifactSet dan kredit/lisensi ekspor.

M4 geometry dipakai sebagai proteksi output; planner M5 tidak mengubah crop kamera untuk menyelesaikan konflik teks. Area manual tidak digeser diam-diam. Subtitle bakar hanya usulan geometri OCR terukur bila komponen siap; ketiadaan model bukan bukti tidak ada subtitle.

Installer kumulatif memeriksa seluruh hash payload/guard sebelum backup, mengenali baseline M2 publik yang diketahui serta M3/M4, mempertahankan .env/model/font pribadi/sumber/hasil/database, dan memiliki rollback terjaga. Source producer M4 dibekukan terpisah supaya uji historis tidak memaketkan kode M5 sebagai M4. Probe Windows di pengujian installer menggunakan double yang diberi label; ini tidak dinyatakan sebagai instalasi Windows nyata.

## Bukti dan batas penerimaan

Ringkasan angka final, JUnit, log UI, render dua rasio, uji parity raster, dan baseline install/rollback berada di folder verification dalam paket. Hasil uji lama yang sempat gagal selama pengembangan bukan bukti kelulusan; yang dipakai untuk ringkasan adalah hasil final sesudah koreksi.

Bukti media memakai FFmpeg/libass/Pillow nyata, dengan sumber, transkrip, warna/tone dan geometry yang dibuat untuk pengujian. Ini membuktikan eksekusi, waktu, coverage, ukuran, dan proteksi pada fixture tersebut. Sampel warna paint pada MP4 final juga diukur: foreground/outline yang tidak dapat dipisahkan dicatat sebagai null/perlu review, bukan skor nol. Scope ini tidak menyatakan semua latar bergerak atau bentuk huruf telah tersertifikasi. Bukti tersebut tidak membuktikan akurasi ASR/OCR/ASD/SAM, kualitas terjemahan, estetika TikTok profesional, atau kebenaran makna pada seluruh video asli pengguna.

G5 tetap pending corpus video asli dan review manusia dua rasio. G3/G4 corpus nyata dari tahap sebelumnya tetap pending; pekerjaan M5 dilanjutkan sesuai instruksi pengguna. Uji Windows/browser native, NVENC RTX3050, model lokal nyata, dan Remotion M5 belum dinyatakan lulus. CapCut native tidak ditulis ulang; DaVinci text tetap ditunda sesuai prioritas.

A05/A06 diuji melalui final ink/protected geometry/animasi dan raster. A07 diuji dengan emphasis off di legacy dan M5. AT06 memakai hold kontinu, bukan jarak endpoint kilatan; AT08 mempertahankan logical ID, angka, unit, negasi serta ukuran glyph. Penutupan G5 tetap memerlukan pemeriksaan sumber/plan asli dan pembacaan oleh manusia.

## Catatan untuk pengujian pengguna

Pilih satu sumber asli, gunakan preset Editorial dan render potret+lanskap. Bandingkan preview dengan final pada bagian yang sama. Kirim bila ingin dinilai: MP4 kedua rasio, edit-plan/readability/QC dari ArtifactSet, screenshot sembilan kelompok M5 (terutama font, area manual, template policy, backend), serta contoh target tipografi. Tidak perlu mengunduh ulang seluruh model atau me-render semua video besar untuk pemeriksaan awal.

## Hasil uji rilis final

Kode yang diuji: `f73f1064192ec685b6b19a9904c88f4cf4d6a72a`. Commit paket pada manifest juga mencakup pembaruan laporan ini; tidak ada perubahan kode setelah pengujian.

| Pemeriksaan | Hasil | Bukti |
| --- | --- | --- |
| Suite Python lengkap | 1.463 lulus, 61 dilewati, 0 gagal/error; 1.524 kasus terkumpul | `verification/regression-release.xml` dan log |
| Suite khusus M5 | 125 lulus, 0 gagal/error | `verification/m5-final.xml` dan log |
| UI | 14 suite DOM adapter lulus; M5 berisi 12 kelompok perilaku | `verification/ui/summary.json` dan log |
| Media nyata | ASS/Raster dua rasio, audiogram, cover, censor/bleep, source-clock dan transisi | Tes media dan `verification/media` |
| Parity 6 template × 2 rasio | Batas ink berbeda maksimal 2 px (toleransi 4); IoU mask minimum 0,6603 (batas 0,62); toleransi waktu satu frame | `verification/media/parity-summary.json` |
| Installer empat baseline | M2 GitHub terpin, M2 asli, M3, M4: preflight, install, reinstall idempoten, rollback byte-identik dan data pribadi/SQLite terjaga | `verification/baseline-installation.json` |

Jumlah suite khusus M5 sudah termasuk dalam suite lengkap, sehingga tidak boleh dijumlahkan. Kasus yang dilewati tetap tercatat di JUnit, bukan dinyatakan lulus. Browser native terblokir karena executable Chromium tidak tersedia. Probe native Windows/stopped memakai double yang ditandai; pemeriksaan salin berkas, hash, SQLite, dan rollback dijalankan sungguhan. Pengujian ulang paket final menambahkan pemeriksaan import modul yang benar-benar terpasang pada Linux.

Perubahan kompatibilitas terakhir juga menguji mute/solo track ilustrasi M1 untuk layer M5 dan pemulihan pilihan renderer/font legacy ketika M5 dimatikan, sambil mempertahankan pilihan M5 saat diaktifkan kembali. Tidak ada klaim lulus G5 estetika atau corpus sumber asli dari angka tes ini.
