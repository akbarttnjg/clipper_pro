# Laporan implementasi 4.0.18 — M6 audit repairs + M7

Basis kode: GitHub `14b89fa708f10c31c4119b1c6294d3faf937d373` (M6 4.0.17).
Spesifikasi: Arsitektur Clipper Pro Terpadu 120 Halaman, SHA-256
`76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36`;
halaman 53, 64–65, 104–105. Audit enam temuan M6 menjadi kontrak regresi,
bukan hanya perubahan label. Tidak ada push/deploy dari paket ini.

## Implementasi

M7.1–M7.6 memiliki jalur aplikasi, API, antrean, eksekusi media dan paket lokal.
Writer CapCut/Resolve lama tetap dipakai; opsi M7 menambahkan satu master aktif
agar proses nonlinear M6 tidak berubah karena penjumlahan ulang stem.
Premiere/Final Cut/OTIO sengaja membawa potongan final dengan efek menyatu.
Kemampuan caption/style/motion/crop/mask/stem/effect dibedakan sebelum ekspor.
Istilah `editable_candidate` memerlukan bukti impor; bukan sertifikasi native.

Output final baru memuat lima format sidecar dan snapshot font dalam ArtifactSet
yang sama. M7 memakai ArtifactSet delivery terpisah: pemeriksaan coverage,
full decode, salinan aset, laporan, inventory dan CRC ZIP selesai sebelum seal.
Gabungan memakai trim per klip dan reset clock frame/sample untuk menghindari
tambahan frame dari priming AAC. Jumlah frame MP4 diperiksa terhadap plan.
Metadata sidecar membedakan bahasa sumber, terjemahan dan bilingual.
Database pointer hanya diterbitkan dengan lease antrean dan dependency yang
masih sesuai. Gagal, stale atau cancel tidak mengganti delivery lama.

Portabilitas memakai inventory relatif dan relink native yang diperiksa.
Setelah ekstraksi/pemindahan, script stdlib memverifikasi semua anggota sebelum
menyesuaikan path. Receipt persiapan merekam checksum file yang ditulis ulang.
Font yang dirujuk saja disertakan; custom face memerlukan metadata izin.

Review lokal menggunakan token acak 256 bit, hash token di SQLite, scope
review/download, expiry dan revocation. Anggota dikunci pada content identity
set yang direview. Preview tetap dapat disalin; tidak mengklaim DRM.

## Batas penerimaan

- G6: listening ucapan asli Indonesia/code-switch, kata pelan, negasi, angka,
  jeda bermakna dan Demucs dengan runtime/bobot asli masih perlu.
- G7: CapCut 4.7.0 impor/edit/simpan/render/compare di Windows masih perlu.
- Resolve Free 18.6.6 perlu impor nyata; EX05 text/font tetap backlog eksplisit.
- Premiere/Final Cut memerlukan import exchange di aplikasi target.
- i5-12500H / 40 GB / RTX3050 4 GB, NVENC dan browser native belum disertifikasi
  dari lingkungan Linux. Transcode profil delivery baru adalah CPU eksplisit.
- Cover/deskripsi/tag adalah turunan lokal dari judul/caption yang disetujui,
  bukan evaluasi kualitas pemasaran. Tidak ada auto-posting (cakupan M8).

## Rujukan adapter

- Apple FCPXML 1.7 DTD:
  https://developer.apple.com/library/archive/documentation/Miscellaneous/Conceptual/LegacyDTDsFinalCutPro/FCPXMLDTDv1.7/FCPXMLDTDv1.7.html
- Apple Creating FCPXML Documents:
  https://developer.apple.com/documentation/professional-video-applications/creating-fcpxml-documents
- Academy Software Foundation OpenTimelineIO serialized schema:
  https://opentimelineio.readthedocs.io/en/latest/tutorials/otio-serialized-schema.html

Hasil pengujian akhir dan SHA rilis tersedia pada paket verification serta
laporan pendamping. Fixture tone/gambar buatan membuktikan mekanik dan
sinkronisasi; tidak menggantikan penilaian manusia atau editor native.

Uji historis installer 4.0.5/4.0.6 dapat dilewati bila full-source fixture dasar
4.0.4/4.0.5 tidak tersedia di samping checkout. Ini dicatat sebagai skip,
bukan pass. Parser OTIO resmi tidak tersedia dalam runtime verifikasi;
baca-balik OTIO menguji cut list/reference terstruktur, bukan import aplikasi.
