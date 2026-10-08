# Clipper Studio 4.0.7 — Pembenahan 1

Paket ini memperbaiki tujuh cacat yang dibuktikan dalam audit 4.0.6, adapter angka alignment, dan pelaporan hasil timing. Model dan keputusan editorial diuji terpisah dari pemeriksaan kode. Kualitas framing, desain, dan ilustrasi menjadi pekerjaan tahap berikutnya.

## Tujuh tahap pembenahan

| Tahap | Sasaran | Bukti selesai |
| --- | --- | --- |
| 1. Stabilitas dan integritas hasil | B01–B07, adapter alignment, status hasil dan cache | Regresi, ekspor clean, konsistensi transkrip, lalu uji timing di Windows |
| 2. Framing dan ruang aman | Prioritas pembicara/materi, crop stabil, panel adaptif, zoom terukur | Video nyata 9:16/16:9 mempertahankan wajah dan materi dengan ukuran layak |
| 3. Cerita dan batas klip | Gagasan unik, deduplikasi footage, awal/akhir lengkap, jeda bermakna | Klip utuh tanpa pengulangan gagasan; jumlah mengikuti cerita yang layak |
| 4. Tipografi dan subtitle | Hierarki, aksen berdasarkan makna, line break, posisi dan kontrol manual | Contoh Rapi/Ekspresif terbaca dan konsisten pada kedua rasio |
| 5. Efek, ilustrasi dan audio | Ilustrasi menambah pemahaman, transisi sesuai konteks, musik/SFX lokal | Preview nyata dengan suara jelas, gerak terarah, dan sumber ilustrasi terlacak |
| 6. Integrasi komponen dan ekspor | Alignment terukur, runtime renderer, semua klip dan rasio | Backend aktual terbukti; paket CapCut/Resolve memuat semua hasil terpilih |
| 7. Penerimaan dan performa | Import/edit/save/render/reopen, sumber 1–2 jam, RAM/VRAM, waktu | Bukti native, benchmark cold/warm dan pemulihan versi; target 30 menit dinilai lewat pengukuran |

Paket A mencakup tahap 1; Paket B mencakup tahap 2–5; Paket C mencakup tahap 6–7. Target tetap lokal, tanpa API berbayar, dengan MP4 serta paket editor. Durasi klip 30–120 detik mengikuti kelengkapan konteks. Hook berasal dari ucapan, tanpa banner judul.

## Isi patch tahap pertama

| Temuan | Perubahan |
| --- | --- |
| B01 — Motion Canvas | request.json ditulis di root proyek, sesuai import kedua modul; identitas aset diperbarui |
| B02 — Backdrop legacy | ASS mengikuti nilai kontras dalam rencana tersimpan; toggle memengaruhi outline/shadow |
| B03 — Legacy di Remotion | Warna, fade dan transisi aksen dipertahankan dalam plan; template mengeksekusi data tersebut dan mempunyai entry JavaScript yang valid |
| B04 — Video clean | Mode source_only meniadakan caption ASS, overlay Remotion, dan sisipan; fingerprint cache clean diperbarui |
| B05 — Kamus saat analisis ulang | ASR mentah disimpan sebagai take terpisah; identitas tampilan mencakup hasil/kebijakan koreksi; perubahan kamus memperoleh take baru |
| B06 — Riwayat antrean | Worker mengecek queued lewat SQL; semua tugas aktif dipertahankan dan ditampilkan sebelum riwayat terminal |
| B07 — Timestamp overlap | Interval diurutkan dan akhir ucapan mempertahankan maksimum, sehingga kata bersarang tidak dianggap jeda |

Koreksi manual dan timing pindah ke take tampilan baru hanya setelah sumber, track audio, dan ASR mentah terbukti sama. Jika bukti ASR berubah, patch lama tetap tersimpan dengan take lamanya dan perlu ditinjau kembali. Identitas take mentah serta lineage dapat diperiksa dalam metadata proyek. Perubahan tidak memakai migrasi schema database.

Adapter WhisperX kini mengubah skalar NumPy/Pandas yang memang berupa angka menjadi float Python sebelum pemeriksaan ketat. Strings, boolean, NaN, skor tanpa bukti, overlap, rentang kosong dan timing di luar audio tetap ditolak. Pesan error menyertakan angka hasil backend, tipe angka, dan batas audio. Folder dari Windows Copy as path dapat dibaca dengan tanda petik pembungkus.

Status membedakan berhasil, sebagian berhasil, perlu diperiksa, dan tanpa kandidat. Pekerjaan yang selesai tetapi aligned=0 tidak dinyatakan sebagai bukti keberhasilan pengukuran model.

## Pasang dan uji

1. Ekstrak seluruh paket di luar folder mesin. Selesaikan/batalkan antrean lalu tutup server lewat Ctrl+C.
2. Jalankan CEK_SEBELUM_UPGRADE.cmd dengan target C:\AI\clipper. Pemeriksaan menolak dasar kode yang berbeda sebelum menimpa file.
3. Jika pemeriksaan lulus, jalankan UPGRADE_PEMBENAHAN_1.cmd pada target yang sama.
4. Jalankan JALANKAN_PRO.cmd dari folder mesin. Tekan Ctrl+F5 di browser dan periksa versi 4.0.7.
5. Buka proyek uji, Transkrip & cerita, lalu Muat revisi terbaru. Kata Ketika yang sudah disimpan menjadi kandidat uji.
6. Klik Selaraskan frasa yang dikoreksi pada CPU. Target satu kandidat: aligned=1, attempted=1, errors kosong.
7. Dengarkan bagian sumber dan periksa timing yang tersimpan. Jika ditolak, kirim isi lengkap Alignment terakhir, termasuk diagnostic.

Tidak ada pip install atau unduhan model pada installer ini. Runtime dan bobot yang telah dipasang tetap dipakai. Cache render memakai identitas baru sehingga perubahan renderer/kontras tidak memanfaatkan hasil lama yang salah.

Cadangan kode tersimpan di steezy_backups/repair1-<waktu>. Installer juga membuat salinan SQLite melalui SQLite backup API sebelum mengubah kode, menggunakan WORK_DIR dari Config yang membaca lingkungan, .env, dan .env.pro dengan urutan yang sama seperti aplikasi. Database proyek aktif tidak ditimpa. PULIHKAN_PEMBENAHAN_1.cmd memulihkan kode dan mempertahankan edit proyek yang dibuat setelah upgrade; salinan SQLite sebelum upgrade tersedia terpisah dalam folder data pada cadangan.

Untuk GitHub, file sumber yang diperbarui ada pada payload dengan struktur folder yang sama. Paket dibangun dari commit lokal berbasis kode 4.0.6 yang dicocokkan dengan commit GitHub 71453b7cbe00c7b77ced73431d9405067f5af3d4. Manifest menyatakan source_origin=local; paket ini belum dikirim ke GitHub oleh assistant.

## Bukti dan batas pengujian

Tes Python menggunakan SQLite/worker/service asli; model berat dan decoder persiapan sumber diganti fixture terarah. Uji ekspor dan toggle kontras menjalankan FFmpeg/libass asli. Uji adapter memakai skalar NumPy nyata dan hasil CTC terkontrol. Uji UI menjalankan fungsi asli dengan DOM/React stubs. Semua itu menguji perilaku kode, bukan akurasi model Indonesia.

Remotion/Motion Canvas dengan browser, model CTC nyata pada Windows, GPU RTX 3050, native CapCut/Resolve, dan benchmark sumber 1–2 jam belum dijalankan pada lingkungan pengembangan ini. Laporan verification memuat perintah, hasil tes, dan cakupan. Keberhasilan timing pada laptop ditetapkan setelah uji langkah 6–7.

Rencana mengacu pada audit menyeluruh dan Laporan_Rencana_Pembenahan_Clipper_4_0_6, dengan identitas B01–B07 tetap sama.
