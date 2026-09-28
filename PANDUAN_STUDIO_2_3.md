# Clipper Studio Local 2.3 — panduan upgrade

Paket ini memperbarui instalasi Clipper Studio 2.x yang sudah berjalan, termasuk fork `akbarttnjg/clipper_pro` versi 2.2. Seluruh font dan video contoh preset dibundel. Pemasangan normal tidak mengunduh model, tidak memasang ulang Python, dan tidak memerlukan API berbayar.

## Pasang di Windows

1. Tutup server Clipper: tekan **Ctrl+C** di terminal yang menjalankan aplikasi.
2. Ekstrak seluruh `Clipper_Studio_Local_2_3.zip` ke folder baru. Jangan menjalankan installer langsung dari dalam ZIP.
3. Jalankan **PASANG_UPGRADE.cmd**. Jika `C:\AI\clipper` tersedia, installer memakainya. Untuk lokasi lain, jalankan `PASANG_UPGRADE.cmd --target "D:\folder\clipper"` dari terminal di folder paket.
4. Jalankan **CEK_PRO.cmd**, kemudian **JALANKAN_PRO.cmd** dari folder instalasi Clipper.
5. Buka `http://localhost:8765`, lalu **Ctrl+F5** agar browser memuat UI 2.3.
6. Buka sesi tersimpan. Kandidat dan transkrip lama dapat dipakai kembali; tidak perlu menjalankan analisis 30 menit lagi.

Installer membuat cadangan otomatis di `steezy_backups`. Folder `work`, `uploads`, `clips`, `.venv`, berkas `.env` / `.env.pro`, brand pribadi dan preset pribadi tidak termasuk berkas yang ditimpa. Output lama tetap ada; render baru memakai akhiran `-v23`.

Jika perlu kembali, tutup server lalu jalankan **PULIHKAN_PRO.cmd**. Pemulihan ditolak jika berkas program telah diubah lagi setelah pemasangan, agar perubahan tersebut tidak hilang. Pemulihan program tidak menghapus hasil video atau sesi pengguna.

## Memulai gaya baru pada clip lama

1. Pilih kartu clip di kiri. Kartu aktif adalah clip yang sedang diedit; kotak centang menentukan clip yang akan dirender.
2. Buka tab **Gaya → Pilih tampilan**. Mulai dari **Editorial elegan** untuk podcast, atau **Ruang belajar** untuk edukasi.
3. Pilih **Font utama** dan **Font penekanan** jika ingin mengganti pasangan. Centang **Gunakan pasangan font**. Isi kata penting yang memang ada dalam ucapan, misalnya `skill, penghasilan, risiko`.
4. Atur intensitas **Tenang** atau **Seimbang**, ukuran **100%**, dan warna aksen. Ukuran tersedia 70–130%; mesin dapat mengecilkan frasa yang panjang agar tetap muat.
5. Buka **Komposisi** untuk rasio, framing, dan posisi teks. Biarkan penyesuaian posisi demi keterbacaan aktif sebagai awal.
6. Geser video **Sumber** ke bagian yang ingin diperiksa, lalu klik **Preview dari sini**. Preview berlangsung hingga 12 detik dari posisi itu, termasuk bagian tengah/akhir clip. Di ujung clip, preview dimulai dari maksimal 12 detik sebelum akhir.
7. Bila sesuai, **Simpan koreksi** dan **Render pilihan**. Untuk banyak clip, klik **Salin gaya ke clip yang dicentang** terlebih dahulu.

Preset tampilan mengatur font, warna, ukuran, intensitas dan animasi. Preset tidak memindahkan batas cerita, mengganti rasio, atau mengganti musik. Bagian **Preset saya** menyimpan kombinasi pribadi secara lokal, maksimal 30 preset.

## Lima tampilan

| Tampilan | Pasangan font | Gerak utama |
|---|---|---|
| Editorial elegan | DM Sans SemiBold + DM Serif Display Italic | Variasi gerak halus per frasa |
| Angka tegas | DM Sans SemiBold + Bebas Neue | Pop penekanan |
| Ruang belajar | DM Sans SemiBold + Montserrat Bold | Geser terarah |
| Fokus lembut | DM Sans SemiBold + DM Serif Display | Blur singkat ke tajam |
| Pop editorial | Montserrat Bold + DM Serif Display Italic | Pop terukur |

Kata penekanan berasal dari pilihan pengguna, angka, atau kosakata isi tertentu saat daftar kata penting kosong. Kata terpanjang tidak otomatis dianggap paling penting. Font yang diukur untuk tata letak digunakan pula oleh ASS dan metadata teks editor. Bayangan lembut membantu keterbacaan di atas gambar terang.

## Empat tab pengaturan

- **Gaya:** preset, font utama/penekanan, kata penting, animasi, intensitas, ukuran, warna, preset pribadi, salin gaya.
- **Komposisi:** 9:16 / 16:9, fokus pembicara / seluruh gambar / materi + pembicara, posisi teks, zoom, area manual.
- **Cerita:** judul, batas waktu, perapian subtitle, judul tiga detik, kutipan pembuka, pemangkasan jeda.
- **Audio:** berkas musik/efek untuk sesi dan volume untuk clip aktif.

Ketika panel materi terdeteksi di 16:9, penempatan aman menyediakan ruang subtitle di bawah gambar. Pada materi + pembicara 9:16, mesin menyediakan ruang teks di antara materi dan pembicara bila diperlukan. Ini menggunakan perkiraan geometri gambar, bukan pemahaman isi diagram; tetap periksa adegan yang berubah. Mematikan penempatan aman mengizinkan posisi manual kembali.

## Perapian teks yang bisa diperiksa

**Cerita → Rapikan ringan** menyembunyikan gumaman seperti `eee/emm/hmm` dan pengulangan dekat dari beberapa pengisi seperti `nah nah`. Audio, timestamp kata yang dipertahankan, serta transkrip sumber tidak ditulis ulang. Kata negasi, keraguan (`mungkin`), nominal, dan fakta tidak ditebak atau diganti.

Klik **Bandingkan teks sebelum / sesudah** untuk melihat perubahan. Pilih **Semua kata transkrip** untuk menampilkan kembali semuanya. Angka pecahan yang mencurigakan atau angka dengan timestamp sangat panjang ditandai untuk didengarkan kembali. Laporan tersedia di `clips/*-v23.subtitle-review.json`; rencana edit menyimpan kata sumber dan kata tampilan secara terpisah.

Pilihan **Pangkas jeda bicara panjang** adalah pengaturan terpisah yang memang dapat mengubah durasi audio/video. Koreksi ejaan manual tetap disimpan sebagai koreksi, tanpa menghapus transkrip analisis asli.

## MP4 dan proyek editor

- **MP4:** hasil dengan tipografi dan animasi sudah menyatu; siap digunakan setelah pemeriksaan isi.
- **ASS:** master animasi subtitle untuk renderer ASS/libass; bukan jaminan layer native di CapCut/Resolve.
- **Paket CapCut + DaVinci:** video tanpa teks, track suara/musik/efek, font, ASS, SRT, rencana edit, dan proyek dengan teks native.
- **DaVinci:** XML timeline + komposisi Fusion/Text+ dan pengimpor Lua di dalam paket. Satu clip per timeline.
- **CapCut:** draft dengan layer teks dan wrapper multi-timeline; draft per clip tetap disediakan sebagai cadangan.

Framing dan zoom sudah menyatu di video bersih. Posisi, ukuran dan font teks diteruskan ke layer native; blur/fade CapCut belum memiliki pemetaan yang terverifikasi. Bayangan/ukuran atau animasi native dapat tampak berbeda dari render ASS. Instal TTF dalam folder `Fonts` untuk Resolve, lalu ikuti `BACA_DULU.txt` dalam paket proyek.

Berkas ekspor dan referensi font diuji otomatis. Impor interaktif pada **CapCut 9.5** dan **DaVinci Resolve Free 21.0.4** milik Anda masih perlu dicoba pada satu proyek. Jangan menganggap MP4, ASS, dan teks native identik sepenuhnya.

## Kebutuhan dan batas pengujian

Tidak ada model AI atau dependensi runtime baru untuk upgrade ini. NVENC dan fallback CPU yang sudah ada tetap digunakan. Kecepatan laptop dan akurasi ucapan tidak dapat dinilai dari uji di mesin lain; paket ini berfokus pada tipografi, UI, penempatan, dan penggunaan hasil analisis tersimpan.

Lihat `TEST_REPORT_STUDIO_2_3.md` untuk pengujian yang benar-benar dijalankan. Gunakan sumber asli yang sudah diunduh sebagai masukan; hindari memasukkan MP4 yang subtitelnya sudah menyatu untuk membuat subtitle kedua.
