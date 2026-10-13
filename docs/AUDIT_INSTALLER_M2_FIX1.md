# Audit pemasangan M2 · Installer Fix 1

Revisi ini memperbaiki pemasangan paket kumulatif Clipper Pro 4.0.13 M2. Enam paket fitur M2 tetap tersedia. Versi aplikasi tetap 4.0.13; revisi installer ditampilkan sebagai 1.

## Penyebab error

Screenshot menunjukkan satu konflik pada `docs/releases/m0_fixture.zip`. Paket M2 sebelumnya memasukkan arsip pengujian yang dibuat lokal tersebut sebagai payload dan hanya menerima kemasan ZIP bawaan paket. Installer berhenti sebelum menimpa file. Pesan ini tidak membuktikan kode M1 rusak.

Audit berhasil mereproduksi pesan yang persis sama dengan arsip yang seluruh isi filenya identik, tetapi metadata ZIP-nya berbeda. Byte arsip pengguna belum tersedia, sehingga perubahan metadata bukan diagnosis yang dipastikan terhadap arsip pengguna. Kesalahan kontrak paket sudah terbukti: arsip pengujian lokal yang tidak digunakan saat clipping ikut memblokir upgrade.

## M1 GitHub yang diperiksa

- Repository: https://github.com/akbarttnjg/clipper_pro
- Branch: `main`, commit `4529c82f964c83f1031823b937f784c50e8858eb`.
- Git tree: `8affd64b6cb7987c950675fcdf5e3f87750596d5`.
- Seluruh 167 file yang relevan terhadap pemasangan M1 cocok dengan Git blob sumber yang telah diverifikasi dan whitelist kode paket M2.
- Arsip lokal `docs/releases/m0_fixture.zip` tidak ada pada Git tree tersebut. File itu memang dikecualikan oleh `.gitignore` sebagai hasil pembuatan lokal.
- File konfigurasi pribadi dan media percobaan di luar kontrak pemasangan tidak dimasukkan ke paket upgrade.

## Perubahan

1. Arsip lama dikeluarkan dari payload dan guard. Installer tidak membaca, mengganti, atau menghapusnya, termasuk saat pemeriksaan, pemasangan ulang, kegagalan, dan rollback.
2. Snapshot pengujian M0 bawaan M2 memakai nama tersendiri: `docs/releases/m2_m0_fixture.zip`. Arsip, commit asal, jumlah file, dan checksum tiap file diperiksa sebelum pemulihan fixture uji.
3. Pemeriksaan file ZIP bawaan menggunakan SHA-256 byte asli. Normalisasi CRLF hanya dipakai untuk kode/teks; format manifest lama tetap didukung.
4. Manifest menolak payload/guard ganda, entri rusak, mode checksum tidak dikenal, serta benturan dengan daftar file lokal yang wajib dipertahankan.
5. Builder pengujian M0 memakai fixture milik producer beku yang sedang diuji, sehingga tidak membuat ulang arsip lokal milik instalasi M2.
6. Whitelist kode diperluas hanya dengan sumber M2 terdahulu yang terverifikasi untuk memperbolehkan pemasangan revisi ini pada M2 yang sudah terpasang. Perubahan kode lokal yang tidak dikenal tetap ditolak sebelum penyalinan.

## Pemasangan

1. Ekstrak ZIP **Installer Fix 1** ke folder baru di luar mesin.
2. Hentikan antrean dan server dengan Ctrl+C.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`, pilih folder mesin yang berisi `app.py`, `clipper`, dan `.venv`.
4. Jika lulus, jalankan `PASANG_M2_4_0_13.cmd` pada folder yang sama.
5. Jalankan `JALANKAN_PRO.cmd`, kemudian Ctrl+F5 di browser.

Tidak perlu menghapus `m0_fixture.zip`, memasang ulang M1, mengunduh model, atau menyalin payload secara manual. Jika masih ada konflik pada file kode lain, simpan pesan lengkapnya; konflik kode tidak dilewati otomatis.

## Bukti pengujian

| Pemeriksaan | Hasil |
|---|---|
| Regresi Python penuh | 1.165 tes: 1.104 lulus, 0 gagal, 0 error, 61 dilewati |
| Kasus regresi baru untuk revisi ini | 42, seluruhnya lulus |
| Installer + fixture historis + kontrak | 70 lulus, 2 dilewati karena native environment tidak tersedia |
| Suite UI | 11 lulus; menggunakan DOM adapter |
| Skenario dasar pemasangan/pemasangan ulang/rollback | 6 lulus |
| Kode M1 dari GitHub | 386 blob sumber publik diverifikasi; semua 167 file wajib diterima |

Skenario dasar meliputi checkout M1 GitHub tanpa arsip lokal, M1 GitHub dengan arsip yang dikemas ulang, M0, M1 awal, M1 lengkap, dan M2 sebelumnya. Semua diuji dengan operasi file/SQLite nyata.

61 tes yang dilewati terdiri dari 17 pemeriksaan native CV/dependensi core yang belum tersedia, 22 pemeriksaan pyCapCut opsional, dan 22 pemeriksaan fixture sumber historis 4.0.4/4.0.5 yang tidak tersedia pada host ini. Hasil lengkap berdasarkan JUnit, karena capture keluaran terminal regresi penuh tidak lengkap.

Hasil regresi, reproduksi error paket lama, kecocokan GitHub, dan uji arsip tersedia di `verification/installer-fix1/`. Bukti M2 sebelumnya tetap disertakan di `verification/` dan harus dibaca sesuai tanggal serta cakupan pengujiannya.

Operasi filesystem, checksum, backup SQLite, penyalinan atomik, dan rollback diuji nyata. Probe dependensi runtime dan pemeriksaan server memakai double yang dinyatakan pada suite installer, karena environment uji ini tidak memiliki native OpenCV lengkap. Uji ini tidak membuktikan bahwa paket sudah dipasang pada komputer Windows pengguna.

Gerbang G2, pengujian Windows/GPU dengan ucapan asli, akun provider hidup, dan editor native tetap memerlukan penerimaan pada perangkat pengguna. Perbaikan pengenalan teks DaVinci tetap ditunda sesuai arahan pengguna.
