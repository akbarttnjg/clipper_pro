# Audit perubahan M9 — Clipper Pro 4.0.21

Rilis ini melanjutkan fondasi 4.0.20. Perubahan utama adalah jalur dubbing
satu suara dari track terjemahan M2 yang disetujui, dengan kandidat terpisah,
stem A/B dan penerimaan eksplisit sebelum membuat proyek editor baru.
Konteks generatif kini dapat dibatasi per klip/rentang pada sumber panjang.

## Temuan dan perbaikan

| Temuan | Perilaku 4.0.21 | Bukti yang relevan |
|---|---|---|
| Konteks kreatif selalu mengambil seluruh transkrip | Pilih klip/rentang sebelum batas konteks; ID dan jam unit asal dipertahankan | Transkrip buatan 35.000 unit selama 7.200 detik, seleksi di tengah/akhir |
| Usulan co-editor dapat diarahkan ke target lain | Klip dan rasio harus sama dengan sumber usulan | Uji penolakan lintas klip/rasio |
| GN05 belum memiliki pipeline dubbing internal | Track M2 disetujui → review per cue → Piper lokal → PCM per cue → kandidat A/B | CLI nada buatan dan FFmpeg sungguhan, FFT frekuensi dan posisi sampel |
| Hasil TTS tidak membuktikan pengucapan benar | Kandidat menunggu dengar; penerimaan mengikat SHA output dan revisi sumber | Penolakan belum dengar, output berbeda dan penerimaan ganda |
| Cue terlalu panjang berisiko terpotong | Atur batas percepatan; padding hening; tolak jika ekor tidak muat | Uji cue berlebih, bukti truncated_samples=0 pada hasil sukses |
| Input dapat berubah saat kerja | Pin track, revisi, model/config/executable SHA; periksa ulang saat publikasi | Perubahan sumber/revisi/voice, pembatalan dan tamper media/manifest/ZIP |
| Downgrade 4.0.21→4.0.20 dapat menyembunyikan data dubbing | Deteksi fitur baseline dan wajib checkpoint eksplisit jika data baru dipakai | Uji installer/rollback dan integritas SQLite |

## Jejak arsitektur

Dasar: `Arsitektur_Clipper_Pro_Terpadu_120_Halaman.pdf`, SHA256
`76685871f95074d95c44fffaa4a0de4a65ab7b6a19fb28fa640a54d04f2dec36`.
GN05 menargetkan track terjemahan, glossary dan review fakta. Implementasi
baru memenuhi jalur lokal satu suara dengan review, tetapi kualitas bahasa,
multi-voice, latar dan sinkronisasi wajah belum diterima. Status GN05 berubah
dari **blocked** menjadi **partial**. GN01/GN02/GN16 mendapat konteks terpilih;
status acceptance modelnya tetap bersyarat.

| Milestone | Lokal | Bersyarat | Sebagian | Belum diimplementasikan |
|---|---:|---:|---:|---:|
| M8, 44 kebutuhan | 26 | 8 | 9 | 1 |
| M9, 45 kebutuhan | 7 | 9 | 19 | 10 |

Jumlah adalah kategori cakupan kebutuhan, bukan persentase kelulusan produk.
Seluruh acceptance milestone M8/M9 belum ditutup. Tracker JSON memuat batas
setiap kebutuhan, termasuk fitur lama yang belum lengkap.

## Verifikasi dan batas bukti

Uji menggunakan Python/FFmpeg/OpenCV yang tersedia, executable nada buatan
untuk protokol Piper, HTTP fixture model lokal dan adapter DOM JavaScript.
PCM dan media benar-benar diproses; tidak ada model neural berlisensi yang
diunduh atau diuji dalam pekerjaan ini. Keberhasilan protokol tidak membuktikan
kualitas aksen, nama, angka atau negasi pada suara model nyata.

Hasil akhir regresi, JUnit, hash source dan bukti pemasangan terdapat dalam
`HASIL_VERIFIKASI_4_0_21.json` dan paket bukti yang menyertai distribusi.
Laporan 4.0.20 yang dipertahankan di repo adalah bukti historis rilis sebelumnya.
Uji native Windows/perangkat browser, akun platform live, native CapCut 4.7.0
dan Resolve Free 18.6.6 belum dilakukan pada lingkungan ini. Tidak ada posting,
broadcast, login akun atau push GitHub yang dilakukan.

## Pemulihan baseline dan keterulangan

Workspace sementara kehilangan checkout M9 asli. Payload 4.0.20 dipulihkan
dari paket tersimpan SHA256
`34089d0717fa70b32ff7160e1ffaf188b2e0c56a663bac205825222dc8dae866`;
seluruh 84 payload dicocokkan dengan manifest, termasuk empat suite Python M9
dan adapter recorder. Kode lain dipulihkan dari snapshot produser M8 yang
terikat SHA. Commit sumber lama yang dinyatakan paket adalah
`6c05c88fa88bd98168618255f69f90d4a67332c0`; objek git itu tidak tersedia lagi,
sehingga dibuat commit pemulihan terpisah dan provenance dipertahankan.
Produser 4.0.20 dibekukan sebelum perubahan baru; membangun rilis lama tidak
mengambil kode 4.0.21. Paket baru menerima M7, M8 terpin, atau payload 4.0.20
yang cocok hash. Rincian ada di `docs/releases/recovered_4_0_20_provenance.json`.
