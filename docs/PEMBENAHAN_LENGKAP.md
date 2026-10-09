# Clipper Studio 4.0.8 — Pembenahan Lengkap

Paket ini melaksanakan pembenahan kode tahap 2–7 sekaligus, di atas tahap 1 versi 4.0.7. Dasar GitHub: `9e0677c60605be0d16a6f19eebf8cb12094a3531`. Pemeriksaan 53 file dasar tersedia di `docs/verification/BASELINE_GITHUB_4_0_7.json`. Pembaruan tidak mengunduh model atau mengganti driver/CUDA.

Paket revisi juga menerima unggahan 4.0.8 yang telah diperiksa pada commit `1a6bcb82801c83d7bc19e00a18e125deb6c85454`. Revisi memperbaiki diagram daftar yang memotong poin kelima atau membuang kalimat pembatas. Render/preview dengan diagram ditandai perlu dibuat ulang; analisis sumber dan render dengan ilustrasi dimatikan tetap dapat digunakan kembali. Jika 4.0.8 sudah terpasang, tidak perlu mengulang pemasangan model.

## Pemasangan

1. Ekstrak ZIP ke folder baru, misalnya `C:\AI\pembenahan-lengkap`. Hentikan antrean dan server Clipper dengan Ctrl+C.
2. Jalankan `CEK_SEBELUM_UPGRADE.cmd`. Pilih `C:\AI\clipper`, atau gunakan `--target "C:\AI\clipper"` dari terminal. Target harus berisi `app.py` dan `.venv` mesin Anda.
3. Jika pemeriksaan lulus, jalankan `PASANG_PEMBENAHAN_LENGKAP.cmd` dengan target yang sama. Pemasang memeriksa seluruh payload sebelum menyalin, mencadangkan kode dan database SQLite, lalu memeriksa impor modul baru.
4. Jalankan `JALANKAN_PRO.cmd` dari mesin. Tekan Ctrl+F5 pada browser; header harus menunjukkan 4.0.8.
5. Buka **Periksa / ekspor → Seluruh klip · dua rasio**. Pilih klip yang layak. Untuk mengganti gaya lama, pilih Adaptif atau Rapi lalu tekan **Terapkan preset pada seluruh pilihan**. Tombol ini menerapkan DM Sans + DM Serif, perlindungan kontras, penekanan makna dan gerak terbatas pada kedua rasio.
6. Klik **Render seluruh pilihan · 9:16 + 16:9**. Satu pekerjaan berat berjalan pada satu waktu. Final yang masih sesuai diperiksa dan digunakan kembali.
7. Setelah kedua rasio seluruh pilihan siap, klik **Buat satu paket seluruh pilihan**. Pilih Hibrida untuk caption/audio terpisah, atau Tampilan terjaga untuk menyalin MP4 final. Paket tidak melewatkan rasio yang belum tersedia.

Gaya lama tidak diganti saat pemasangan; penerapan preset merupakan tindakan eksplisit di UI. Koreksi ucapan, angka, negasi, timing manual dan potongan tetap tersimpan. Final lama ditandai perlu diperbarui karena keputusan render berubah.

Jika kode lokal berbeda dari dasar yang dikenal, pemasang menolak sebelum menyalin. Simpan perubahan di Git dan bandingkan daftar file yang dilaporkan dengan payload. Jangan mengatasinya dengan menyalin seluruh folder manual. `PULIHKAN_PEMBENAHAN_LENGKAP.cmd` mengembalikan kode dan menjaga edit proyek setelah upgrade; salinan database sebelum upgrade tersedia terpisah.

## Perubahan dalam seluruh tahap

| Tahap | Masalah sebelumnya | Perubahan |
|---|---|---|
| 2 — framing | Tekstur latar dianggap tulisan/materi sehingga pembicara mengecil | Klasifikasi satu pembicara mendahulukan bukti wajah. Geometri tanpa teks terverifikasi menjadi diagnostik; OCR/materi/area manual tetap dilindungi. |
| 2 — jenis sumber | Pilihan manual ditimpa klasifikasi otomatis | Pembicara/Papan/Layar/Grafik manual mengunci jenis adegan. |
| 2 — ruang teks | Strip dibuat sebelum panel alternatif dicoba | Grid adaptif dicoba dahulu; strip fallback melakukan crop ulang sesuai rasio area gambar. |
| 2 — kamera | Zoom memotong kepala atau terlalu rapat antarshot | Kepala pada pembesaran maksimum diperiksa; jarak zoom berlaku lintas shot; crop dikunci selama shot. |
| 3 — duplikasi | Footage sama lolos karena judul/kutipan berbeda | Ucapan dan fakta aktual diperiksa terlebih dahulu. Angka/negasi berbeda tidak disamakan. |
| 3 — batas cerita | Daftar yang menjanjikan beberapa butir berhenti terlalu awal | Penanda daftar belum lengkap masuk tinjauan batas; kelanjutan tidak dikarang. |
| 4 — pilihan gaya | Preset menimpa template manual | Kebijakan Auto/Manual dipisahkan; pilihan gaya langsung dapat dikunci. |
| 4 — penekanan | Energi suara hanya metadata | Prominensi memengaruhi ukuran aksen yang bermakna. Toggle penekanan juga mematikan hierarki font aksen. |
| 4 — waktu baca | Teks berhenti saat masih ada jeda aman | Hold memakai jeda hingga frasa/shot berikutnya, tanpa menggeser timing kata sumber. |
| 4 — konsistensi | Review gaya memakai rencana berbeda dari final | Review, preview dan final berbagi kebijakan potongan, jeda dan audio dialog. |
| 5 — ilustrasi | Kartu kutipan mengulang subtitle | Hanya perbandingan eksplisit/daftar lengkap menjadi diagram setelah diucapkan; adegan materi/emosi dipertahankan. |
| 5 — aset editable | Diagram sederhana memerlukan runtime besar | SVG, proyek Motion Canvas dan video FFmpeg dengan fade disimpan; runtime browser opsional. |
| 5 — audio | Dialog diproses ulang pada rasio kedua | Cache berdasarkan isi sumber/potongan/normalisasi dengan checksum WAV; musik/SFX dicampur sesudah keputusan caption. |
| 6 — semua klip | UI mengemas satu klip/rasio | Seleksi proyek, antrean atomik dua rasio, snapshot final dan satu paket seluruh timeline. |
| 6 — komponen | SDK terisolasi tidak dipakai oleh ekspor | Backend utama didukung; komponen pyCapCut yang lolos sampel menjadi fallback nyata dan dicatat dalam manifest. |
| 6 — caption native | Animasi menghilangkan outline; shadow selalu aktif | CapCut mengikuti toggle kontras dan warna kata; Resolve memakai warna tersimpan. |
| 6 — media | Sumber/audio diduplikasi; master menunjuk ke luar paket | Dedup berdasarkan isi; master/SVG/proyek diagram disertakan; geometri hibrida tidak diterapkan dua kali. |
| 6 — cache | Isi video tanpa teks tidak diperiksa | Checksum MP4 diverifikasi sebelum dipakai ulang. |
| 7 — status | Ketersediaan komponen dianggap berhasil | Ketersediaan, uji model, QC render, struktur paket dan impor native dilaporkan terpisah. |
| 7 — performa | Sumber besar di-hash berulang dalam satu snapshot | Scope snapshot membaca tiap berkas yang tidak berubah sekali; pekerjaan berikutnya tetap memeriksa isi baru. |

## Komponen

Gunakan FFmpeg, font, `.venv`, ASR, Ollama/Qwen dan model CTC yang sudah dipasang. Patch tidak memerlukan model baru. Alignment tetap CPU; tidak perlu menginstal ulang CUDA global karena kegagalan WhisperX GPU sebelumnya.

Remotion dan Motion Canvas opsional. ASS/FFmpeg serta diagram lokal tetap bekerja tanpa keduanya. SmolVLM, SigLIP2, TalkNet dan SAM bukan syarat memasang patch. TalkNet dapat digunakan pada sumber beberapa pembicara setelah uji sampel.

Jika CapCut sudah dapat diekspor dari `.venv` utama, tidak perlu memasang SDK kedua. Jika backend belum tersedia, gunakan **Komponen & perangkat → pyCapCut**, jalankan uji sampel, kemudian ekspor ulang. Status kegagalan CapCut dan paket Resolve dilaporkan terpisah.

## Penerimaan pada laptop Anda

`CEK_PEMBENAHAN.cmd` memakai Python aplikasi dan menyimpan JSON diagnosis. Setelah server ditutup:

```bat
CEK_PEMBENAHAN.cmd --alignment --project ID_PROYEK
CEK_PEMBENAHAN.cmd --benchmark --project ID_PROYEK
```

Tanpa `--project`, alat memilih proyek bertanskrip terbaru. Alignment mengukur maksimal 12 rentang koreksi pada CPU, tanpa menerapkan timing hasil uji. `aligned=0` tanpa kandidat berarti model belum diukur. Timing yang ditolak tetap dilaporkan.

Benchmark merender seluruh klip terpilih dalam dua rasio, mengukur waktu/RAM/VRAM bila tersedia, lalu memeriksa reuse final. ASR/discovery dan impor native tidak dihitung. Uji pada sumber sekitar 30 menit, kemudian 1–2 jam. Target 30 menit untuk seluruh alur memerlukan pengukuran laptop; hasil uji singkat tidak boleh diekstrapolasi menjadi jaminan.

Di CapCut 9.5 dan Resolve Free 21.0.4 build 5: impor satu timeline, periksa awal/tengah/akhir, edit teks, geser ilustrasi, atur audio, render, simpan, tutup dan buka ulang. Catat melalui **Evaluasi & bukti impor**. Struktur yang lolos belum membuktikan kesamaan blur/fade/font native dengan MP4.

## Batas bukti

Kode dan pengujian yang tersedia diselesaikan dalam satu paket. Model CTC Windows, runtime browser yang terpasang, detektor pada video mentah, impor editor dan waktu produksi penuh memerlukan perangkat/masukan yang tidak tersedia di lingkungan pengembangan. Contoh visual memakai plate tanpa teks dari paket sebelumnya, transkrip tersimpan dan pengamatan wajah sebelumnya; bukan transkripsi atau deteksi baru.

Laporan QA dan contoh video berada dalam `verification` pada ZIP. QC teknis tidak dianggap penilaian manusia atas cerita atau bukti seluruh komponen telah berjalan pada laptop Anda.
