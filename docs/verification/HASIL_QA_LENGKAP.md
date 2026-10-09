# QA Pembenahan Lengkap 4.0.8

Kode dasar dibandingkan dengan commit GitHub 9e0677c60605be0d16a6f19eebf8cb12094a3531: 53 file cocok. Pengujian mencakup geometri, penempatan caption, deduplikasi fakta, sumber kata/negasi/angka, preset manual, prosodi, diagram, audio, SQLite, antrean, ekspor massal dan pemasang.

140 uji Python dan lima uji modul UI lolos. Pemasang diuji untuk checksum, cadangan SQLite, rollback, data model yang terlindungi, dan paket nyata 44 file. Log dan checksum paket tersedia dalam folder verification ZIP. Uji Python memakai pustaka standar dan FFmpeg nyata. Uji UI menggunakan modul sebenarnya melalui adapter DOM; ini bukan pengujian browser native.

Replay visual memakai video tanpa teks dari ZIP pengguna sebelumnya. Plate 1514 × 852 dipulihkan dari canvas 1920 × 1080 dan dibesarkan kembali sebelum pengujian 14 detik. Transkrip serta pengamatan wajah berasal dari rencana edit sebelumnya; detektor dan ASR baru tidak dijalankan.

Dua hasil Full HD (1080 × 1920 dan 1920 × 1080) lolos QC stream, ukuran, durasi, batas caption, envelope animasi, area terlindungi dan waktu baca. Audio terukur sekitar -16.02 LUFS / -1.49 dBTP. Ini pengukuran FFmpeg, bukan penilaian dengar.

Serializer pyCapCut memakai sumber repository resmi pada tree 27480a1e954740af50363076e6fea94f2893ae93. Metadata media berasal dari FFprobe melalui adapter MediaInfo. Struktur paket CapCut dan Resolve lolos pada dua timeline; uji ekspor proyek SQLite juga mencakup dua klip × dua rasio (empat final). SDK snapshot dan lingkungan QA tidak disertakan sebagai komponen produksi.

Worker pyCapCut terisolasi juga dijalankan dalam lingkungan Python terpisah dengan SDK snapshot dan adapter yang sama. Backend managed_component digunakan dan kedua struktur editor lolos. Ini tidak memverifikasi SDK atau DLL yang terpasang pada Windows pengguna.

Uji pemasangan seluruh 44 payload di atas fixture kode dasar berhasil. Rollback mengembalikan kode, dua edit SQLite sebelum/sesudah pemasangan tetap ada, dan penanda bobot model tidak berubah. Pemeriksaan impor runtime Windows dikontrol dalam fixture karena lingkungan aplikasi laptop tidak tersedia.

Penerimaan yang memerlukan perangkat sasaran: alignment CTC bahasa Indonesia pada Windows; detektor/ASR dari video mentah; renderer Remotion/Motion Canvas terpasang; impor, edit, render, simpan dan buka ulang editor; pengukuran seluruh alur untuk sumber 30 menit dan 1–2 jam.

Status konstruksi, struktur, dan impor editor dibedakan. Kelengkapan cerita/akurasi transkrip/retensi tetap memerlukan tinjauan manusia. Tidak ada klaim bahwa semua komponen sudah berjalan pada laptop sasaran atau bahwa target 30 menit sudah terpenuhi.

## Pemeriksaan unggahan GitHub pengguna

Commit `1a6bcb82801c83d7bc19e00a18e125deb6c85454` pada `main`, 9 Oktober 2026 pukul 21:41 WIB, berisi seluruh 44 file pembenahan. Isi cocok dengan paket sebelumnya setelah normalisasi akhir baris pada `CEK_PEMBENAHAN.cmd`; 11 file penjaga juga cocok. Berkas pembenahan telah masuk ke kode aktif, bukan hanya menjadi arsip ZIP.

Snapshot modul aplikasi dan UI dari commit tersebut lulus 138 uji Python dan lima uji modul UI. GitHub Actions belum memiliki riwayat run, dan commit tidak memiliki commit status; kelulusan di atas berasal dari pemeriksaan lokal, bukan CI GitHub. Sebagian pengujian memakai pengamatan/geometri OpenCV terkontrol karena OpenCV tidak tersedia pada host QA; detektor sebenarnya belum diuji di laptop.

Dua kegagalan makna berhasil direproduksi pada diagram daftar: sumber dengan lima poin digambarkan hanya empat poin, dan kalimat pembatas di antara poin terbuang. Perbaikan menolak diagram jika daftar yang diamati melampaui empat poin atau ada kalimat tambahan di antara penanda poin. Ucapan sumber tetap dipertahankan. Regresi tambahan beserta seluruh suite lulus, sehingga total menjadi 140 uji Python. Perbaikan ini disiapkan pada branch PR; belum digabung otomatis ke `main`.

Versi aturan diagram dimasukkan pada cache aset dan dependency preview/final hanya saat ilustrasi aktif. Uji SQLite memastikan empat final dua-klip/dua-rasio lama tidak digunakan ulang, sedangkan dependency analisis sumber serta render tanpa diagram tidak berubah. Pemasang revisi menerima checksum unggahan 4.0.8 terverifikasi agar pengguna yang sudah memasang pembenahan dapat menerapkan perbaikan ini.
