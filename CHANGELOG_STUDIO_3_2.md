# Perubahan 3.2

- Folder keluaran per proyek; video, subtitle, laporan, ekspor, dan revisi lama terpisah.
- Cache preview terpisah, fingerprint untuk penggunaan ulang, tombol hapus dengan ukuran dan perlindungan proses aktif; pengenalan preview lama dan perapian hasil lama.
- Pencarian hingga lima cerita per jendela, penelusuran tambahan pada jendela yang minim kandidat, kandidat cadangan sebelum batas hasil, dan pemeriksaan seluruh sumber dengan pelaporan cakupan.
- Duplikasi tidak lagi ditentukan hanya oleh kosakata topik yang sama. Batas hasil nol berarti adaptif; batas eksplisit hingga 100. Tombol pencarian tambahan mempertahankan edit sesi.
- Petunjuk kosakata Whisper, dengar ulang audio meragukan secara terbatas, koreksi alias berkonteks, kamus pengguna, dan log koreksi. Teks mentah dan waktu sumber tetap tersedia.
- Tanda baca tampilan minimal dengan perlindungan angka, desimal, persentase, dan penyangkalan; kata meragukan ditandai.
- Perlindungan area wajah/tulisan pada komposisi hasil; area subtitle stabil per adegan dan jalur terpisah bila penuh. Animasi diperiksa terhadap area terdeteksi. B-roll memakai area yang sama di render dan ekspor.
- Preset Editorial bertingkat, hierarki ukuran, animasi yang tetap di panel, pemisahan frasa pada pergantian adegan, serta area pembicara vertikal yang tidak dipotong ulang.
- Form awal lebih ringkas, bantuan terlihat sebelum tindakan, penjelasan scope clip, laporan cakupan, dan panel Folder & cache.
- Tidak menambahkan API berbayar atau mengganti model Whisper/Qwen pengguna. Dependensi 3.1 tetap dipakai; model wajah YuNet disertakan beserta lisensinya.
