# Steezy Pro Local 1.0

Modifikasi untuk Steezy-code/clipper, berdasarkan commit
`eda13985b1d93333baf8dc44327c65e552a782be`.
Disiapkan untuk Windows, Intel i5 generasi 12, RAM 40 GB, RTX 3050 VRAM 4 GB.
Profil ini merupakan titik awal; performa pada perangkat tersebut belum diukur langsung.

## Pasang

1. Tutup server Steezy (Ctrl+C di terminal yang menjalankan app.py).
2. Ekstrak **seluruh** ZIP ke folder tersendiri, misalnya `C:\AI\Steezy_Pro_Local_1_0`.
   Jangan menjalankan PASANG.cmd dari dalam tampilan ZIP.
3. Klik dua kali **PASANG.cmd**. Target otomatis adalah `C:\AI\clipper` jika ada.
   Jika instalasi berada di lokasi lain, jalankan dari terminal pada folder paket:
   `PASANG.cmd --target "D:\Aplikasi\clipper"`.
4. Setelah sukses, buka folder instalasi Steezy dan jalankan **CEK_PRO.cmd**,
   lalu **JALANKAN_PRO.cmd**. Buka `http://localhost:8765`.

Ini paket modifikasi untuk instalasi Steezy yang sudah berfungsi. Python 3.10+,
lingkungan `.venv`, FFmpeg/ffprobe dan dependensi Steezy perlu tersedia.
Installer menambah Pillow untuk pengukuran teks. Tidak perlu membeli lisensi,
memasukkan kartu, atau mendaftar API berbayar.

Ollama lokal harus berjalan untuk mode pilih cuplikan AI. Jika CEK_PRO menyatakan
model belum diunduh, jalankan `ollama pull qwen3:8b` di terminal. Model Whisper
multibahasa `medium` diunduh otomatis pada transkripsi pertama jika belum ada.
Unduhan model dapat berukuran beberapa GB. Setelah dependensi dan model tersimpan,
pemrosesan utama bisa berjalan tanpa internet. Face detector memakai model lama
jika tersedia; jika perlu ia mencoba unduhan gratis, dengan fallback detektor
bawaan OpenCV. Fitur Stock/B-roll tetap opsional dan dimatikan pada profil awal.

## Mulai dari sini

Pilih pengaturan **sebelum** memilih/menjatuhkan video, karena unggahan langsung
memulai proses.

| Pengaturan | Saran awal |
| --- | --- |
| Rasio | 16:9 untuk landscape; 9:16 untuk Shorts/Reels/TikTok |
| Proses | Pilih cuplikan AI untuk video panjang; video utuh untuk bahan yang sudah dipotong |
| Gaya teks | Editorial Kinetic |
| Posisi | Auto; gunakan kanan/kiri/bawah jika posisi otomatis kurang sesuai |
| Bahasa | Indonesia; Auto untuk bahasa lain/campuran |
| Layout | Fill |
| Trim silence | Mati, agar jeda bicara tetap natural |
| Stock/B-roll | Mati untuk alur lokal tanpa API |
| Jumlah clip | 4; jumlah nyata bisa lebih sedikit bila kandidat tidak memenuhi durasi |

**16:9** menghasilkan 1920×1080; **9:16** menghasilkan 1080×1920.
Rasio berbeda dari sumber akan melakukan crop. Sumber landscape menjadi vertikal
bisa kehilangan teks/grafik di tepi; preview terutama untuk materi edukasi dan keuangan.
Resolusi 1080p tidak mengembalikan detail yang tidak ada pada sumber berkualitas rendah.

Mode **video utuh** melewati pemilihan Ollama. Durasi dan jumlah clip tidak dipakai
pada mode ini. Bahasa dipakai pada transkripsi awal; untuk menggantinya, unggah ulang.

## Tipografi dan koreksi

- Editorial: kata muncul bertahap sesuai waktu ucapan, ukuran bertingkat, satu kata
  penekanan per frasa, aksen warna, animasi pendek dan shadow tipis.
- Clean: frasa tampil sekaligus dengan ukuran seragam untuk keterbacaan.
- Posisi Auto pada landscape mencoba sisi yang tidak bertabrakan dengan wajah yang
  terdeteksi. Jika tidak yakin, teks dipindah ke bawah. Pada portrait teks berada di bawah.
- Ukuran teks diukur terhadap area aman, termasuk untuk kata Indonesia yang panjang.
- Font DejaVu Sans Bold sudah dibundel beserta lisensinya. Kolom **Font klasik**
  hanya memengaruhi gaya Karaoke/Boxed/Bold. Warna Accent berlaku juga untuk Editorial.
- Untuk mengganti rasio/gaya/posisi, ubah kontrol atas lalu tekan **↻** di kartu clip.
- Tekan **Koreksi teks** untuk memperbaiki kata, waktu kata, kata penekanan dan batas clip.
  Semua waktu editor mengacu ke **video sumber**, bukan ke detik nol clip.
  Simpan koreksi, lalu tekan **↻**. Satu baris idealnya satu kata; hindari memasukkan
  satu kalimat panjang ke satu baris. Perubahan harus berurutan dan dalam durasi sumber.
- Hasil tersimpan di folder `clips`. File QC di sebelah MP4 memeriksa audio, resolusi,
  dan durasi; ia tidak menilai kebenaran isi atau daya tarik video.
- Transkrip, keputusan clip, koreksi dan rencana caption dicatat di `work/<job-id>`.
  Daftar pekerjaan/editor masih berada di memori: refresh halaman atau restart server
  tidak menyediakan pemulihan sesi editor otomatis. MP4 dan catatan kerja tetap ada.
- Render ulang memperbarui MP4 clip yang sama. Salin hasil dahulu jika ingin menyimpan
  beberapa versi rasio/gaya untuk clip yang sama.

## Profil perangkat

File `.env.pro` mengatur model dan pemakaian perangkat. Aplikasi membaca `.env`
lalu `.env.pro` (nilai profil Pro memiliki prioritas).

| Komponen | Setelan awal |
| --- | --- |
| Transkripsi | faster-whisper medium, Indonesia, word timestamps |
| GPU Whisper | Auto, int8_float16; CPU int8 bila CUDA tidak tersedia/gagal biasa |
| Pemilihan clip | Ollama qwen3:8b lokal, context 4096, 16 lapisan GPU |
| Memori GPU | Proses transkripsi terpisah berakhir sebelum Ollama mulai |
| Pekerjaan | Satu proses berat pada satu waktu; unggahan lain masuk antrean |
| Encoding | NVENC jika uji encoder berhasil; CPU libx264 jika tidak tersedia |
| Audio | Normalisasi satu tahap dengan target -16 LUFS |

40 GB RAM membantu menampung model pada CPU. RAM tidak menggantikan VRAM secara
langsung. Kecepatan dipengaruhi lama video, model, suhu, driver dan program lain;
paket ini tidak menjanjikan render real-time.

Jika VRAM penuh atau proses berhenti:

1. Tutup aplikasi lain yang memakai GPU. Ubah `OLLAMA_NUM_GPU=8` di `.env.pro`.
2. Jika masih gagal, gunakan `OLLAMA_NUM_GPU=0` agar pemilihan berjalan di CPU.
3. Untuk masalah DLL/CUDA/transkripsi, gunakan `WHISPER_DEVICE=cpu`.
4. Jika encoder GPU gagal setelah proses dimulai, gunakan `USE_NVENC=0`.
5. Restart Steezy setelah mengubah konfigurasi. CPU lebih lambat tetapi tetap lokal.

Jika medium terlalu lambat, `WHISPER_MODEL=small` dapat dipakai dengan kompromi
akurasi. Untuk istilah khusus/nama/singkatan, gunakan koreksi teks. Perubahan model
memerlukan unduhan model tersebut pertama kali.

## Backup, pemulihan, dan update berikutnya

- Installer memeriksa checksum paket dan mencadangkan setiap file yang akan ditimpa
  di `steezy_backups/<tanggal-waktu>/original`, beserta daftar filenya.
- Folder `uploads`, `clips`, model yang sudah ada dan folder `intelligence` khusus
  milik Anda tidak termasuk payload. File yang dimodifikasi paket memang ditimpa,
  tetapi versi sebelumnya ada pada backup.
- Kegagalan penyalinan akan mencoba mengembalikan file yang sudah tersalin.
  Instalasi dependensi Python tidak ikut dibatalkan.
- Untuk kembali: tutup Steezy, jalankan **PULIHKAN_PRO.cmd** di folder instalasi.
  Atau jalankan `PASANG.cmd --target "C:\AI\clipper" --rollback` dari folder paket.
- Pemulihan menolak menimpa file yang Anda ubah lagi setelah pemasangan, termasuk
  `.env.pro`. Jika ditolak, simpan perubahan tersebut dan gunakan file di folder
  backup untuk pemulihan manual sesuai daftar `backup.json`. Jangan hapus backup dulu.
- Jangan langsung menjalankan git pull ke file yang sudah dimodifikasi. Simpan backup
  dan bandingkan perubahan upstream lebih dahulu; paket ini berbasis commit di atas.
- Pratinjau pemasangan tanpa mengubah file: `PASANG.cmd --dry-run`.
- Jika Pillow sudah tersedia dan ingin memasang tanpa koneksi:
  `PASANG.cmd --skip-deps`. Model/dependensi lain tetap harus sudah terpasang.

## Batas versi ini

Ini implementasi tahap pertama dari arah blueprint: fondasi transkrip, seleksi clip
berbasis segmen sumber, tipografi terukur, koreksi manusia, dan pemeriksaan teknis
hasil. Bukan implementasi seluruh modul kognitif V2/V3 sekaligus. Adapter lama pada
folder `intelligence` tetap disimpan tetapi tidak dimuat oleh jalur baru.

Video referensi memakai keputusan editor manusia, pergantian shot dan penempatan
teks yang disengaja. Paket ini mendekati unsur tipografinya, tetapi hasil tidak
identik otomatis. Belum ada motion tracking per objek, deteksi siapa yang sedang
berbicara, penyusunan ulang multi-kamera, sound design atau penyisipan B-roll semantik
penuh. Crop bawaan mengikuti wajah terbesar; ketika dua pembicara tampil bersamaan,
ia belum tentu memilih pembicara aktif. Pergantian shot cepat tetap perlu diperiksa.

Pemilihan AI hanya menerima segmen yang benar-benar ada dan durasi yang valid.
Itu mengurangi timestamp karangan, bukan jaminan konteks selalu lengkap. Skor clip
adalah penilaian editorial model, bukan probabilitas viral atau penilaian kebenaran.
Jika Ollama gagal, aplikasi bisa memakai fallback segmen dengan peringatan jelas.

Gunakan video sumber bersih tanpa subtitle permanen. Teks yang sudah menyatu pada
video referensi tidak bisa dihapus otomatis oleh paket ini. Dua contoh MP4 dalam
folder `contoh` adalah uji sintetis tipografi tanpa narasi, bukan hasil AI dari
podcast Anda.

Lihat `CATATAN_PENGUJIAN.md` di paket untuk bagian yang sudah dan belum diuji.

Kode asal: https://github.com/Steezy-code/clipper
Dokumentasi dependensi: https://github.com/SYSTRAN/faster-whisper dan https://docs.ollama.com/
Kode asal berlisensi MIT; font mengikuti lisensi terpisah di clipper/fonts.
