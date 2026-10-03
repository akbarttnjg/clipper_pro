# Hasil pengujian Studio 3.3

Dasar sumber: akbarttnjg/clipper_pro, commit 5b1020a600e7d7a5d3a97f92bacf996be0ee0f93.

## Hasil

- 245 pengujian Python lulus: 217 pengujian sebelumnya dan 28 kasus regresi versi 3.3. Satu peringatan deprecation Starlette, tanpa kegagalan. Satu tes lama disesuaikan dengan kontrak baru: frasa tidak dipotong pada pergantian komposisi dan band B-roll tidak mengecilkan seluruh shot.
- Tujuh respons pemeriksaan AI dari tiga sesi pengguna diputar ulang. Semuanya gagal validasi ID segmen dengan alasan segment_id yang dapat diperiksa. Respons gagal tidak menjadi cache yang terus digunakan.
- Empat edit-plan versi 3.2 diperiksa ulang. Durasi frasa terpendek berubah dari 0,033 menjadi 0,800 detik pada dua kasus, serta 0,147 menjadi 0,680 detik pada dua kasus lain. Tidak ada ID kata ganda pada hasil caption baru.
- Enam render FFmpeg nyata lulus QC teknis dan pemeriksaan tata letak caption: slide 16:9, slide 9:16, pembicara 16:9, pembicara 9:16, sisipan lokal terjadwal, dan preview dari tengah clip.
- Waktu B-roll diverifikasi lewat piksel pada detik 2, 6 dan 11: sumber asli, fixture sisipan, lalu sumber asli. Preview mempertahankan sisipan pada detik 10–12.
- Paket ekspor satu timeline dibentuk dan diperiksa secara struktural: XML DaVinci dan draft CapCut tersedia dengan track video, ilustrasi, dan teks. Status exporter tetap generated-unverified / experimental-generated sampai dibuka di editor pengguna.
- Tiga belas pemeriksaan installer: CRC ZIP, ekstraksi baru, path berspasi, dasar CRLF Windows, dry-run, perlindungan modifikasi lokal, penolakan payload rusak, instalasi offline, kesesuaian hash, keutuhan data pengguna, pemasangan ulang idempoten, perlindungan rollback, dan pemulihan tepat ke byte sebelumnya.

## Batas hasil

Render menggunakan video-clean.mp4 dan voice.wav dari paket pengguna sebagai sumber uji. Ini menguji komposisi yang sudah tersedia, bukan menjalankan ulang analisis pada video sumber lengkap 1–2 jam. Ilustrasi warna digunakan khusus untuk menguji waktu overlay, bukan menilai kualitas pemilihan stok.

Lingkungan uji memakai CPU/libx264. GPU RTX 3050, NVENC Windows, model Qwen dan Whisper lokal, serta permintaan langsung API stok tidak dijalankan dalam uji ini. Keberhasilan uji tidak membuktikan akurasi semantik semua topik, ASR, atau potensi FYP. Tampilan browser dan impor native CapCut 9.5/Resolve Free 21.0.4 tetap perlu diperiksa pada komputer pengguna.

Tidak ada biaya API baru atau model tambahan yang diwajibkan paket ini. Waktu proses laptop tidak dapat disimpulkan dari waktu render lingkungan uji.
