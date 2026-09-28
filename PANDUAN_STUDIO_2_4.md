# Clipper Studio Local 2.4

Pembaruan untuk instalasi Clipper Studio 2.x yang sudah berjalan. Fokusnya: tipografi yang lebih rapi, pemilihan cerita sesuai penonton, komposisi materi yang terbaca, serta B-roll kontekstual dari koleksi lokal atau API stok. Model Qwen/Whisper dan dependensi tetap memakai instalasi Anda.

## Pasang di Windows

1. Tutup server Clipper dengan **Ctrl+C** di terminal.
2. Ekstrak seluruh `Clipper_Studio_Local_2_4.zip` ke folder baru. Jangan jalankan installer dari dalam ZIP.
3. Jalankan **PASANG_UPGRADE.cmd**. Target bawaan: `C:\AI\clipper`. Lokasi lain: `PASANG_UPGRADE.cmd --target "D:\folder\clipper"` dari terminal di folder paket.
4. Di folder instalasi, jalankan **CEK_PRO.cmd**, kemudian **JALANKAN_PRO.cmd**.
5. Buka `http://localhost:8765`, tekan **Ctrl+F5**, lalu pastikan label **LOKAL · 2.4**.

Installer memeriksa seluruh file sebelum menyalin dan membuat cadangan otomatis di `steezy_backups`. Sesi, sumber, hasil, preset pribadi, koleksi/cache stok, konfigurasi dan `.venv` tidak ditimpa. Pemulihan: tutup server dan jalankan **PULIHKAN_PRO.cmd**. Jika file program telah Anda edit setelah memasang pembaruan, pemulihan berhenti agar edit itu tidak hilang.

Sesi lama dapat dibuka tanpa mengulang analisis. Pilih clip, atur gaya, lalu render ulang dari sumber asli. Output baru berakhiran `-v24`; MP4 lama tidak berubah. Untuk menerapkan sasaran penonton pada pemilihan seluruh topik, buat analisis baru. **Periksa AI** pada sesi lama memeriksa kandidat yang sudah ada.

## Alur yang disarankan

1. **Cerita:** pilih sasaran penonton. Dengarkan pembuka dan penutup; sesuaikan batas jika masih menggantung. Mode awal sesi baru menggunakan urutan asli, tanpa banner judul dan tanpa kutipan pembuka berulang. Pada sesi lama, matikan **Awali dengan kutipan dari sumber** jika masih tercentang.
2. **Tipografi:** buka **Pilih tampilan**, pilih preset, lalu tentukan font utama dan font penekanan. Ukuran ditampilkan dalam persen. Mulai dari 100% dan intensitas tenang.
3. **Visual:** pilih rasio, jenis sumber, komposisi, posisi blok teks dan perataan baris. Untuk 16:9, posisi kiri/kanan dipasangkan dengan rata kiri/kanan. Untuk 9:16, mulai dari bawah dengan rata tengah atau kiri. Posisi manual terkunci saat berganti template.
4. **Audio:** gunakan musik lokal dan volume rendah; musik akan diturunkan saat pembicara bersuara.
5. Klik **Simpan koreksi → Preview dari sini → Render pilihan**. Preview mulai dari posisi pemutaran sumber saat ini, maksimal 12 detik. Periksa juga hasil final.

### Enam preset

| Preset | Pasangan font | Penggunaan awal |
|---|---|---|
| Studio editorial | DM Sans + Bebas Neue | Pembicara, bisnis, edukasi; penekanan yang jelas |
| Editorial elegan | DM Sans + DM Serif Italic | Narasi tenang dan motivasi |
| Angka tegas | DM Sans + Bebas Neue | Angka/istilah penting, gerak lebih kuat |
| Ruang belajar | DM Sans + Montserrat | Penjelasan materi dengan slide ringan |
| Fokus lembut | DM Sans + DM Serif | Masuk blur singkat |
| Pop editorial | Montserrat + DM Serif Italic | Pop dan variasi yang lebih terasa |

Tujuh pilihan font tersedia beserta berkas dan lisensinya. Pemenggalan frasa mempertimbangkan jeda, tanda baca dan kata penghubung. Kata penting menggunakan ukuran/font berbeda tanpa selalu dipaksa menjadi baris sendiri. Perapian ringan hanya mengubah tampilan subtitle; transkrip sumber dan audio tidak ditulis ulang. Angka/waktu ucapan yang mencurigakan ditandai untuk didengarkan, bukan ditebak.

## Siapkan B-roll

Klik **B-roll & API** di bagian atas. Anda bisa memakai koleksi lokal saja, satu penyedia API, atau gabungannya. API key diisi sendiri di aplikasi; tidak perlu mengirimkannya lewat chat.

### Koleksi lokal

1. Siapkan folder, misalnya `D:\Broll`.
2. Gunakan nama yang menjelaskan gambar, misalnya `mengetik laptop.mp4`, `diskusi tim kantor.mp4`, atau `mencatat anggaran.mp4`. Subfolder ikut dicari.
3. Isi **Folder koleksi lokal** pada dialog B-roll, lalu simpan.

Opsional: `mengetik laptop.json` di samping video tersebut dapat berisi metadata berikut:

```json
{
  "title": "Mengetik di laptop",
  "tags": ["typing", "laptop", "mengetik", "pekerjaan"],
  "author": "Nama pembuat",
  "source_url": "https://halaman-asal-video",
  "license_url": "https://halaman-lisensi",
  "attribution": "Kredit yang perlu dicantumkan"
}
```

### API stok opsional

| Penyedia | Tautan akun/API | Perilaku aplikasi |
|---|---|---|
| Pexels | https://www.pexels.com/api/ | Pencarian video dengan orientasi hasil |
| Pixabay | https://pixabay.com/api/docs/ | Pencarian video; hasil pencarian dicache 24 jam |
| Coverr | https://coverr.co/developers | Gunakan akses Demo gratis; kuotanya lebih kecil |

Gunakan akses gratis yang tersedia di akun masing-masing. Aplikasi tidak memiliki alur pembelian, langganan, atau peningkatan paket. Kuota/key tidak cocok atau koneksi gagal akan ditampilkan; sumber asli tetap bisa dirender. Coverr memiliki paket Production berbayar yang tidak diperlukan untuk alur ini. Ketentuan layanan dapat berubah.

API key disimpan lokal dalam `.stock-settings.json` dan tidak ditampilkan kembali atau dimasukkan ke paket editor. Nama file tersebut otomatis ditambahkan ke `.gitignore` tanpa mengganti aturan Anda. Transkrip diproses oleh Ollama lokal; API stok menerima kata pencarian, bukan video sumber atau seluruh transkrip. Cache pencarian privat dapat memuat URL unduhan bertoken; folder `work` tetap merupakan data lokal dan tidak perlu diunggah ke GitHub.

### Terapkan pada clip

1. Buka tab **Visual → Ilustrasi B-roll**.
2. Pilih **Koleksi lokal saja** atau **Otomatis · lokal lalu API**. Bawaan adalah mati.
3. Mulai dengan maksimal **3 sisipan**. Batas kontrol 1–5; mesin boleh menghasilkan lebih sedikit atau tidak ada jika tidak cocok.
4. Klik **Siapkan ilustrasi clip ini**. Lihat preview, alasan pemilihan, waktu dan sumber. Hilangkan centang sisipan yang tidak sesuai.
5. Render. Anda juga bisa langsung render dan persiapan dijalankan otomatis.

Qwen mengusulkan pencarian berdasarkan konteks kalimat; pencocokan gambar belum memakai model vision. Sisipan singkat sekitar 2–3 detik menggunakan suara pembicara asli. Awal dan akhir clip dipertahankan. Materi/papan tulis yang terdeteksi tidak ditutup stok. Mode **Papan tulis / materi** mematikan sisipan sepanjang clip dan mempertahankan jeda menulis. Jadi, tidak setiap kata harus berubah menjadi gambar.

Tombol **Kredit stok** menyajikan sumber yang dipakai. Sertakan kredit yang diminta penyedia, terutama Coverr, pada deskripsi unggahan. Ini juga disertakan dalam paket editor.

## Materi dan podcast

Untuk gambar pembicara + papan, pilih **Materi + pembicara** dan tandai dua area bila deteksi otomatis kurang tepat. Format 16:9 menempatkan keduanya berdampingan dengan area subtitle tersendiri; format 9:16 menggunakan susunan vertikal. Jeda menulis dipertahankan saat opsi terkait aktif.

Mode podcast mempertahankan komposisi yang aman ketika beberapa wajah terdeteksi. Pembaruan ini belum memiliki identifikasi pembicara aktif berbasis suara. Bahan dua pembicara nyata masih perlu diuji; gunakan gambar utuh atau area manual jika framing otomatis kurang tepat.

## Output siap pakai dan proyek editor

| Output | Isi |
|---|---|
| MP4 | Gambar, B-roll, tipografi animasi, suara dan musik yang sudah digabung |
| ASS + SRT | ASS sebagai master animasi penuh; SRT untuk teks/waktu sederhana |
| Paket CapCut + DaVinci | Video dasar, B-roll terpisah, teks native, audio terpisah, font, ASS, kredit |

Setiap clip menjadi satu timeline pada paket. Video dasar tidak berisi B-roll atau subtitle yang sudah menyatu, sehingga sisipan dapat dipindah/dihapus. Framing dan zoom pada video dasar sudah dirender. CapCut juga memperoleh draft per clip sebagai cadangan bila format multi-timeline tidak terbaca. Buka `BACA_DULU.txt` di paket proyek untuk langkah impor/relink.

**ASS tidak otomatis menjadi layer animasi native.** Paket menyediakan ASS master dan membangun teks native terpisah. CapCut belum memetakan blur/fade secara identik; ukuran dan baseline font editor dapat berbeda. Impor interaktif CapCut 9.5 dan Resolve Free 21.0.4 belum bisa diuji di lingkungan ini. Efek penuh ada pada MP4/ASS; coba satu proyek sebelum produksi banyak clip.

## Kinerja dan pemeriksaan hasil

Tetap gunakan Qwen3:8b dan Whisper yang sudah bekerja di laptop Anda. Tidak ada model baru yang wajib diunduh. B-roll menambah waktu perencanaan, unduh awal, dan konversi aset pendek; hasil pencarian/media dapat dipakai ulang. Untuk VRAM 4 GB, tutup editor video saat menjalankan analisis/render. Target 30 menit bergantung panjang sumber, model, temperatur laptop, dan jumlah hasil; belum dibenchmark pada laptop Anda untuk versi 2.4.

Tes teknis tidak membuktikan retensi/FYP atau kelengkapan topik. Periksa pembuka/penutup, angka, keterbacaan papan, posisi subtitle, dan relevansi stok pada satu hasil asli. Laporan rinci: `TEST_REPORT_STUDIO_2_4.md`.
