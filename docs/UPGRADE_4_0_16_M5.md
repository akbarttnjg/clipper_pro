# Clipper Pro 4.0.16 — M5

Paket ini kumulatif dari M2, M3, atau M4 yang terverifikasi. Hasil bawaan tetap dua rasio: potret dan lanskap. Rasio tambahan harus dipilih secara eksplisit.

## Pasang

1. Ekstrak ZIP ke folder baru di luar folder mesin. Jangan menyalin payload sendiri.
2. Selesaikan/batalkan antrean, tutup server dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`, masukkan lokasi mesin lama.
4. Sesudah lulus, jalankan `PASANG_M5_4_0_16.cmd`. Installer mencadangkan kode dan SQLite; kode lokal yang tidak dikenal menghentikan pemasangan sebelum penyalinan.
5. Jalankan `JALANKAN_PRO.cmd`, lalu Ctrl+F5 di browser. Header harus menampilkan 4.0.16 M5.

Video, model, environment, font pribadi, hasil lama, dan fixture lokal `m0_fixture.zip` tetap dipertahankan. Paket tidak memasang model/dependensi. Kode publik M2 lama di GitHub sudah termasuk baseline yang diperiksa.

## Gunakan M5

Buka Edit → Tampilan → M5 · Caption, brand dan finishing. Aktifkan M5 pada rasio aktif. Proyek lama tetap memakai gaya sebelumnya sampai Anda mengaktifkan M5. Terdapat sembilan kelompok kontrol: preset/template, font, paint, ruang, makna/timing, gerak/builder, subtitle sumber, brand/aset/layer, dan galeri/cover/pemeriksaan.

Mulai dengan preset Editorial. Klik **Lihat perubahan preset** sebelum menerapkan. Override manual dipertahankan kecuali kotak ganti manual dipilih. Mengubah satu warna menyimpan satu field; Reset menghapus override field itu dan kembali ke nilai yang diwarisi. Riwayat editor menyediakan Undo/Redo. Asal nilai ditampilkan pada setiap field.

Renderer ASS disarankan untuk kecepatan. Renderer Raster lokal memakai CPU, alpha qtrle, dan antialias 2×; lebih lambat tetapi tidak memerlukan browser/model. ASS dan Raster memakai CaptionPlan yang sama. Pemilihan Wajib Remotion untuk M5 berhenti dengan penjelasan; parity Remotion M5 belum dibuktikan. Opsi otomatis memakai ASS dan mencatat alasannya.

Font utama: DM Sans. Font aksen: DM Serif Display Italic. Putih dan aksen emas adalah titik awal, bukan jaminan estetika untuk semua sumber. Aktifkan penekanan bila perlu; emoji, karaoke, warna speaker, dan sensor dapat dimatikan sendiri. Ukuran glyph minimum 14 px pada simulasi layar selebar 360 px. Frasa dipecah menurut makna dan ruang; mesin menolak area yang tidak cukup, bukan mengecilkan teks melewati batas atau menghapus angka/negasi.

## Font dan aset

Masukkan lokasi lokal TTF/OTF atau gambar/video/audio, nama, asal/lisensi, dan pilih izin. Metadata yang belum berizin dapat diindeks, tetapi tidak boleh dipakai saat render/ekspor. Tombol ubah izin/lisensi menyimpan revisi metadata. Font dibaca dari family, style, weight dan Unicode cmap file aslinya. Glyph yang tidak tersedia menghentikan render dengan kode Unicode; impor fallback yang sesuai. Family/style ambigu dari dua file berbeda ditolak.

Aset menyimpan digest, asal, kredit, tag, koleksi, objek, teks, dan speaker. Pencarian memakai metadata lokal; bukan pengenalan objek/speaker otomatis. Simpan kit, tinjau sebelum menerapkan, unduh ZIP kit, atau impor ZIP pada instalasi lain. Sub-brand mewarisi nilai parent pada revisi yang dipin; perubahan parent berikutnya tidak mengubah kit yang sudah tersimpan. Kit dapat diterapkan ke rasio aktif atau seluruh klip/rasio terpilih melalui diff. History revisi tersimpan. Kamus kit tidak menulis ulang fakta: gunakan tombol terapkan kamus ke sumber secara eksplisit. Koreksi kritis tetap melalui review transkrip.

## Ruang, subtitle sumber dan bahasa

Posisi kiri/kanan/bawah tetap dihormati. Area manual memakai `[x,y,lebar,tinggi]` dalam persen output, misalnya `[6,58,82,23]`; `null` mengembalikan pilihan otomatis. Wajah/materi M4 tetap dilindungi. Jika subtitle tidak muat, perbesar area atau kurangi panjang frasa melalui transkrip; jangan memaksa font sangat kecil.

Deteksi subtitle bakar memakai usulan geometri dari sampel OCR M4 yang masih sesuai sumber. Ini bukan classifier makna subtitle. Tinjau dahulu; usulan tidak otomatis disetujui. Bila OCR belum siap, tandai area secara manual. Format area: `[{"rect":[8,70,80,12],"start":0,"end":10,"provenance":"ditinjau pada output","approved":true}]`. Interval menggunakan waktu sumber; posisi menggunakan output rasio aktif. Pilihan Hindari/Tutup/Rekonstruksi berarti melindungi area atau menutup lalu menggambar caption baru; tidak mengembalikan piksel sumber yang sudah tertutup teks lama.

Dua bahasa dipilih melalui track transkrip M2 yang telah disetujui. M5 memberi dua band terlindungi, memeriksa masing-masing track, serta menyertakan SRT sumber dan terjemahan terpisah. Jika area tidak cukup pada ukuran minimum, render berhenti.

## Speaker, sensor dan builder

Speaker styles: `[{"speaker_id":"S1","label":"Akbar","color":"#FFFFFF","approved":true}]`. Identitas dipilih operator, bukan dari ID pelacak wajah. Emoji map: `[{"keyword":"penting","icon":"★"}]`; font harus memuat glyph tersebut. Kamus sensor: `["kata"]`, mode Mask atau Mask+bleep, lalu setujui kamus sesudah mendengarkan konteks. Teks sumber tidak dihapus; mask dan bleep mengikuti clock output.

Builder terbatas: `{"id":"saya","name":"Gaya saya","motion":"rise","accent_ratio":1.12,"max_rows":2,"line_gap":0.23,"roles":["narration"]}`. Pilih Template buatan saya. Tidak ada JavaScript/Python yang dijalankan dari template.

## Layer finishing inti

Contoh logo: `[{"id":"logo1","kind":"logo","asset_id":"ID_ASET","start":0,"end":3,"rect":[5,5,12,12],"opacity":0.8,"anchor":"top_right","transition":"fade","transition_s":0.2}]`. Jenis lain: image, video, title, intro, outro, lower_third, diagram. Kartu adalah overlay terjadwal, tidak menambah detik sumber/audio. Intro/hook tidak muncul bila tidak ditambahkan. Lower-third memerlukan speaker disetujui dan interval ucapan yang sesuai.

Diagram memakai `quote`, seluruh `items`, opsional `values` dan `unit`. Item/angka harus ada dalam kutipan sumber; daftar tidak dipotong. Urutan layer mengikuti daftar. Maksimal empat layer bersamaan, luas total 35% canvas, B-roll 30 detik per layer, cache frame B-roll maksimal 512 MB. Layer ditolak bila menutupi materi/wajah/caption. Video B-roll mengikuti sumber, termasuk reverse/freeze/reorder M1. Required SigLIP2 yang tidak menghasilkan skor menghentikan render; skor tidak dibuat-buat. Cut/fade/blur/glitch hanya berlaku pada layer yang Anda pilih, maksimum transisi 0,4 detik; audio tidak diubah. Cakupan efek lengkap M9 tetap terpisah.

## Galeri dan cover

Simpan seluruh draf dahulu, kemudian buat galeri enam template pada sampel video Anda. Galeri memakai rasio/font/renderer aktif; bukan thumbnail promosi statis. Perubahan sumber/pengaturan menandai galeri lama. Cover dibuat dari frame preview/final revisi aktif pada rasio yang sama; pilih waktu output dan teks pendek opsional.

Buat preview cepat lalu detail untuk kedua rasio. Periksa minimum glyph, hold, kontras bergerak, wajah/materi, angka, negasi, penutup dan warna speaker. Simpan contoh final dan laporan; corpus G5 belum otomatis dinyatakan lulus hanya karena tes teknis lolos.

## Ekspor dan pemulihan

Tampilan terjaga mempertahankan final. Layer/paint M5 belum memiliki kesetaraan native penuh; gunakan mode terjaga untuk kesamaan tampilan. Hibrida memuat source layer yang sudah dibakar; tipografi editable tetap memiliki batas renderer editor. Bila bleep atau penutup subtitle bakar aktif, hibrida diblokir agar sensor/mask tidak hilang; gunakan mode terjaga. Native dasar diblokir untuk M5. Format CapCut yang sudah berjalan tidak ditulis ulang; teks DaVinci tetap ditunda.

Jalankan `PULIHKAN_M5_4_0_16.cmd` untuk rollback kode. Jika proyek/aset/kit/antrean memakai data M5, downgrade memerlukan flag `--restore-project-state`; SQLite terbaru dicadangkan sebelum snapshot pra-upgrade dipulihkan. Aset/video pribadi tidak dihapus. Baca laporan sebelum mengembalikan database.

`JALANKAN_UJI_M5.cmd` menjalankan suite pada instalasi Anda bila pytest tersedia. Uji native Windows/NVENC/model lokal dan penilaian estetika video asli belum dapat diwakili oleh tes Linux/fixture.
