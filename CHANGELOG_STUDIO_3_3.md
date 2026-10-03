# Clipper Studio Local 3.3

Perbaikan untuk dasar GitHub 5b1020a600e7d7a5d3a97f92bacf996be0ee0f93 (Studio 3.2).

- Model menerima pilihan ID segmen yang valid, terpisah jelas dari waktu detik. ID, durasi, rubrik, kelengkapan dan kutipan diperiksa sebelum digunakan. Satu percobaan perbaikan diberi alasan penolakan; tidak ada pelonggaran kriteria agar hasil terlihat berhasil.
- Cache menyimpan respons yang lolos grounding. Cache gagal versi sebelumnya tidak dipakai. Periksa AI meminta pemeriksaan baru; diagnostik tersimpan di boundary-reviews atau topic-windows.
- Keputusan cerita yang belum terverifikasi tidak lagi menjadi veto palsu terhadap ilustrasi. Keputusan preserve_speaker yang valid tetap dihormati, begitu juga materi papan tulis.
- Status B-roll membedakan sisipan tersedia, kosong, dilewati, dan layanan/aset belum tersedia. Preview di tengah clip menjaga waktu sisipan dan offset aset.
- Frasa subtitle tetap utuh melewati pergantian komposisi. Panel bersama melindungi wajah dan materi; B-roll pendek hanya memengaruhi komposisi pada rentang terkait beserta frasanya.
- Deteksi materi mencakup slide putih besar dan kartu diagram berwarna pada latar netral. Zoom hanya dinonaktifkan bila berisiko menabrak panel subtitle.
- Perbarui koreksi menerapkan kamus pada sesi tersimpan tanpa menjalankan Whisper. Koreksi manual dan arsip transkrip asli dipertahankan; cadangan sesi dibuat sebelum perubahan.
- Preview lama tanpa fingerprint dikenali sebagai cache. Cache dan hasil versi 3.3 dibedakan dari 3.2.
- Installer offline memeriksa isi paket, dasar kode lokal, perubahan CRLF Windows, cadangan, dan rollback. Tidak mengganti media, kredensial, model, font, atau lingkungan Python.

Format ekspor native tetap perlu dicoba pada CapCut dan DaVinci pengguna. ASS merupakan master subtitle, bukan format layer native yang identik pada kedua editor. Upgrade ini tidak mengganti model AI dan tidak menjanjikan FYP atau waktu proses tertentu.
