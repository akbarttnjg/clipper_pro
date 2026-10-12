# Implementasi M0 — Clipper Studio 4.0.11

Baseline: `6682f0b4e633af6ca830e63754ac3d46fc100bbf` (4.0.10).
Hasil verifikasi akhir: **824 passed, 0 failed, 22 skipped** dari 846 kasus.
Seluruh **40 regresi khusus M0** lulus tanpa skip. Dua puluh dua skip memerlukan
fixture source historis 4.0.4/4.0.5; alasannya tidak berhubungan dengan hasil M0.
Dasar pekerjaan: laporan arsitektur terpadu 120 halaman, 252 kebutuhan fitur,
34 temuan audit, regresi X01–X06, dan rencana M0–M9 (59 paket kerja).

## Enam paket M0

| Paket | Perubahan | Bukti yang tersedia |
|---|---|---|
| M0.1 | Snapshot source publik, hash baseline, lingkungan/test storage terisolasi | fixture berprovenance, JUnit baseline, inventaris runtime |
| M0.2 | Fingerprint render/preview/export/report sama; snapshot enqueue immutable; expected revision atomik | uji invalidasi aktif, cache lintas revisi nonpixel, konflik SQLite |
| M0.3 | Confidence nullable, manual timing terlindungi, bounds/keep spans dua rasio dan undo atomik | X01, alignment manual vs otomatis, uji perpotongan kosong |
| M0.4 | Staging satu volume, set media/sidecar bertanda hash, receipt/exchange baru setiap publikasi, pointer dan status job satu commit | ENOSPC terkontrol, staging terputus, tamper, hasil lama identik byte |
| M0.5 | Decode audio/video penuh, fps/offset/durasi; coverage logical token beserta urutan/multiplicity; integral clear hold; critical facts | FFmpeg nyata, X02–X04, video truncation/fps salah, metrik negasi/angka/unit |
| M0.6 | Track audio doctor eksplisit, receipt requested/actual/fallback, model lokal saja, CAS cancel, lease/token fencing dan acknowledgement tree | dua audio berbeda, ASR kosong ditolak, CUDA required fixture, worker/proses anak nyata |

## Kontrak publikasi

1. Enqueue menyimpan snapshot proyek dan fingerprint efektif dalam transaksi
   yang memeriksa expected revision. Input snapshot tidak berubah setelah enqueue.
2. Worker membaca snapshot tersebut. Sumber, parameter, words, aset/font dan
   komponen aktif diperiksa kembali sebelum publikasi. Model alignment dan
   generation weights dipindai rekursif berdasarkan isi.
3. Render core ditulis pada staging di volume target; media lulus full decode,
   caption lulus kontrak plan, dan sidecar/receipt diberi manifest content hash.
4. Set publikasi baru menyertakan MP4, plan, ASS, SRT, QC, credits, audio,
   runtime receipt, exchange, dan publication receipt. Cache hit mempertahankan
   encode provenance sambil menulis requested revision dan exchange baru.
5. Rename menutup set. SQLite memeriksa owner, lease token, expiry, status
   running dan fingerprint sebelum pointer proyek, artefak dan status completed
   disimpan dalam satu transaksi. Set yang tidak berhasil dipublikasikan tidak
   menggantikan pointer lama.

`verify()` menolak perubahan anggota/manifest, traversal/symlink, anggota wajib
yang hilang dan JSON rusak. Recovery melaporkan staging yang tidak lengkap serta
sealed yang mungkin belum direferensikan; keputusan promosi tidak ditebak.

## Pembatalan dan pemulihan

Cancel queued memakai CAS dalam SQLite. Cancel running menjadi cancel_requested
sampai supervisor mengakui proses berhenti. Worker lama tidak dapat menulis ulang
status terminal atau mempublikasikan dengan lease yang telah diganti/habis.
Heartbeat dimiliki supervisor; worker anak tidak memperpanjang parent yang mati.
Eksekusi sinkron QA memiliki heartbeat hanya oleh owner asli.

Recovery lease expired melakukan fencing, mempertahankan slot serial saat tree
masih hidup, meminta termination, lalu force kill setelah batas tunggu. Status
interrupted baru diberikan setelah PID/birth token tidak menunjukkan proses
aktif. Launch yang belum tercatat PID-nya tidak memasuki tahap berat.

## Makna confidence dan QC

Confidence `null`/tidak tersedia berarti unknown. Ia tidak diganti menjadi 1.0
atau dihitung sebagai angka ketika menentukan penerimaan recheck. Unknown tidak
otomatis berarti subtitle salah. Informasi confidence tetap dapat ditinjau.
Timing manual tidak dipendekkan oleh cleanup dan tidak ditimpa alignment otomatis.
Score CTC minimal 0.001 adalah penolakan nilai numerik hampir nol, bukan ambang
akurasi bahasa yang telah dikalibrasi.

QC caption membedakan inspection completed, geometry passed, dan acceptance.
Token yang terulang/hilang/tertukar ditolak berdasarkan ID logical, bukan hanya
keanggotaan origin word. Clear hold menggabungkan interval opacity/blur/scale
yang memenuhi batas dan mengukur total serta interval terpanjang yang berurutan.
Raster contrast tetap **not_measured**; plan QC tidak membuktikan kontras piksel,
kualitas glyph atau kenyamanan gerak pada semua font/renderer.

Koreksi X04: renderer saat ini memegang keyframe per interval. Fixture titik
`(0,1),(.01,1),(1,0),(1.99,1),(2,1)` memberikan total clear 1.01 detik,
terpanjang 1.0 detik. Angka 0.0596 detik total / 0.0298 detik terpanjang berlaku
untuk interpolasi **linear** yang dinyatakan eksplisit, dan tidak dilabeli sebagai
hasil render ASS nyata. Fixture flash pendek terpisah ditolak oleh QC produksi.

## Baseline dan harness

Run baseline asli: 715 passed, 69 failed, 22 skipped. Lima puluh kegagalan berasal
dari fixture memakai default WORK_DIR absolut yang dibekukan saat import Config,
sehingga transcript ID tetap bertabrakan antar service. Fixture kini memberi
work/out relatif secara eksplisit; semantik storage produksi tidak diubah.

Mock lama diperbarui mengikuti argumen render `mode` dan import cv2 lazy. Label
backend semantic aktual tetap `local_e5`. Tes installer historis memakai source
beku agar modul masa depan tidak tercampur dalam overlay versi lama. Pemeriksaan
hash installer produksi tidak dilonggarkan untuk menerima kode lokal sembarang.

Satu perbaikan geometri legacy menggunakan envelope blur yang sama dengan
validator untuk clamp animasi. Source-word kosong tidak diperlakukan sebagai
bukti dua cerita identik. Metadata claim tidak dapat mengubah fakta footage asli.

## Batas bukti dan langkah berikutnya

Video uji dibuat oleh FFmpeg; transcript adalah fixture yang dilabeli sintetis.
Tidak ada klaim ASR, detektor neural, E5, CUDA atau native editor telah dijalankan
pada video asli pengguna. Regresi Windows/NTFS/taskkill, inference Indonesia pada
track pilihan, dan CapCut 4.7.0 masih memerlukan bukti pada laptop pengguna.
Resolve Free 18.6.6 teks/font mengikuti penundaan yang sudah diterima.

X06/pencarian teks koreksi tetap M1.4. Audit geometri menyeluruh dan inspeksi
raster berada di M5; laporan 252 fitur tetap utuh. Sesudah penerimaan M0 di target,
mulai M1.1 dengan penyimpanan transcript/display token dan kontrak revision yang
sekarang sudah dijaga. Rincian hasil run akhir ada dalam `docs/verification/m0/`.
