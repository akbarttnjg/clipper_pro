# Clipper Studio Local 2.0

Upgrade untuk `akbarttnjg/clipper_pro`, berdasarkan commit
`7d74f843e7a851fb88af8bf66d0dc7d311a5c2ae`. Profil awal: Windows,
i5-12500H, RAM 40 GB, RTX 3050 4 GB. Tidak membutuhkan API berbayar.

## Memasang

1. Tutup server Clipper lama dengan **Ctrl+C** di terminal.
2. Ekstrak seluruh ZIP ke folder baru, misalnya `C:\AI\Clipper_Studio_2_Upgrade`.
   Jangan menjalankan installer dari dalam tampilan ZIP.
3. Klik dua kali **PASANG_UPGRADE.cmd**. Masukkan folder Steezy jika diminta;
   lokasi default adalah `C:\AI\clipper`.
4. Installer memeriksa checksum, memasang dependensi tambahan di `.venv` yang sudah
   ada, lalu mencadangkan file lama ke `steezy_backups`. File `.env.pro` ikut diganti
   dengan profil versi 2; versi sebelumnya ada di backup.
5. Di folder Steezy, jalankan **CEK_PRO.cmd**, kemudian **JALANKAN_PRO.cmd**.
   Buka `http://localhost:8765`. Tekan **Ctrl+F5** bila browser masih menampilkan UI lama.

Installer tidak menyertakan Python, FFmpeg, Ollama, atau model Whisper/Qwen yang besar.
Komponen Steezy yang sudah bekerja tetap digunakan. Dependensi Python tambahan perlu
internet saat pemasangan. Setelah model tersedia, proses video berlangsung lokal.

Instal ke lokasi lain dari terminal:

```bat
py -3 steezy_pro_installer.py --target "D:\AI\clipper"
```

Simulasi tanpa mengganti file: tambahkan `--dry-run`. Jika dependensi tambahan sudah
terpasang dan sedang offline, tersedia `--skip-deps`.

## Alur yang disarankan

1. **Video baru** → pilih file hasil unduh. Untuk video 1–2 jam, gunakan **path lokal**
   agar aplikasi tidak menyalin video besar. Isi path musik/efek juga bila memakai mode path.
2. Pilih **9:16** atau **16:9**, bahasa Indonesia/campuran, durasi adaptif, batas 10 clip.
3. **Analisis video**. Whisper ditutup sebelum Qwen dimuat. Kandidat dipilih berdasarkan
   isi konkret, kejelasan pembuka, dan penutup. Jumlah boleh kurang dari 2 bila isi yang
   lolos sedikit; aplikasi tidak mengisi kuota dengan cuplikan lemah.
4. Pilih kartu clip. Dengarkan awal dan **Dengar penutup**. Klik kata pada transkrip
   untuk mencari posisi sumber. Tombol **I/O** menandai awal/akhir dari playhead sumber.
   Sesudah memperpanjang batas, klik **Muat konteks batas** untuk memeriksa teks tambahannya.
5. **Edit kata** memperbaiki ejaan. Atur judul, kata penting, rasio, posisi teks, warna,
   ukuran, komposisi, musik, serta kutipan pembuka. Simpan koreksi.
6. **Preview 12 detik** membuat render kecil dari awal susunan edit, termasuk hook bila
   diaktifkan. Periksa tampilan dan suara. Preview bukan MP4 final 1080p.
7. Centang kandidat yang disetujui → **Render pilihan**. File final ada di `clips`
   dan dapat diunduh dari kartu clip. Pengaturan tiap clip tersimpan terpisah.
8. **Paket CapCut + DaVinci** membentuk proyek dari revisi hasil render yang sama.
   Perubahan setelah render mewajibkan render ulang agar proyek tidak memakai data lama.

## Cara kerja edit

- **Topik utuh:** jendela analisis bertumpang tindih dan ID segmen sumber digunakan untuk
  menahan model agar tidak mengarang waktu. Kutipan penutup diverifikasi terhadap transkrip.
  Ini membantu seleksi; batas semantik dan akurasi transkrip tetap diperiksa manusia.
- **Durasi:** umumnya 30–120 detik, toleransi hingga 20 detik untuk menuntaskan topik.
  Hook yang diputar ulang di depan menambah durasi hasil beberapa detik.
- **Hook:** kutipan asli dipindahkan ke awal lalu tetap terdengar dalam konteks pembahasan
  utama. Tidak ada suara sintetis. Kolom waktu hook memakai detik **video sumber**.
  Kutipan harus berada dalam clip. Kosongkan kedua kolom bila tidak ingin kutipan pembuka.
- **Jeda:** hanya jeda panjang yang dipadatkan. Pemotongan isi/pengulangan verbal yang
  mengubah argumen belum dilakukan otomatis. Alur utama tetap kronologis.
- **Kamera:** deteksi wajah pada sampel, pembagian adegan, lalu posisi crop dikunci per
  adegan. Bukan pelacak wajah setiap frame. Multi-orang/wajah kecil yang meragukan memakai
  gambar utuh. Belum ada identifikasi pembicara aktif dari audio.
- **Materi/grafik:** mode *Pertahankan seluruh gambar* menjaga informasi. Mode *Materi +
  pembicara* menyediakan komposisi atas/bawah pada 9:16 jika wajah terdeteksi. Grafik kecil
  tetap perlu ditinjau; memilih 16:9 sering lebih jelas.
- **Tipografi:** frasa utuh maksimal dua baris, kotak teks diukur, baseline konsisten,
  kata bermakna/angka memakai hierarki ukuran/warna dan font aksen. Transisi frasa berupa
  fade singkat; penekanan warna mengikuti ucapan. Tidak ada efek acak setiap kata.
- **Zoom:** penekanan isi yang memenuhi jarak waktu, lalu kembali. Jump cut dan pergantian
  adegan tetap berupa cut bersih agar pembicaraan tidak terasa seperti slideshow.
- **Audio:** suara dinormalisasi, musik lokal dikecilkan saat orang berbicara, fade awal/akhir,
  efek suara singkat pada hook/zoom bila file efek disediakan, limiter pada mix akhir.
  Efek suara tidak dibuat/diunduh otomatis.
- **Sesi:** kandidat, koreksi, pengaturan, dan hasil render tersimpan. Setelah crash/restart,
  pilih riwayat proyek dan pulihkan. Transkrip yang cocok dapat dipakai kembali.

## CapCut dan DaVinci

Ekspor adalah **proyek editable**, dengan sumber video, kata/komposisi teks, dan WAV
suara/musik/efek terpisah. MP4 final juga tersedia sebagai hasil siap pakai.

| Editor | Isi paket | Cara membuka |
|---|---|---|
| DaVinci Resolve Free | XML per clip, SRT, komposisi Fusion Text+, satu script yang membuat satu proyek berisi N timeline | Jalankan `SIAPKAN_DAVINCI.cmd`, lalu perintah `dofile(...)` yang ditampilkan di Console Lua Resolve |
| CapCut 9.5 | Draft satu proyek dengan N timeline; draft per clip sebagai alternatif | Tutup CapCut, jalankan `PASANG_CAPCUT.cmd` dari paket proyek |

**Kompatibilitas native bersifat eksperimental.** Struktur XML/JSON, kontinuitas waktu,
dan sintaks Lua/Fusion diperiksa di lingkungan pengembangan. Aplikasi Resolve Free 21.0.4
dan CapCut 9.5 tidak tersedia di sini, sehingga keberhasilan impor serta kesamaan tampilannya
belum dapat dinyatakan teruji. Uji satu clip terlebih dahulu.

Batas ekspor yang diketahui:

- Penekanan warna pada komposisi Fusion masih statis; MP4 menggunakan penekanan saat ucapan.
- Resolve menerima framing dasar yang dapat diedit. Titik zoom ditandai dengan marker;
  keyframe zoom halus dapat ditambahkan di Inspector. CapCut menerima keyframe zoom.
- Mode materi+pembicara diekspor sebagai gambar utuh pada editor; split perlu disusun ulang.
- Ukuran/posisi font native bisa berbeda dari libass. Dua font disertakan; instal melalui
  klik kanan TTF → **Install** sebelum membuka Fusion.
- Video sumber asli direferensikan untuk menghindari menyalin berjam-jam media. **Jangan
  pindahkan sumber atau folder paket proyek** setelah impor. Audio dan font dibawa dalam paket.
- Installer CapCut membuat proyek baru dan backup indeks; tidak menimpa draft lama.
  Folder CapCut khusus dapat diberikan lewat `--draft-root`.

## GPU dan target waktu

NVENC sekarang diuji dengan encode 720p, bukan sampel 64×64 yang bisa gagal meskipun
GPU mampu encode. **CEK_PRO.cmd** menampilkan path FFmpeg dan alasan kegagalan aktual.
Jika NVENC gagal saat render, aplikasi mencoba CPU satu kali dan menampilkan peringatan
serta log. NVENC mempercepat encoding; transkripsi, AI pemilihan, dan sebagian filter
memiliki beban tersendiri.

Tutup Resolve/CapCut saat transkripsi atau pemilihan AI agar VRAM 4 GB tidak berebut.
Whisper dan Ollama dijalankan bergantian. RAM 40 GB membantu proses CPU, tetapi tidak
menggantikan VRAM. Profil awal memakai Whisper `medium` dan Qwen `qwen3:8b` lokal.

**30 menit merupakan target, bukan hasil benchmark di laptop Anda.** Ukur satu video
representatif dahulu. Jika transkripsi terlalu lambat, coba `WHISPER_MODEL=small` di
`.env.pro` dan cek akurasi nama/angka. Jika Qwen kehabisan VRAM, turunkan
`OLLAMA_NUM_GPU` dari 16 ke 8; pemrosesan akan lebih banyak memakai CPU.

## Pemulihan dan laporan masalah

Tutup server, jalankan **PULIHKAN_PRO.cmd** di instalasi Steezy. Pemulihan memeriksa
checksum agar tidak menimpa perubahan baru sesudah pemasangan. Dependensi Python yang
ditambahkan tidak dicopot oleh rollback; backup memulihkan file aplikasi.

Untuk melaporkan masalah, lampirkan keluaran `CEK_PRO.cmd`, pesan pada UI, log render
clip yang gagal (`clips/*.render.log`), serta satu contoh hasil. File `.env` yang berisi
kredensial tidak perlu dibagikan. Tidak ada alasan mengunggah seluruh sumber 2 jam untuk
masalah tampilan yang sudah dapat direproduksi pada potongan pendek.

## Catatan kode

`intelligence/` lama tidak dipanggil oleh pipeline baru. Modul tetap berada di instalasi
Anda; upgrade ini tidak menghapusnya. Titik utama: `story.py`, `editplan.py`,
`composition.py`, `typography.py`, `render.py`, `projects.py`, dan `app.py`.

Basis Steezy berlisensi MIT. Font DejaVu dan model YuNet disertakan dengan lisensinya.
`pycapcut==0.0.3` dipasang sebagai dependensi dan bukan API resmi CapCut.
