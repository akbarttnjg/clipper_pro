# Laporan implementasi Clipper Pro 4.0.14 M3

Dasar kebutuhan: **Arsitektur_Clipper_Pro_Terpadu_120_Halaman (2).pdf**, 120 halaman, SHA256 `76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36`. Paket M3 ditentukan halaman 48; CL01–CL19 halaman 90–92. Dasar kode publik: GitHub `akbarttnjg/clipper_pro`, commit `b8d12eb972b742a75379c39dc8fa7d35752b9e5e`, tree `10a7c77bf85fabba66f60439b468009d0e48f475`.

412 file GitHub cocok dengan sumber M2 Fix1 lokal. Perbedaan builder M0 lama dikenali melalui hash yang diketahui dan diperbaiki dalam overlay. Konfigurasi privat `.env.pro` serta video uji NVENC tidak menjadi payload. Versi M2 awal juga dikenali; baseline kode asing tetap ditolak.

## Hasil enam paket

| Paket | Fungsi yang dipasang | Persyaratan |
|---|---|---|
| M3.1 | Kandidat dengan kontrak sumber, count/duration/range, scan semua chunk dan overlap adaptif; pool terbatas dengan cakupan sepanjang sumber | CL01, CL02, CL07 |
| M3.2 | Batas unit/kalimat utuh, pertanyaan–jawaban, caveat, kesimpulan dan rincian daftar; perbaikan span sebelum ranking | CL05, CL06 |
| M3.3 | Index SQLite immutable, query ulang, E5 opsional dan Ollama lokal, speaker/frasa, ringkasan/tag/chapter berbukti sumber | CL03, CL04, CL12, CL17 |
| M3.4 | Deduplikasi konservatif yang menjaga angka/negasi, proposal perbandingan semantik, cakupan topik, top-N dan alternatif | CL08, CL09, CL11 |
| M3.5 | Alasan/skor terpisah, energi audio aktual, frame+hash, VLM/objek opsional, HUD yang ditinjau, voice marker dan hotkey | CL10, CL13, CL14, CL15, CL16 |
| M3.6 | Susunan span tidak bersebelahan, clock dua rasio, review/accept/reject, set render dan feedback historis | CL18, CL19 |

Ini merupakan implementasi workflow. **G3 belum lulus**: kualitas seleksi cerita/semantic retrieval, objek dan event game pada corpus nyata belum diukur. CL15 belum memenuhi penerimaan corpus per game; emosi otomatis CL14 belum diimplementasikan sebagai model terkalibrasi. Nilai yang tidak diukur tetap `null`, bukan nol atau angka keberhasilan.

## Perubahan perilaku

- Pada proyek baru yang mengaktifkan M3, analisis menyimpan ASR/koreksi lebih dahulu dan mengantrekan seleksi. Proposal belum menjadi klip render sebelum operator menerimanya.
- Pencarian ulang bergantung pada sumber, transkrip, teks/timing/speaker dan model yang relevan. Perubahan prompt tidak memanggil ASR; perubahan style tidak membuang index.
- Sebuah kandidat menyimpan kutipan klaim/caveat/penutup, identitas unit, span, batas permintaan, alasan, skor, confidence sumber, blocker dan review flag. ID kandidat tetap sama jika isi sumber kandidat sama meski query/ranking berbeda.
- Kelengkapan mendahului daya tarik. Kekurangan jumlah/topik dinyatakan; filler tidak dimasukkan untuk membuat target terlihat tercapai.
- Deduplikasi otomatis terbatas pada teks sumber yang ekuivalen dengan angka/negasi sama. E5 mengusulkan perbandingan manusia; kemiripan embedding tidak otomatis menghapus cerita.
- Keputusan manusia, alasan dan checklist tersimpan terpisah dari skor model. Reject menonaktifkan render tanpa menghapus klip atau feedback. Reaccept mempertahankan edit varian.
- Susunan beberapa span memakai proxy FFmpeg dan clock M1 yang telah ada. Audio, video, caption dan kedua rasio mengikuti urutan sumber yang sama. Ucapan penghubung tidak dibuat.
- Draf query/review terpisah per tab; konflik tidak membuang teks. Source player memakai media canonical agar tombol evidence/marker mengikuti waktu sumber.

## Runtime model dan sumber bukti

Ollama memeriksa digest model `/api/tags` sebelum/sesudah proposal dan output terstruktur `/api/generate`. Proposal harus memakai ID/kutipan yang benar-benar ada dalam sumber; ID palsu, kutipan buatan, struktur tambahan dan hasil terpotong ditolak. Prompt memperlakukan transkrip sebagai data. Receipt mencatat model, digest, evaluasi dan waktu; perangkat aktual tetap belum diketahui jika server tidak memberikan bukti.

E5 opsional berjalan pada CPU melalui komponen lokal yang sudah teruji. Passage memakai prefix `passage:`, query `query:`. Vektor divalidasi dan index mengikat digest bobot aktual, generation, preprocessing, take, scope dan sumber. Bobot berubah saat inference → hasil tidak disimpan. Cue panjang dibagi menjadi passage tanpa memalsukan timing per kata.

Audio menggunakan PCM dari FFmpeg dan track canonical yang dipilih, buffer terbatas serta cancellation subprocess. Decode gagal berbeda dari energi nol. Frame disampel dengan anggaran terbatas; waktu/hash disimpan. Frame/energi belum merupakan pengenalan emosi atau label objek. VLM/OCR opsional harus memberikan receipt model aktual; status tidak tersedia tetap ditampilkan dalam laporan.

Rujukan protokol utama: [Ollama tags](https://docs.ollama.com/api/tags), [Ollama generate](https://docs.ollama.com/api/generate), [multilingual-e5-small model card](https://huggingface.co/intfloat/multilingual-e5-small). Pengujian protocol double memastikan batas aplikasi; tidak mengukur kualitas model tersebut.

## Integrasi dan perlindungan pekerjaan

API baru berada di `/api/studio/projects/{id}/selection`, dengan sub-route decision/story/marker/render-set. Mutation memakai expected revision dan operation id; queue memakai lease dan pemeriksaan source/dependency sebelum publikasi. SQLite/CAS/idempotence/histori diuji nyata. Gagal/batal seleksi baru mempertahankan laporan sebelumnya.

Render/export/batch menjaga status M3 accepted dan signature sumber. Include flag saja tidak melewati review. Pemilihan set final menonaktifkan klip lain tanpa menghapus edit. Sumber/track berubah tidak diam-diam memakai transkrip lama. Mode sumber audio tidak mendapat wajah/frame rekaan. Transcript kosong untuk review non-dialogue diberi receipt `inference_performed:false`.

Installer mengenali M2 yang telah diverifikasi, memeriksa payload/guard, membuat backup kode/SQLite, melakukan import probe, serta rollback saat penyalinan/probe gagal. Data M3 atau pekerjaan antrean aktif menghalangi rollback kode saja. Pemulihan state mencadangkan SQLite terbaru dahulu. Fixture historis M2 dibekukan dengan hash tiap anggota supaya uji M2 tidak membangun ulang paket menggunakan kode M3.

## Bukti uji dan batasnya

Regresi final: **1.304 tes terkumpul; 1.243 lulus, 61 dilewati, 0 gagal, 0 error**. Seluruh **139 tes khusus M3** lulus. **12 suite UI** lulus; panel M3 mencakup **13 kelompok perilaku**. Versi environment, daftar skip, log dan JUnit tersedia di `verification/summary.json`. Pengujian mencakup kontrak cerita, index/query, grounding Ollama, speaker/frasa, corpus waktu authored dua jam, SQLite/CAS/queue/API, frame/PCM FFmpeg, UI DOM serta installer. Tidak ada target angka tes untuk menyatakan kualitas; setiap tes menguji perilaku atau kegagalan yang relevan.

61 skip terdiri dari 17 pemeriksaan lingkungan OpenCV/core, 22 pemeriksaan pyCapCut, serta 22 pemeriksaan yang memerlukan fixture sumber lama 4.0.4/4.0.5. Kegagalan tidak disamarkan sebagai skip. Pemasangan, pemasangan ulang idempotent, preservasi file/data, dan rollback byte-for-byte lulus pada dua baseline: unggahan GitHub M2 yang diverifikasi (413 file publik, tanpa membaca konfigurasi privat) dan M2 awal (396 file sumber). Runtime probe native pada uji installer menggunakan double eksplisit; ini tidak menyatakan aplikasi telah dibuka pada Windows pengguna.

Uji media M3 menggunakan sumber **sintetis** warna merah/biru/hijau dengan nada berbeda dan tiga cue authored. Kandidat gabungan melewati review/accept, editor membuat proxy, lalu renderer FFmpeg/libass menghasilkan portrait 360×640 dan landscape 640×360. Full decode, urutan warna, frekuensi audio, durasi, pemetaan origin word, clock identik, cache reuse dan sumber tidak berubah diperiksa. Geometry ditentukan secara eksplisit; tidak ada klaim inference CV atau nilai estetika typography dari fixture ini.

Protokol Ollama/E5/VLM tertentu memakai double yang dinyatakan di tes. Video dua jam berupa referensi timing authored untuk cakupan scanner, bukan ASR dua jam atau blind editorial benchmark. UI memakai DOM adapter Node, belum browser Windows nyata.

Penerimaan yang masih diperlukan: corpus blind G3 lintas jenis sumber, model lokal nyata pada mesin pengguna, corpus masing-masing game, original media + OpenCV/NVENC, browser Windows/two-tab/zoom dan regression CapCut native. Pembacaan teks DaVinci tetap ditunda sesuai instruksi pengguna. Paket ini tidak menyatakan hasilnya sudah setara clipper TikTok profesional hanya dari tes fungsi.
