# Clipper Pro 4.0.18 — perbaikan M6 + M7

Paket ini dipasang di atas M6 4.0.17 yang sesuai GitHub
`14b89fa708f10c31c4119b1c6294d3faf937d373`. Ini upgrade kode offline,
bukan pemasang ulang Python, model atau aplikasi editor. Keenam temuan audit
M6 diperbaiki secara kumulatif; tidak perlu memasang patch M6 terpisah.

## Pasang

1. Ekstrak ZIP upgrade ke folder baru di luar folder mesin Clipper.
2. Selesaikan/batalkan antrean, lalu hentikan server dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`. Pilih folder mesin yang memuat `app.py`,
   `clipper`, `static` dan `.venv`. Pemeriksaan tidak menulis kode/backup.
4. Jika lulus, jalankan `PASANG_M6_M7_4_0_18.cmd` pada folder paket upgrade.
5. Buka `JALANKAN_PRO.cmd` dari folder mesin lama. Tekan Ctrl+F5 di browser.
6. Render ulang final revisi aktif, kedua rasio bila diperlukan. Render lama
   tetap disimpan sebagai rujukan; versi input baru meminta final baru.
7. Buka **Periksa dan ekspor → M7**. Pilih isi paket → **Periksa paket dan
   kemampuan layer** → **Buat paket M7**. Unduh setelah antrean selesai.

Installer memeriksa checksum kode dasar, menolak modifikasi lokal yang tidak
cocok sebelum menimpa file, mencadangkan kode dan SQLite, serta menyediakan
rollback. Sumber, uploads, clips, model, environment dan font pribadi tidak
menjadi payload pemasangan. Tidak ada download model, musik, API berbayar,
perubahan dependensi otomatis atau unggahan GitHub dalam paket ini.

## Perbaikan M6 yang dibawa

| Temuan | Perilaku setelah perbaikan |
|---|---|
| A01 / P1 | Caption mute/hidden tidak menghapus interval ucapan dari ducking atau proteksi angka/negasi untuk SFX. Clock sumber lengkap dipetakan terpisah. |
| A02 / P1 | Dubbing non-loop yang terlalu pendek ditolak sebelum bagian sumber dibisukan; tidak diisi nol untuk menutupi kekurangan aset. |
| A03 / P2 | Track musik terkunci juga melindungi perubahan akibat voiceover/ducking dan pemisahan sumber. |
| A04 / P2 | Musik loop yang dipotong di tengah meneruskan fase crossfade kontinu. |
| A05 / P2 | Fade track berlaku pada batas logis; slice internal speed ramp tidak mengulang fade. Smooth join mengikuti sambungan M1 sebenarnya. |
| A06 / P2 | Pembuat paket historis M0–M5 dan M6 memakai producer beku dengan provenance/checksum, sehingga tidak mencampur kode M7 ke versi lama. |

## Isi M7

- MP4 final per klip × rasio (9:16, 16:9, serta 1:1/4:5/custom yang dibuat di M4), H.264/AAC, pemeriksaan resolusi/FPS/durasi/
  sinkron awal dan full decode. Profil **Salinan final** mempertahankan byte
  final yang direview. Seimbang/Mutu tinggi/Hemat adalah transcode CPU libx264
  eksplisit, CRF 18/16/23; profil aktual tercatat. Tidak ada klaim NVENC baru
  untuk transcode delivery ini.
- SRT, VTT, ASS, TXT dan JSON dari satu revisi caption. Kata, bahasa sumber/
  tampilan, identitas output, revisi dan clock disimpan. Ekor hold caption
  dibatasi frame akhir; waktu ucapan tidak dipendekkan.
- ZIP seluruh pilihan, inventory relatif dengan SHA-256, font yang benar-benar
  dirujuk dan lisensinya, aset editor dalam paket, timeline gabungan per rasio.
- Kandidat proyek CapCut Desktop **4.7.0** dan Resolve Free **18.6.6** memakai
  writer yang sudah ada. Audio aktif adalah satu master final M6; stem
  premaster menjadi referensi WAV terpisah. Menjumlah stem kembali dapat
  mengubah normalisasi/limiter, sehingga tidak dijanjikan identik.
- XML FCP7 untuk Premiere, FCPXML 1.7 untuk Final Cut, dan OTIO JSON. Ketiga
  exchange membawa potongan video final; teks/efek di dalamnya sudah menyatu.
- Clean video tanpa caption (B-roll/finishing tetap menyatu), overlay caption
  alpha opsional **qtrle ARGB MOV**, serta WAV master/stem 48 kHz. Alpha dapat
  besar; aktifkan hanya bila diperlukan.
- Publish kit lokal: cover JPEG, judul, deskripsi, tag/caption dan metadata
  yang terikat revisi/hash. Tidak memposting ke platform.
- Tautan review lokal dengan izin **Review** atau **Review + unduh ZIP**, masa
  berlaku 15 menit–7 hari dan pencabutan. Token disimpan dalam bentuk hash.
  Tautan selalu menunjuk delivery yang sama meski proyek kemudian diedit.

## Buka delivery di editor

Ekstrak ZIP delivery ke folder permanen. Jalankan **CEK_PAKET.cmd**, lalu
**SIAPKAN_PAKET.cmd** untuk memetakan path ke lokasi ekstraksi. Ulangi persiapan
setelah folder dipindahkan; perubahan aset yang tidak sesuai checksum ditolak.

CapCut: `Editors/PASANG_CAPCUT.cmd`. Jika wrapper multi-timeline ditolak,
jalankan `py -3 PASANG_PROYEK.py --capcut --individual` dari `Editors` untuk
mendaftarkan draft per klip. Installer proyek tidak menimpa proyek lama.
Untuk gabungan, gunakan `Merged/<rasio>/Editors/PASANG_CAPCUT.cmd`; caption
pada gabungan ini berada di gambar final dan tidak editable sebagai teks.

Resolve: XML di `Editors/DaVinci/clip-XX/timeline.xml`. Script Lua/Fusion
merupakan kandidat tambahan. **EX05 text/font tetap backlog**; jangan anggap
native text setara sebelum membandingkan render editor dengan MP4 rujukan.

Premiere/Final Cut/OTIO: berkas di `Clips/<key>/Exchange` atau
`Merged/<rasio>/Exchange`. Jalankan persiapan paket dahulu. Tidak ada proyek
`.prproj` atau `.fcpbundle` native yang dijanjikan oleh adapter XML ini.

Jangan menghapus folder delivery setelah impor karena proyek merujuk media
paket. Periksa lisensi custom font/aset Anda sebelum mendistribusikan paket.
Path sumber pada `reference-plan.json` adalah bukti asal, bukan media aktif
proyek editor. Semua media aktif harus tetap di dalam delivery.

## Review dan bukti native

Pada panel M7, buat tautan untuk delivery yang sudah selesai. Pilih izin dan
masa berlaku secara eksplisit. Buka link `/watch`, salin URL dari browser bila
ingin membagikannya di jaringan Anda. Server lokal harus tetap berjalan dan
terjangkau penerima. Paket ini tidak menerbitkan server publik atau membuka
port. Izin review membatasi endpoint ZIP, **bukan DRM**: video yang ditampilkan
secara teknis tetap dapat disimpan penerima. Tombol cabut menonaktifkan token.

Struktur JSON/XML yang lulus tidak membuktikan impor native. Di mesin target,
buka paket, periksa media online/font/crop, edit teks yang memang kandidat
editable, simpan, render ulang, bandingkan audio/gambar dengan final. Catat
versi editor dan masalah pada panel Evaluasi & bukti impor. Untuk M7 target
versinya 4.7.0/18.6.6. G7 tetap menunggu bukti ini; G6 mendengar video asli dan
Demucs dengan bobot asli juga belum disahkan oleh tes sintetis.

## Pulihkan

Hentikan server lalu jalankan `PULIHKAN_M6_M7_4_0_18.cmd`. Cadangan berada di
`steezy_backups/complete-...`. Rollback kode saja mempertahankan edit M6 yang
masih kompatibel. Bila database telah memuat delivery M7, tautan review atau
antrean M7, kode lama tidak memahami fitur tersebut dan rollback akan berhenti.
Untuk kembali ke checkpoint sebelum upgrade, jalankan dari folder paket:

```text
py -3 complete_installer.py "D:\Folder\Clipper" --rollback --restore-project-state
```

SQLite terbaru dicadangkan terpisah sebagai
`data/studio4-latest-before-rollback.sqlite3` pada backup sebelum state lama
dipulihkan. Langkah ini mengembalikan keputusan proyek ke checkpoint sebelum
upgrade; baca pesan installer sebelum memakainya. File video/model pribadi
bukan bagian rollback kode dan tidak dihapus.

## Pengujian sendiri

`JALANKAN_UJI_M6_M7.cmd` menjalankan regresi audit M6 dan uji M7 bila pytest
sudah tersedia di environment mesin. Perintah ini tidak memasang pytest.
Periksa hasil di `m7-test-results`. Bukti Linux/FFmpeg/DOM yang disertakan
terpisah dari uji Windows, RTX/NVENC, suara asli dan aplikasi editor target.
