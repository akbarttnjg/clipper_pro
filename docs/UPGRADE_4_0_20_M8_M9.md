# Clipper Pro 4.0.20 - Paket gabungan M8 dan M9 lokal

Paket ini memasang M8 beserta fondasi operasional M9 pada mesin M7 4.0.18 yang Anda unggah ke GitHub, commit `f6f1f6a11631f800c1749f8cb6fbcae6dfff384d`. Tidak perlu memasang paket M8 terpisah. Riwayat M0-M7 tetap menjadi dasar mesin; paket ini tidak berisi video pribadi, model, token, font pribadi, atau environment Anda.

**Cakupan M9 belum memenuhi seluruh milestone arsitektur.** Sebanyak 45 kebutuhan M9 ditelusuri satu per satu: 7 tersedia lokal, 9 mempunyai adapter bersyarat, 18 baru sebagian, dan 11 belum diimplementasikan. Angka ini menunjukkan cakupan, bukan nilai mutu atau persentase acceptance. Rincian terikat kode ada di `M9_REQUIREMENTS.json`. M8 mempunyai 44 kebutuhan: 26 lokal, 8 bersyarat, 9 sebagian, dan 1 terblokir.

## 1. Pemasangan Windows

1. Ekstrak ZIP ke folder baru di luar folder mesin Clipper.
2. Hentikan antrean dan capture. Sesi M9 yang sudah ada harus final atau dijeda melalui kontrol host. Rekonsiliasi inference eksternal yang belum selesai. Hentikan server, worker CLI dan jendela `JALANKAN_PRO.cmd`; tunggu lease M8 berakhir.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`. Pilih folder mesin yang berisi `app.py`, `.venv`, dan `JALANKAN_PRO.cmd`.
4. Jika pemeriksaan lulus, jalankan `PASANG_M8_M9_4_0_20.cmd` pada folder paket. Isi folder mesin yang sama.
5. Installer memeriksa SHA payload dan dasar kode, mencadangkan kode serta SQLite, memasang file, lalu memeriksa import dengan Python mesin. Jika salinan/probe gagal, kode dipulihkan otomatis.
6. Jalankan `JALANKAN_PRO.cmd` yang berada di mesin lama. Tekan Ctrl+F5 pada browser. Header harus menampilkan versi 4.0.20 M8-M9.
7. Jalankan `CEK_M8_M9_RUNTIME.cmd` dari paket untuk memeriksa import/filter. Pemeriksaan ini belum membuktikan perangkat, akun, atau model neural berhasil.

Jangan menyalin isi `payload` secara manual. Jika dasar kode berbeda, installer menolak menimpa. Cocokkan mesin/commit terlebih dahulu; jangan menghapus pemeriksaan checksum. Paket menerima dasar M7 yang diverifikasi dan file M8 dari producer yang dipatok, bukan modifikasi bebas.

`work`, `clips`, `uploads`, `.venv`, `ClipperModels`, `models`, dan `clipper/fonts` dipertahankan. Dependensi/model opsional tidak diunduh otomatis. SQLite memakai tabel tambahan M8/M9; source/transkrip lama tidak dimigrasikan diam-diam menjadi konten generatif. Pipeline render inti tetap `4.0.18-m7` karena perilaku final M0-M7 tidak diganti.

## 2. Mulai memakai M8

Klik **Distribusi & workspace M8** di header atau buka `/m8` pada origin mesin yang sama.

Alur awal yang dapat dipakai tanpa akun: pilih final M7 yang masih berlaku, buat profil **handoff**, buat draf, periksa preflight, kemudian setujui hash draf. Worker menghasilkan ZIP video, subtitle, cover dan metadata. Status `handoff_ready` berarti paket siap untuk unggahan manual; itu bukan bukti video telah diposting.

YouTube langsung bersifat pilihan. Google Desktop OAuth, project API/consent, scope, kepemilikan channel, dan credential vault harus siap. Credential Windows memakai DPAPI untuk pengguna Windows yang menjalankan mesin. Pada non-Windows, `cryptography` dan kunci eksternal `CLIPPER_M8_VAULT_KEY` 32 byte base64 diperlukan. Kunci tidak disimpan bersama data oleh aplikasi. Jangan membagikan backup credential atau menaruh kunci di GitHub.

Metadata, akun, revisi dan hash output dibekukan saat draf dibuat. Jika salah satunya berubah, draf harus diperiksa/disetujui ulang. Kehilangan respons upload ditangani lewat rekonsiliasi sesi, bukan membuat video kedua. Jadwal lokal memerlukan komputer dan worker tetap aktif; sleep/mati/offline berarti jadwal tertunda. Paket ini tidak menyediakan hosting selalu hidup.

Analytics membedakan nilai 0 dan belum tersedia. Pengukuran API dan impor manual mempunyai provenance serta periode tersendiri. Eksperimen observasional tidak dinyatakan sebagai bukti sebab-akibat. Skor drop-off terkalibrasi, API Meta langsung, unggahan thumbnail/subtitle live, SSO, dan cloud sync masih terbuka. Panduan M8 internal lebih rinci ada di `docs/UPGRADE_4_0_19_M8.md`; gunakan installer 4.0.20 untuk paket gabungan ini.

## 3. Rekaman M9 lokal

Klik **Rekaman & studio M9**. Halaman dibuka di tab terpisah agar editor dapat tetap digunakan. Buka melalui origin `http://127.0.0.1:PORT` atau localhost yang sama, bukan membuka HTML dari Explorer.

1. Beri nama, pilih Lokal, dan nyatakan izin merekam. Klik Buat sesi.
2. Pilih mikrofon, layar/slide, kamera, serta audio sistem bila diperlukan. Audio sistem bergantung pada browser, OS dan pilihan berbagi layar; tidak dianggap tersedia jika browser tidak memberikannya.
3. Pilih perangkat atau gunakan pemilih browser. Setujui capture track Anda, lalu klik Mulai merekam.
4. Izinkan akses melalui dialog browser. Layar, kamera, mikrofon dan audio sistem direkam terpisah.
5. Chunk disimpan dahulu di IndexedDB browser lalu diunggah dengan sequence dan SHA. Server menulis atomik dan fsync sebelum mengakui penerimaan. Cadangan browser tidak dihapus otomatis setelah ACK.
6. Klik Hentikan dan simpan. Bila jaringan terputus, gunakan Pulihkan unggahan lokal pada browser/profil/origin yang sama. Jangan menghapus site data/private session sebelum hasil diverifikasi.
7. Periksa rekaman. Semua track harus sealed dan jumlah chunk lengkap. Pilih layar/slide atau track host sebagai utama. Kamera host dapat ditempatkan di panel terpisah; seluruh frame materi diperkecil dengan padding, bukan dipotong.
8. Dengarkan sinkronisasi, periksa offset dan backstage, lalu setujui finalisasi. Worker serial merangkai byte fragment, mengonversi track, melakukan full decode, membuat program dan arsip original terpisah.
9. Hasil otomatis menjadi proyek sumber di editor. Pilih proyek tersebut lalu jalankan analisis/transkripsi secara eksplisit. Tidak ada ASR palsu yang dibuat dari nama file atau naskah.

Panjang rekaman tidak dihitung dari jumlah chunk. Timebase memakai durasi/timestamp media yang didekode ditambah offset start yang dicatat. Jam tamu adalah estimasi dengan ketidakpastian; periksa drift pada awal, tengah dan akhir. Offset manual tersedia melalui `m9.record.offset` dengan alasan sebelum finalisasi.

Batas: chunk transport 25 MiB, fragment browser 8 MiB, maksimum 10.000 chunk per track, 18 track, 6 peserta, 30 GiB per sesi dan cadangan ruang disk 1 GiB. Sebelum finalisasi, sediakan ruang tambahan setidaknya tiga kali ukuran chunk ditambah 1 GiB untuk track/program/arsip. Browser dapat mempunyai quota lebih rendah. Capture panjang 1-2 jam pada perangkat Anda belum diuji. Tutup aplikasi berat, lakukan uji pendek dahulu dan jaga penyimpanan browser/disk mencukupi.

Jika browser crash, hanya byte yang sudah disimpan dapat dipulihkan. Unggah ulang cadangan, periksa chunk berurutan, lalu gunakan kontrol **Tutup prefix pemulihan** secara eksplisit bila chunk akhir hilang. Prefix tidak dinyatakan sebagai rekaman utuh. Jika mux/decode tidak berhasil, original fragment tetap disimpan; unduh cadangan lokal untuk inspeksi. Jeda sesi menutup akses unggahan tanpa menghapus track. Pemulihan sesi membuka kembali tahap finalisasi, bukan mengembalikan data yang belum tersimpan.

## 4. Room tamu dan backstage

Room saat ini menyediakan perekaman tamu dan unggahan progresif. **Belum ada percakapan WebRTC/monitor langsung, STUN/TURN, live broadcast atau multistream.** Gunakan sarana komunikasi Anda sendiri bila membutuhkan percakapan saat rekaman.

Host membuat undangan dari kontrol rekaman. Tautan ditampilkan sekali dan disalin/dikirim sendiri oleh pengguna. Aplikasi tidak mengirim pesan ke tamu. Token berada dalam fragment, bukan query URL; server menyimpan hash, masa berlaku dan status pencabutan. Tamu hanya dapat mengirim track miliknya pada room undangan; token ini tidak memberikan akses workspace/editor.

Di luar localhost, room memerlukan mode server eksplisit, host yang diizinkan, HTTPS, dan deployment yang Anda kelola. Lihat `CLIPPER_M8_SERVER_MODE=1` serta `CLIPPER_M8_ALLOWED_HOSTS`. Server lama tidak dibuka begitu saja ke LAN/internet. Jangan menganggap tautan localhost dapat dibuka tamu dari komputer lain. Tidak ada tunnel/hosting yang dipasang paket ini.

Tamu mulai backstage. Host menekan Masukkan ke program untuk membuka interval audio; menonaktifkannya menutup interval. Program memakai interval tersebut. **Arsip track original dan stem host tetap dapat mengandung percakapan backstage.** Periksa sebelum membagikan arsip/paket podcast. Tamu tidak menjadi visual utama otomatis; layout panel kamera saat ini hanya kamera host.

## 5. Paket podcast dan potongan

Pada tab Paket podcast, pilih proyek episode, tentukan bab berurutan dengan bab pertama 0, isi notes dan pilih aset cover M9. Jika cover kosong, paket memakai gambar placeholder yang jelas. Hasil ZIP berisi WAV PCM 48 kHz, bab JSON, notes, cover, manifest SHA, serta stem bila sumber berasal dari rekaman M9.

Bab/notes/audio merujuk proyek dan revisi sama. Perubahan revisi saat proses berjalan membatalkan publikasi hasil lama. Stem original disertai offset; tidak disamakan dengan mix program yang telah membuang backstage. Ini paket lokal untuk host, bukan pengiriman otomatis ke layanan podcast.

Potongan rekaman tersedia setelah rekaman final. Rentang awal/akhir menghasilkan proyek baru dengan lineage source-time. Clipping buffer selama capture/live belum tersedia.

## 6. Tulisan, co-editor dan narasi

Tulisan manual dapat disimpan sebagai script/storyboard terpisah. Summary, notes, blog dan copy memerlukan sumber transkrip aktif. Draf selalu dilabeli sintetis/parafrasa dan klaim baru harus ditinjau.

Ollama lokal dapat membuat draf dengan referensi segmen/kata. Co-editor hanya boleh mengusulkan pengaturan subtitle/audio terbatas atau timeline. Tombol Tinjau membuat draft/diff editor inti; tidak auto-apply, tidak menghubungkan akun, dan tidak memposting. Jika revisi berubah, usulan harus dibuat ulang. Prompt transcript diperlakukan sebagai data.

Piper membutuhkan executable lokal, model `.onnx` dan konfigurasi berdampingan `nama-model.onnx.json`, bahasa yang cocok, lisensi dan izin suara. Jalur, executable dan model dipatok dengan SHA. Jangan mendaftarkan runtime/model yang tidak Anda percayai. Tidak ada pelatihan atau voice cloning di paket ini.

Sebelum TTS, periksa seluruh tulisan; persetujuan terikat SHA teks dan versi profil suara. WAV hasil diperiksa/didekode dan menjadi proyek audio sintetis baru. Dengarkan angka, negasi, nama, pelafalan bahasa dan izin sebelum dipakai. Uji adapter CLI menggunakan tone buatan, bukan bukti mutu suara neural. Model asli perlu Anda pasang dan validasi. Default CPU Piper mengurangi perebutan GPU.

Dubbing otomatis, lip-sync, gaze, avatar/presenter, speech repair otomatis, video/fill/object generatif, musik/SFX generatif dan animasi gambar belum mempunyai adapter bawaan. Hasil luar berizin dapat dicatat melalui `m9.media.import` sebagai aset sintetis dengan model/prompt/lisensi/provenance; impor itu tidak dinyatakan sebagai inference Clipper.

## 7. Gambar lokal opsional

Adapter ComfyUI hanya mendukung text-to-image workflow API dengan core node yang diizinkan dan satu checkpoint `.safetensors`. Tidak menerima custom/API nodes atau workflow cloud. Gunakan instance loopback khusus Clipper; jangan jalankan tugas lain secara paralel pada GPU 4 GiB.

Daftarkan URL numerik loopback, workflow API JSON, checkpoint, binding node prompt/seed, lisensi dan anggaran VRAM. Pastikan model_path adalah checkpoint yang benar-benar dikonfigurasi di server ComfyUI. API ComfyUI tidak memberikan attestasi hash bobot server; manifest membedakan hash file yang dinyatakan operator dari identitas server yang belum terattestasi. Metadata prompt gambar diperiksa bila tersedia. Probe memeriksa koneksi, node dan file; status itu **belum** membuktikan inference/model berkualitas. Batas awal: satu latent, batch 1, sisi maksimal 768, maksimal 50 steps, waktu maksimal 600 detik. Anggaran bukan jaminan model muat; mulai kecil dan ukur VRAM aktual.

Inference yang responsnya hilang menahan reservasi sumber daya. Antrean berat lain tidak boleh berjalan sampai provider selesai dan reservasi direkonsiliasi. Pembatalan proses Clipper tidak menjamin proses ComfyUI langsung berhenti. Tunggu/hentikan tugas pada instance provider, kemudian gunakan Rekonsiliasi reservasi GPU dengan ID tugas. Sistem memeriksa antrean provider kosong; tidak membuat inference kedua otomatis.

## 8. Efek sumber M9

Efek menghasilkan **salinan sumber baru sebelum subtitle**, dengan manifest sumber, revisi, rentang, resep dan hash. Sumber asli dan proyeknya dipertahankan. Setelah efek, analisis sumber turunan di editor agar transkrip/timing terikat media yang benar. Efek baked tidak dijanjikan menjadi layer native di CapCut/Resolve.

Operasi JSON yang tersedia: `color`, `curves`, `lut`, `chroma`, `overlay`, `blur`, `mosaic`, `denoise`, `upscale`, `interpolate`, `lens`, `stabilize`, `fade`, `v360`.

- `no_pan` harus true; hook tetap false. Pan/Ken Burns tidak dibuka oleh resep ini.
- Blur/mosaic/overlay memakai `rect: [x,y,w,h]` dan `ranges: [[awal,akhir]]` dalam detik relatif rentang sumber yang dipilih. Area `protected_regions` tidak boleh ditutupi. Mask masih statis; tracking otomatis belum tersedia.
- Chroma key mengganti warna kunci dengan latar warna, memakai similarity/blend dan persetujuan tepi. Periksa rambut, gerakan dan materi pada video nyata.
- Overlay adalah aset gambar terdaftar, opacity dan urutan operasi eksplisit. Mode blend lanjutan/animasi belum tersedia.
- Color/curves/LUT dibatasi SDR. HDR ditolak, bukan dikonversi diam-diam. LUT `.cube` disalin/diperiksa jumlah nilai dan SHA. Color wheels, color match dan relighting belum tersedia.
- Upscale Lanczos menjaga rasio dan ukuran genap. Ini bukan neural enhancement.
- Interpolasi CPU dibatasi sumber maksimal 1080p, 120 detik, dan target 24-60 FPS. Periksa artefak gerakan/teks.
- Deshake/lens memerlukan review tepi/crop; tidak boleh dipakai sembari mengklaim area penting terlindungi belum berubah.
- Viewport 360 statis dibedakan dari panorama asli. Keyframe viewport bergerak belum tersedia.
- Transformasi geometri harus terakhir agar koordinat area tidak diam-diam berubah.

Lakukan A/B sumber dan hasil. Full decode serta kesesuaian durasi tidak membuktikan mutu wajah/teks. Uji mesin ini memakai geometri/warna buatan; acceptance media nyata tetap diperlukan. Preset pack JSON v1 dapat diekspor/diimpor melalui API; pack tidak membawa kode, aset proprietary, LUT atau overlay luar otomatis.

## 9. API, CLI, worker dan uji

HTTP command M8 yang sama menyediakan aksi `m9.*`; schema 1, command_id stabil dan workspace/role tetap berlaku. Lihat `docs/m9/COMMANDS.md`. CLI contoh:

```text
.venv\Scripts\python.exe -m clipper.m8_cli command m9.status
.venv\Scripts\python.exe -m clipper.m8_cli command m9.list --args-file args.json
```

Untuk perintah kedua, buat `args.json` berisi `{"kind":"recording"}`. Gunakan `--help` untuk sintaks CLI; port mengikuti server Anda. Token sesi dibaca dari environment sesuai panduan M8, bukan ditaruh di argumen command. Worker inti memproses tugas M9 satu per satu, terpisah dari penyimpanan capture browser. `JALANKAN_WORKER_M8.cmd` menghidupkan worker distribusi/otomasi lokal bila server UI tidak dijalankan.

`JALANKAN_UJI_M8_M9.cmd` memerlukan pytest dan dependensi tes yang telah Anda siapkan. Installer tidak memasangnya otomatis. Native browser/Windows/model/live API tetap butuh acceptance terpisah; tes protokol bertanda fixture tidak boleh dipakai sebagai bukti inference neural atau unggahan live.

## 10. Rollback dan batas penerimaan

Hentikan server, worker dan capture sebelum rollback. Gunakan `PULIHKAN_M8_M9_4_0_20.cmd`. Bila data M8/M9 telah dibuat, rollback biasa ditolak agar kode lama tidak diam-diam membaca state baru. Mode `--restore-project-state` tersedia secara eksplisit setelah Anda memahami dampaknya: SQLite kembali ke checkpoint sebelum upgrade. Installer menyimpan salinan SQLite terbaru sebelum rollback; media/model tidak dihapus. Ekspor/backup pekerjaan baru sebelum memilih mode ini.

Browser IndexedDB terpisah dari SQLite. Jangan menghapus cadangan capture browser hanya karena kode telah dipulihkan. Backup proyek M8 menyertakan sumber dan referensi lineage/arsip rekaman, tetapi clone restore tidak menghidupkan kembali sesi capture, token tamu atau antrean publikasi.

Acceptance Windows, capture panjang, drift/jaringan nyata, model neural/VRAM, YouTube live, font/native CapCut 4.7.0/Resolve Free 18.6.6 dan G6 listening/Demucs tetap terbuka. Jangan menilai seluruh M0-M9 sempurna hanya karena regresi perangkat lunak lulus. Paket menyediakan kode, hasil uji dan daftar gap yang dapat diperiksa.
