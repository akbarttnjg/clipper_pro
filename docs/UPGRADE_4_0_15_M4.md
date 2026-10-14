# Clipper Pro 4.0.15 — M4 kamera dan layout

Paket kumulatif ini melanjutkan M3 4.0.14 dan juga mengenali unggahan GitHub M2 yang telah diverifikasi. Kode M3 yang diperlukan disertakan; tidak perlu memasang M3 lagi bila dasar M2 Anda cocok dengan hash. M4 mengikuti keenam paket di halaman 49 arsitektur dan VF01–VF17 di halaman 92–94.

## Pemasangan

1. Ekstrak ZIP ke folder baru di luar mesin lama.
2. Hentikan antrean, kemudian tutup server dengan **Ctrl+C**.
3. Jalankan **CEK_SEBELUM_UPGRADE.cmd** dan masukkan folder mesin yang berisi app.py, clipper dan .venv.
4. Setelah pemeriksaan lulus, jalankan **PASANG_M4_4_0_15.cmd**.
5. Buka mesin dengan JALANKAN_PRO.cmd lalu **Ctrl+F5**. Header menjadi **4.0.15 M4**.

Installer memeriksa kode dasar, membuat backup kode/SQLite, melakukan pemeriksaan import, dan memulihkan kode jika pemasangan gagal. Sumber, hasil lama, environment, model, .env/.env.pro, font pribadi dan arsip lokal m0_fixture.zip dipertahankan. Jangan menyalin payload secara manual. Kode lokal yang tidak dikenal tidak ditimpa.

Tidak ada unduhan model atau instalasi dependensi otomatis. FFmpeg/Pillow/NumPy dari environment mesin digunakan. Detektor/ASD/OCR/SAM lokal bersifat opsional; tracker objek/planar memerlukan OpenCV native yang telah tersedia. Bila komponennya belum siap, statusnya terlihat atau tugas khususnya ditolak dengan hasil lama tetap tersimpan.

## Percobaan pertama

1. Buka klip yang sudah diterima pada M3. Masuk **Edit**, pilih portrait atau landscape.
2. Buka **M4 · Kamera dan layout per adegan**.
3. Untuk sumber edukasi/papan, pilih **Edukasi no-pan**. Pilih **Otomatis per adegan** atau **Layar / papan**, gerak **Statis / tanpa pan**, sisi kosong **Pillarbox**.
4. Aktifkan OCR/detektor hanya bila komponen lokal tersedia. Area manual tetap bisa digunakan.
5. Klik **Simpan pengaturan kamera pada rasio ini**, lalu **Analisis kamera M4**.
6. Pantau antrean lalu klik **Muat hasil kamera**. Periksa frame, alasan speaker/fallback, materi/HUD, gerak dan waktu sumber.
7. Isi alasan, centang pemeriksaan yang benar-benar dilakukan, lalu **Terima dan aktifkan komposisi M4**.
8. Buat preview melalui kontrol mesin yang sudah ada, lalu render final.

M4 tidak aktif otomatis pada proyek lama. Hasil sebelumnya tetap tersedia. **Matikan M4 pada rasio ini** mengembalikan pemakaian jalur kamera tersimpan sebelumnya. M4 tidak mengganti transkrip, ucapan, font atau template gaya.

## Area manual dan scene

Frame memakai koordinat **persen sumber**, bukan persen layar output. Seret pada frame atau isi x, y, lebar, tinggi. Isi waktu mulai/akhir dalam **detik sumber**, kemudian **Tambahkan area ke draf**.

- **Crop terkunci**: batas crop manual; tidak diganti cue otomatis. Crop yang memotong materi penting ditolak.
- **Pembicara/subjek**: area orang yang ditinjau.
- **Materi/papan**: tulisan, grafik atau demonstrasi yang harus terlihat.
- **HUD/cursor penting**: area antarmuka permainan/layar yang perlu dipertahankan.
- **Lindungi area**: batas tambahan bagi crop/caption.
- **Objek**: area objek sumber yang perlu diperiksa.

Pin/area manual lama dipindahkan ke pengaturan awal M4 ketika belum ada kontrol M4 tersimpan. Pengaturan yang Anda simpan berikutnya merupakan pilihan eksplisit pada rasio tersebut.

Setiap shot menyimpan waktu/frame sumber. Pergantian suara/layout dapat membagi shot menjadi segmen layout tanpa menyebutnya cut kamera baru. Override scene disimpan ke draf dan masih perlu disimpan serta dianalisis ulang.

## Speaker, grid, layar dan gameplay

Label diarization tidak otomatis menjadi identitas wajah. Pilih **Hubungkan suara-wajah yang sudah diperiksa** hanya setelah mencocokkan sumber. Lintasan wajah adalah ID geometris, bukan identitas biometrik.

Jika ASD belum tersedia, suara overlap, wajah off-screen, occlusion atau identitas meragukan, mesin menjaga grid/frame/materi dan menjelaskan fallback. Detektor yang tidak tersedia tidak berarti video telah terbukti tidak mempunyai wajah. Pada lebih dari empat subjek yang belum jelas, frame utuh menjadi fallback.

Grid mendukung dua hingga empat subjek. Layar/gameplay mengutamakan materi/HUD dan memisahkan kamera orang. PiP beralih ke tile terpisah bila inset akan menutup area penting. Material/crop, caption band dan safe margin menggunakan geometri yang sama dalam preview/final.

## No-pan dan tracking opt-in

**Edukasi no-pan** mengharuskan crop statis. Gerak hanya aktif jika dipilih eksplisit pada profil lain. Deadzone, smoothing dan batas kecepatan memakai fraksi sumber. Bila lintasan berisiko memotong kepala, frame yang lebih aman dipertahankan.

Keyframe M4 memakai detik sumber dan crop persen; ukuran crop tetap, x/y dapat berubah. Kurva transformasi M1 tidak digabung diam-diam dengan crop M4. Matikan/hapus kurva M1 atau matikan M4 pada rasio tersebut. Edit waktu M1 seperti reorder, rate, reverse dan freeze tetap mengikuti clock sumber yang sama.

## Object/planar tracking dan attachment

Pilih area, rentang maksimal **30 detik**, waktu acuan, dan **Track objek** atau **Track permukaan planar**. Tracking mengukur fitur/flow dan RANSAC pada source clock. Occlusion, cut kamera, out-of-frame atau inlier yang lemah menghentikan pengukuran; layer tidak diekstrapolasi sesudah kehilangan track.

Opsional: pilih file gambar lokal PNG/JPG/WebP sebagai attachment. Gambar mengikuti quad terukur pada source layer. Opacity tersimpan dalam kontrak. Source, model/versi, measurements, inlier dan failure tercatat. Kualitas tracking native pada video asli belum dinyatakan lulus.

## Mask SAM kontinu

Pilih area subjek, rentang maksimal **enam detik**, dan frame acuan di dalam rentang. Pilih **Mask SAM kontinu**, simpan, kemudian analisis.

M4 meminta propagasi SAM lokal pada rentang, memeriksa sumber, ukuran, setiap sample dan kontinuitas waktunya, lalu membuat carrier lossless. Sample model dibawa ke setiap frame output melalui **nearest sample hold**. Ini bukan klaim inference neural 30 fps. Poster/satu frame tidak cukup untuk diterima sebagai mask kontinu.

Mask mengikuti reorder/reverse/freeze dari clock sumber. Rentang dengan materi/HUD/OCR penting memakai source yang aman; mask tidak menyembunyikan tulisan penting. Envelope mask/gestur tersedia bagi caption planner. Periksa seluruh rentang preview sebelum mencentang **Mask sepanjang rentang sudah saya periksa**.

Jika SAM belum tersedia atau propagasinya tidak lengkap, pekerjaan gagal dan laporan lama dipertahankan. Tidak ada mask rekaan sebagai pengganti. Kualitas gestur nyata dan alpha pada corpus asli masih bagian G4 yang belum lulus.

## Rasio tambahan dan ekspor

Default tetap portrait dan landscape. **Tambahkan rasio** dapat membuat 1:1, 4:5 atau ukuran khusus dengan dimensi genap 64–3840 pixel. Susunan/timing editor disalin secara eksplisit. Crop dan keputusan kamera tetap per rasio.

**Salin keputusan sumber ke rasio lain untuk ditinjau** tidak mengaktifkan approval otomatis. Rentang/speaker yang berbeda membutuhkan analisis sendiri. Periksa dan terima masing-masing rasio sebelum final.

Untuk M4 gunakan **Hibrida** atau **Tampilan terjaga** agar kamera/matte/attachment sesuai MP4. Geometri M4 belum menjadi kurva native dasar dalam CapCut/Resolve. Format penulis teks/editor lama dipertahankan; pembacaan teks DaVinci tetap ditunda.

## Draf dan pemulihan

Draf kamera terpisah per tab dan mempertahankan teks numerik persis. Konflik revisi tidak membuang draf. Gunakan **Bandingkan / muat revisi terbaru**, lalu periksa ulang sebelum menyimpan. Draf rusak dapat diunduh sebelum dibuang.

Rollback memakai PULIHKAN_M4_4_0_15.cmd setelah server ditutup. Bila sudah ada state/antrean M4, rollback kode saja ditolak. Untuk pemulihan state pra-upgrade yang sengaja dipilih:

~~~bat
py -3 complete_installer.py --rollback --restore-project-state --target "C:\AI\clipper"
~~~

SQLite terbaru dicadangkan terpisah sebelum state pra-upgrade dipulihkan. File sumber, model, index dan hasil tidak dihapus. Pengujian otomatis dapat dijalankan melalui JALANKAN_UJI_M4.cmd bila pytest sudah tersedia; skrip tidak memasangnya otomatis.

