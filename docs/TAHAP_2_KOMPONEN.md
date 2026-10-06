# Clipper Studio 4.0.2 — Pengelola komponen dan perangkat

Versi ini mengerjakan tahap 2 dari laporan upgrade: komponen, pemasangan,
worker, antrean GPU, kalibrasi, dan pemulihan lingkungan. Fondasi ekspor dari
4.0.1 ikut disertakan. Backend CapCut utama tetap memakai implementasi yang
sudah bekerja. Perbaikan teks/font native DaVinci dijadwalkan kemudian.

## Cara mulai setelah upgrade

1. Tutup aplikasi Clipper lama. Ekstrak ZIP upgrade ke folder pendek.
2. Jalankan `CEK_SEBELUM_UPGRADE.cmd` dengan folder mesin yang sekarang dipakai.
3. Jalankan `UPGRADE_TAHAP_2.cmd` ke folder yang sama.
4. Jalankan `JALANKAN_PRO.cmd` dari folder mesin tersebut, lalu muat ulang browser.
5. Buka **Komponen & perangkat** pada header.
6. Tekan **Kalibrasi perangkat**. Ini membaca perangkat komputer Anda dan
   mengukur encode pendek; hasil server pengembangan tidak dijadikan hasil laptop.
7. Daftarkan FFmpeg dan libass dahulu. Lihat hasil video/frame sampelnya.
8. Pasang komponen berikutnya satu per satu. Mulai dari FontTools, OpenTimelineIO,
   PySceneDetect, YuNet, atau RapidOCR sesuai kebutuhan. Hindari memasang seluruh
   komponen sekaligus; setiap venv menyimpan dependensinya sendiri dan bisa besar.
9. Untuk faster-whisper, pilih `small` untuk uji awal atau `medium` agar sesuai
   pilihan model proyek lama. Isi path video/audio yang mengandung ucapan,
   jalankan **Uji sampel**, lalu tinjau JSON kata dan timestamp.
10. Transcriber baru dipakai produksi hanya setelah **Aktifkan transcriber
    terisolasi**. Modelnya harus sama dengan model pada proyek. Proyek yang memakai
    model lain terus menggunakan transcriber utama. Pilihan model tidak berubah
    otomatis. Generasi baru harus diuji dan diaktifkan lagi.

`Periksa runtime` menguji impor/prasyarat, sedangkan `Uji sampel` menjalankan
operasi contoh. Angka **lolos sampel** tidak menghitung impor modul, dokumentasi,
atau build JavaScript. Lolos sampel menunjukkan operasi tersebut bekerja pada
perangkat yang mengujinya; itu bukan nilai akurasi atau kualitas klip.

## Pemetaan pekerjaan tahap 2

| Tugas laporan | Implementasi versi ini | Bukti yang diperiksa |
|---|---|---|
| 11 — Katalog 26 | Identitas, fungsi, sumber kode/bobot, versi rencana/terpasang, platform, runtime, status dan hasil uji | Katalog tepat 26, status berdasarkan receipt dan uji aktual |
| 12 — Installer | Worker, rencana yang dikunci, unduh Range/If-Range, hash, progress, disk, cancel/resume | Uji unduhan terputus, Range diabaikan/salah, hash salah, disk kurang |
| 13 — Isolasi | Venv per komponen; proses ASR/visual/TalkNet/SAM/Node/eksperimen terpisah | Kegagalan uji tidak mengaktifkan generasi baru; API tetap membaca status |
| 14 — GPU | Lease SQLite lintas proses, identitas PID/start time, antrean produksi dan sampel | Dua proses dan dua thread tidak masuk bersamaan; pemilik mati dipulihkan |
| 15 — Kalibrasi | CPU/RAM/disk/driver/VRAM, encode CPU/NVENC, waktu uji dan sampling VRAM | Benchmark nyata pada komputer yang menekan kalibrasi; model belum diuji tetap belum dinyatakan aman |
| 16 — Remotion | Versi 4.0.533, Node portabel Windows bila diperlukan, komposisi React, still PNG dan MP4 | Uji render dijalankan setelah pemasangan lokal, bukan dicentang dari katalog |
| 17 — TalkNet/SAM | Source commit, bobot, worker CPU/CUDA, fixture skor/mask | Harus lolos uji pada perangkat; status awal belum teruji |
| 18 — Pembanding | Stable-ts, WhisperX, ClipsAI, Auto-Editor, Motion Canvas bisa dipanggil tersendiri | Output sampel tidak mengganti kandidat/hasil/setting produksi |
| 19 — Akses | Ketersediaan kunci provider dan Opus; dokumen skill resmi terpisah | Kunci tersedia tidak dianggap bukti akses jaringan; tidak ada unggahan/job Opus berbayar |
| 20 — Kunci & rollback | Plan, pip report/freeze, npm lock, commit dan hash bobot; pointer generasi sebelumnya | Backup diubah/tampered ditolak; proyek dan koreksi manual tidak disentuh |

## Katalog dan lingkup uji

| No. | Komponen | Uji / keluaran yang disediakan |
|---:|---|---|
| 1 | FFmpeg / ffprobe | MP4 320×180 1 detik lalu probe stream |
| 2 | libass | PNG dengan teks subtitle melalui filter FFmpeg |
| 3 | FontTools | Font asli mesin dibaca dan glyph contoh diperiksa |
| 4 | faster-whisper | Ucapan 6 detik → teks, kata, timestamp; small/medium terkunci |
| 5 | Silero VAD | Audio 6 detik → interval ucapan |
| 6 | WhisperX | Backend ASR pada cuplikan; alignment bahasa tidak otomatis menjadi bukti lulus |
| 7 | Stable-ts | Transkripsi/timestamp pembanding dengan bobot small lokal |
| 8 | pyannote.audio | Cuplikan → interval/identitas pembicara; akses model gated diperlukan |
| 9 | PySceneDetect | Video hitam/putih buatan → pergantian adegan |
| 10 | OpenCV + YuNet | Inference pada gambar kosong; bukan nilai akurasi wajah |
| 11 | RapidOCR | Gambar teks contoh → teks hasil OCR |
| 12 | multilingual E5 small | Dua teks → embedding lokal yang valid |
| 13 | Qwen3 lokal | Inventaris model/digest; inference singkat lalu unload |
| 14 | Qwen3-VL 2B | Deskripsi gambar buatan; CPU awal, CUDA opsional dengan fallback |
| 15 | SmolVLM 500M | Deskripsi gambar buatan sebagai pembanding |
| 16 | SigLIP 2 | Similarity gambar dan dua teks |
| 17 | TalkNet-ASD | Checkpoint + audio/visual tensor buatan → 25 skor |
| 18 | SAM 2.1 tiny | Prompt titik → PNG mask gambar buatan |
| 19 | Remotion | Preview PNG dan MP4 24 frame |
| 20 | Remotion official skills | Dokumen sumber dan commit; bukan renderer tambahan |
| 21 | Motion Canvas | Build contoh animasi; render browser belum dinyatakan terverifikasi |
| 22 | OpenTimelineIO | Tulis/baca timeline 24 frame |
| 23 | pyCapCut | Draft JSON dengan track teks; bukan pemeriksaan impor native |
| 24 | ClipsAI | ClipFinder dan RoBERTa asli pada transkrip contoh; kandidat JSON |
| 25 | Auto-Editor | Cuplikan audio → keputusan potong/timeline Premiere XML |
| 26 | OpusClip skill | Dokumentasi dan CLI resmi disimpan; API berbayar tidak dijalankan |

Semua komponen berat membutuhkan internet pada pemasangan pertama. Model yang
didukung loader Transformers diunduh sebagai berkas konfigurasi/tokenizer/bobot;
kode model Python remote tidak dijalankan (`trust_remote_code=False`).

## Apa yang sudah diuji di lingkungan pengembangan

- Pengelola, API, cancel/resume, hash/range unduhan, rollback, dan lease GPU
  diuji dengan operasi aktual pada fixture dan proses terpisah.
- Sampel FFmpeg, libass, FontTools dan pyCapCut dijalankan menggunakan komponen
  yang tersedia di lingkungan pengujian.
- Worker antrean benar-benar memasang/mendaftarkan FFmpeg dan menjalankan
  kalibrasi CPU. NVENC yang tidak tersedia dicatat gagal, tidak diubah menjadi lulus.
- Pengujian proyek/revisi/ekspor tahap 1 dijalankan kembali.
- Bukti rinci, jumlah tes, dan hasil paket tersedia di folder `verification`
  pada ZIP. Status aplikasi setelah upgrade berasal dari komputer pengguna,
  sehingga tidak membawa centang hasil uji server sebagai hasil laptop.

**Belum diverifikasi di ASUS TUF Anda:** instalasi/model berat, CUDA RTX 3050
4 GB, wheel native Windows/WSL, browser Remotion/Motion Canvas, dan performa
video panjang. ZIP berisi resep dan worker untuk mengujinya, bukan seluruh
bobot atau klaim 26 komponen sudah lolos. Instalasi penuh tahap 2 perlu ditinjau
dari laporan perangkat yang dihasilkan setelah Anda menjalankan panel.

## Resume, disk, dan versi

- **Lanjutkan rencana yang sama** memakai ID job dan plan yang sama. Commit
  sumber/model dan versi paket tidak diambil ulang ketika plan sudah tersimpan.
- Bobot/sumber besar memakai `.part`, Range/If-Range, pemeriksaan ukuran dan
  SHA-256 atau Git blob SHA-1 sebelum dipindahkan menjadi berkas lengkap.
- Jika server mengabaikan Range, unduhan dimulai lagi dengan benar. Jika
  checksum berbeda, berkas tidak diaktifkan. Jika sumber gated menolak,
  komponen menampilkan kegagalan akses yang dapat diperbaiki lalu dilanjutkan.
- Pip memakai cache wheel, checkpoint pemasangan yang selesai, dan `pip
  --report`. Resume byte parsial pada unduhan internal pip tidak dijamin.
- Versi root paket yang tidak sudah dipatok di resep diambil dari rilis stabil
  PyPI ketika plan dibuat. Dependensi hasil resolver dikunci di `installed-lock.txt`
  dan `pip-report.json`. Paket Node memakai `package-lock.json`. Ini kunci per
  lingkungan yang berhasil dipasang, bukan klaim satu kombinasi universal
  sudah diuji pada seluruh versi Windows/Python.
- Node LTS 22 portabel Windows berasal dari distribusi resmi dan diverifikasi
  terhadap `SHASUMS256.txt`; tidak mengganti Node/Python global. Jika Node
  yang kompatibel sudah ada, worker memakai instalasi itu.
- Python 3.10–3.12 dipakai untuk komponen riset. Jika mesin utama memakai
  Python lebih baru, installer mencari Python 3.11/3.12/3.10 berdampingan.
- Perkiraan GB merupakan anggaran awal, bukan total pasti. Bobot diukur dari
  metadata sumber; paket, cache dan browser bisa memerlukan ruang tambahan.
- TalkNet resmi menyediakan Google Drive ID tetapi tidak menerbitkan checksum.
  Hash unduh pertama dicatat untuk pemulihan berikutnya; ini tidak setara
  checksum yang diterbitkan upstream. Loader menggunakan `weights_only=True`.

## Antrean GPU dan profil perangkat

Pekerjaan berat produksi dan uji komponen memakai satu lease lintas proses.
Lease tidak kadaluarsa hanya karena proses lama: pemilik harus berhenti atau
identitas PID/start time berbeda sebelum lease dipulihkan. Lease ini mengatur
pekerjaan Clipper; aplikasi lain yang menggunakan GPU tetap di luar antrean.

Worker ASR/model berakhir untuk melepaskan tensor lokal. Qwen3/vision Ollama
yang dipanggil oleh Clipper memakai pelepasan model pada batas pekerjaan.
Jika uji CUDA gagal karena runtime/VRAM, worker mencoba CPU dan menyimpan
penyebab serta pengukuran percobaan yang gagal. Fallback ditampilkan di panel.

Kalibrasi mengukur 60 frame 640×360 untuk CPU dan NVENC. Sampling VRAM memakai
`nvidia-smi` tiap 0,75 detik, termasuk pemakaian aplikasi lain; ini bukan angka
alokasi eksklusif model. Model yang selesai sebelum interval sampling dapat
memiliki puncak yang tidak tertangkap. Belum ada klaim throughput video panjang.

Profil `fast`, `balanced`, dan `detail` memakai satu worker/batch 1 dan ukuran
gambar uji berbeda. CUDA ASR direkomendasikan hanya jika uji sampel CUDA ASR
sendiri lulus. Encode NVENC yang lulus tidak otomatis membuktikan model muat.
Profil mengatur worker opsional; setting kreatif dan model proyek tidak berubah
otomatis. Uji ulang dan kalibrasi ulang setelah menambah model yang penting.

## Komponen khusus dan akses

- SAM Windows menggunakan CPU tanpa ekstensi CUDA/postprocessing untuk awal.
  Jalur CUDA penuh di WSL membutuhkan lingkungan, driver, dan uji tersendiri.
  Versi ini tidak otomatis memasang WSL atau memindahkan aplikasi ke WSL.
- pyannote memerlukan persetujuan `speaker-diarization-3.1` dan
  `segmentation-3.0` pada akun Hugging Face. Masukkan `HF_TOKEN` di `.env.pro`
  lokal lalu restart. Model embedding dan segmentation dikunci dan dimirror
  ke cache privat untuk inference offline; format checkpoint tetap diuji lokal.
- ClipsAI menjalankan backend ClipFinder, menghindari impor facade WhisperX
  lama yang tidak diperlukan untuk pencarian klip. Embedding RoBERTa yang
  dipakai backend asli dibaca dari bobot lokal. Ia tidak memakai NLTK network
  download sebagai efek samping impor. Ini pembanding, bukan backend default.
- WhisperX sample menguji ASR; forced alignment bahasa memerlukan model dan
  pengujian tersendiri. Hasil sampel ASR tidak diberi label alignment lulus.
- Motion Canvas memiliki proyek contoh, Vite config, dan build checker. Setelah
  dipasang, proyek berada pada folder `node` generasi komponen; untuk preview
  editor jalankan Node lokal dengan `node_modules/vite/bin/vite.js --host
  127.0.0.1`. Render/browser dan perbandingan kreatif masih harus ditinjau.
- Pexels/Pixabay/Coverr menampilkan apakah kunci tersedia. Kunci tersebut
  tidak dibocorkan melalui API/log. Provider baru tidak otomatis digunakan
  pipeline; Pexels lama mengikuti setting proyek. Akses jaringan belum diuji
  hanya karena kunci ditemukan.
- OpusClip skill adalah konektor layanan dengan akses akun. Versi ini hanya
  mengunduh dokumentasi dan CLI; tidak mengunggah video, membuat job berbayar,
  atau mengirim posting. Tidak ada biaya API yang dijalankan installer.

## Pemulihan dan laporan untuk pemeriksaan berikutnya

Pilih **Pulihkan generasi sebelumnya** untuk mengganti pointer komponen.
Checksum sumber/bobot/lock generasi cadangan diperiksa dahulu. Lingkungan utama,
file sumber, render, subtitle, draft CapCut, dan koreksi manual tidak dihapus.
Cache/generasi tetap disimpan sehingga versi yang lama dapat diuji kembali.
Rollback komponen tidak memulihkan binary FFmpeg/Ollama eksternal atau versi
driver yang diubah melalui installer lain.

Untuk membatalkan upgrade kode seluruh aplikasi, gunakan
`PULIHKAN_UPGRADE_TAHAP_2.cmd` dan folder backup yang dicetak installer.
Jangan memakai rollback komponen untuk membatalkan upgrade kode: keduanya
memiliki backup berbeda. Installer kode menolak menimpa perubahan lokal yang
tidak dikenal; simpan kode kustom bila pemeriksaan awal memberi konflik.

Setelah instalasi/uji lokal, klik **Unduh laporan perangkat**. JSON berisi
status 26 komponen, versi aktual, waktu/lingkup uji, fallback, perangkat, dan
status job. Kunci API tidak disertakan. Laporan ini membantu menetapkan model
yang benar-benar layak pada VRAM 4 GB sebelum tahap 3–5 meningkatkan hasil klip.

## Perintah alternatif

Jalankan dari folder mesin dengan Python `.venv` yang sama dengan aplikasi:

```bat
.venv\Scripts\python.exe -m clipper.runtime.cli status
.venv\Scripts\python.exe -m clipper.runtime.cli calibrate
.venv\Scripts\python.exe -m clipper.runtime.cli install ffmpeg
.venv\Scripts\python.exe -m clipper.runtime.cli install faster-whisper --model small
.venv\Scripts\python.exe -m clipper.runtime.cli sample faster-whisper --source "C:\Video\sumber.mp4" --device cpu
```

Jika `WORK_DIR` kustom, gunakan `--root "path\work\runtime"` yang sama dengan
aplikasi. Panel aplikasi merupakan jalur utama agar folder/kunci dari `.env.pro`
dan antrean mengikuti konfigurasi mesin yang dipakai.
