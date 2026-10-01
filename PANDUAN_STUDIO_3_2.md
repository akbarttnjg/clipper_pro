# Clipper Studio Local 3.2

Upgrade untuk instalasi **3.1** dari `akbarttnjg/clipper_pro`, baseline commit `5d307201fe8f9e333df94fd8174eaa566febf370`. Paket ini berisi kode yang saling terhubung, font, contoh galeri, model wajah ringan, installer, dan pengujian.

## Pasang di Windows

1. Tutup server Clipper dengan **Ctrl+C** di terminalnya.
2. Ekstrak ZIP ini. Jangan jalankan langsung dari dalam ZIP.
3. Buka **PASANG_UPGRADE.cmd**. Isi folder instalasi lama yang berisi `app.py`, `clipper`, dan `.venv`—bukan folder `clips` atau folder paket upgrade.
4. Installer memeriksa checksum, mencadangkan file yang berubah ke `steezy_backups`, lalu memasang upgrade. Instalasi 3.1 yang sudah berfungsi tidak perlu mengunduh ulang Whisper/Qwen atau memasang dependensi baru.
5. Di folder aplikasi lama, jalankan **CEK_PRO.cmd**, kemudian **JALANKAN_PRO.cmd**. Buka `http://localhost:8765` dan tekan **Ctrl+F5** sekali. Badge harus menunjukkan **3.2**.

Alternatif lewat terminal di folder paket:

```bat
py -3 steezy_pro_installer.py --target "C:\AI\clipper"
```

Installer mempertahankan `.env`, `.env.pro`, `.venv`, API key, sumber video, sesi, koreksi, musik, dan hasil yang sudah ada. Pilih target instalasi Anda sendiri jika lokasinya berbeda. Jangan menyalin `payload` secara manual bila ingin pencadangan dan pemulihan otomatis.

## Pengaturan awal yang disarankan

Klik **+ Video baru**. Biarkan **Jangkauan pencarian: Luas** dan **Batas hasil: 0 (adaptif)**. Angka nol berarti mengambil cerita unik yang lolos pemeriksaan, bukan memaksakan jumlah tertentu. Pilih 9:16 atau 16:9 dan durasi 30–120 detik. Bagian yang diperlukan untuk menutup topik boleh melewati batas sampai 20 detik dan diberi keterangan.

Mode otomatis memeriksa cerita, merender yang lolos, lalu menyiapkan paket editor. Mode tinjau berhenti pada kandidat agar Anda dapat memeriksanya dahulu. Kandidat meragukan tetap ditampilkan. Satu kegagalan jawaban AI tidak lagi menghentikan pencarian bagian akhir video; tiga kegagalan koneksi/timeout berurutan menghentikan panggilan agar tidak menunggu tanpa batas, dan cakupan yang belum diperiksa dicatat.

Di sesi lama, gunakan **Cari pembahasan lain** untuk menjelajah dengan transkrip tersimpan. Tombol ini menambahkan kandidat baru tanpa mengganti koreksi atau hasil clip lama. Jika sumber pernah gagal dianalisis, jendela yang berhasil akan dipakai kembali dan bagian yang gagal dicoba lagi. Kamus saat membuat sesi baru memberi petunjuk langsung ke Whisper; sesi lama memakai transkrip yang sudah tersimpan.

## Kata lebih rapi

Pada **Bahasa & koreksi istilah** saat membuat sesi, isi kamus seperti ini:

```text
XAUUSD = hausd | xausd
NamaProduk = nama prodak
```

Satu istilah per baris. Tanda `=` memisahkan ejaan benar dan alias; `|` memisahkan beberapa alias. Jangan memasukkan kalimat/parafrasa. Alias yang Anda tulis eksplisit dianggap sebagai instruksi penggantian, jadi gunakan istilah yang tidak ambigu. Kamus menolak perubahan angka dan kata penyangkalan/kepastian.

Koreksi bawaan seperti `hausd → XAUUSD` memakai konteks trading/emas, atau sasaran edukasi keuangan. Kata yang Anda koreksi manual tidak ditimpa. Whisper juga dapat mendengarkan ulang maksimal 12 cuplikan berkeyakinan rendah; hanya alternatif ejaan dengan waktu yang sesuai dan keyakinan lebih kuat yang diterima. Model dilepas sebelum Qwen bekerja untuk mempertahankan alur proses berurutan pada GPU 4 GB.

Pada tab **Cerita**, tersedia **Tanda baca pada layar: Minimal**, kamus per clip, dan **Bandingkan teks sebelum/sesudah**. Titik/koma di tepi kata disembunyikan pada subtitle; angka seperti `1.250,50`, `1,5%`, tanda minus, serta kata `tidak`/`bukan` tetap dijaga. Tanda tanya tetap ada. Transkrip mentah dan catatan koreksi disimpan. Garis bawah bertitik menandai kata yang perlu didengarkan; klik kata untuk memutar sumbernya. Koreksi teks tidak mengubah suara asli.

## Posisi dan gaya subtitle

Gaya awal **Editorial bertingkat** memakai kata penghubung lebih kecil, pasangan sans/serif, dan penekanan lebih besar. Font utama, font penekanan, intensitas, ukuran, dan warna tetap dapat dipilih. Preset pribadi tetap didukung. Tidak ada banner judul pembuka.

Di tab **Visual**, pilih **Posisi blok teks: Otomatis** dan aktifkan **Cari ruang kosong, hindari wajah & tulisan**. Mesin memeriksa wajah dan pola goresan tulisan pada beberapa frame, memetakan area tersebut ke komposisi hasil, lalu memilih area subtitle yang tetap selama adegan. Jika area penuh, mesin menyisihkan jalur subtitle dan menyesuaikan gambar. Sisipan B-roll juga mempertahankan jalur tersebut pada MP4 dan media proyek editable. Area pembicara pada susunan vertikal dipertahankan utuh.

Deteksi tulisan ini berbasis bentuk/pola visual, bukan pembacaan OCR isi papan. Wajah menyamping, gerakan cepat, atau tulisan sangat kecil bisa terlewat. Gunakan **Tandai materi** / **Tandai pembicara** untuk sumber sulit. Pilihan posisi manual tetap mengunci posisi Anda. Perataan baris diatur terpisah. **Preview dari sini** membuat contoh 12 detik dari posisi sumber saat ini; preview identik dipakai ulang dari cache.

## Folder hasil dan cache

Hasil baru disimpan di `clips/<id-proyek>/`:

| Folder | Isi |
|---|---|
| `video` | MP4 hasil terbaru |
| `subtitles` | ASS dan SRT |
| `reports` | QC teknis, catatan subtitle, dan kredit stok |
| `projects` | Folder serta ZIP proyek editable |
| `history` | Render terdahulu setelah diganti revisi baru |

Jika render lama masih dikunci pemutar/editor di Windows, file tetap berada di folder semula agar render baru tidak gagal. Transkrip, sesi, rencana edit, dan audio untuk ekspor tetap berada di `work`; jangan menghapus seluruh folder tersebut.

Klik **Folder & cache** di bagian atas:

- **Hapus cache preview** membersihkan preview sementara versi baru dan preview lama yang pola namanya dikenali. Ukurannya ditampilkan sebelum dihapus. Hasil final, transkrip, koreksi, sumber, model, dan audio proyek dipertahankan. File yang sedang terkunci dilewati; tutup pemutar lalu coba lagi.
- **Rapikan hasil lama** memindahkan MP4/subtitle/laporan yang dikenali dari sesi tersimpan ke folder proyeknya. Tautan hasil lama tetap dapat dibuka di 3.2. File tanpa sesi yang dikenali dan paket ekspor lama tidak dipindahkan.

Pembersihan ditolak selama ada pekerjaan video aktif atau dalam antrean.

## Ekspor dan pemulihan

**Paket CapCut + DaVinci** memakai render terbaru dan berisi media tanpa teks, subtitle, audio terpisah, B-roll, serta proyek/timeline. ASS menjadi acuan tampilan tipografi. Pembuatan paket sudah diuji, tetapi impor native pada CapCut Desktop 9.5.0 dan DaVinci Resolve Free 21.0.4 belum dijalankan di lingkungan Windows tersebut. Baca `BACA_DULU.txt` di paket editor; periksa satu clip sebelum mengimpor seluruh sesi.

Untuk kembali ke kode sebelum upgrade, tutup server lalu jalankan **PULIHKAN_PRO.cmd** dari folder aplikasi. Pemulihan menolak menimpa kode yang berubah setelah pemasangan. Pemulihan mengembalikan kode, bukan menghapus hasil atau mengembalikan koreksi pengguna. Hasil 3.2 yang sudah berada di subfolder tetap dapat dibuka langsung dari File Explorer; UI 3.1 lama belum memahami susunan folder baru.

## Batas pengujian

Baca `TEST_REPORT_STUDIO_3_2.md` untuk rincian. Pengujian kode, API, UI, render dua rasio, pembentukan paket editor, serta installer/pemulihan dilakukan di Linux. Belum ada pengukuran akurasi transkrip/seleksi Qwen pada sumber panjang Anda atau pengukuran waktu di RTX 3050 4 GB. Jumlah hasil tidak dijamin sama dengan Opus/Vizard, dan tidak ada janji selesai 30 menit. Contoh di folder `contoh` memakai gambar dan audio sintetis untuk menunjukkan tata letak, bukan benchmark model atau hasil final video Anda.
