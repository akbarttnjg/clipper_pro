# Clipper Pro 4.0.22 — Perbaikan audit M0–M9

Paket ini memperbaiki sembilan temuan pada rilis 4.0.21. Ini bukan modul M10 dan tidak menandai seluruh acceptance M8/M9 selesai.

## Pasang pada mesin Windows

1. Ekstrak ZIP ke folder baru **di luar folder mesin Clipper**. Jangan menyalin payload secara manual.
2. Hentikan antrean dan tugas komponen, rekaman, server, serta worker/CLI/MCP Clipper, termasuk server pada port khusus. Tugas yang masih `running` atau `cancel_requested` harus dihentikan dengan benar. Jangan mengubah status SQLite secara manual.
3. Jalankan **CEK_SEBELUM_UPGRADE.cmd**, lalu masukkan folder mesin lama, misalnya `C:\AI\clipper`. Pemeriksaan mencocokkan checksum kode dan memakai Python `.venv` mesin tersebut.
4. Jika pemeriksaan lulus, jalankan **PASANG_M8_M9_4_0_22.cmd** dengan folder target yang sama.
5. Jalankan `JALANKAN_PRO.cmd` dari folder mesin lama. Tekan **Ctrl+F5**. Header harus menunjukkan **4.0.22**.
6. Jalankan **CEK_M8_M9_RUNTIME.cmd**. Untuk pengujian kode tambahan gunakan **JALANKAN_UJI_M8_M9.cmd**; pytest harus sudah tersedia pada `.venv`. Tidak ada instalasi komponen atau model otomatis.

Dasar yang didukung: M7 GitHub `f6f1f6a11631f800c1749f8cb6fbcae6dfff384d`, M8 yang dipatok oleh manifest sebelumnya, serta rilis 4.0.20/4.0.21 dengan checksum yang cocok. Jika muncul **Kode lokal berbeda**, berhenti dan pertahankan pesan tersebut. Jangan memaksa menimpa modifikasi lokal.

`.env`, `.env.pro`, video sumber, hasil, unggahan, model, font pribadi, dan lingkungan `.venv` tidak termasuk payload. Installer membuat cadangan kode dan checkpoint SQLite. File kosong `.clipper-install.lock` dipakai OS untuk mencegah perubahan kode ketika mesin terbuka; jangan menghapusnya saat Clipper aktif. File ini tetap ada setelah proses tutup, tetapi kuncinya otomatis dilepas OS.

## Yang diperbaiki

| Temuan | Perubahan |
|---|---|
| A09 | Anggota workspace tidak dapat memakai kit/aset/font host yang belum disiapkan operator untuk proyek. Pemeriksaan juga dilakukan saat menerapkan draf lama. |
| A03 | Installer memeriksa tugas inti, impor, komponen runtime, rekaman, inference tertahan, worker M8 dan proses server. Lease OS melindungi instalasi 4.0.22 sepanjang runtime hidup serta sepanjang install/rollback. |
| A01 | Sumber diperiksa berdasarkan isi file, revisi proyek, dan identitas transkrip pada tahap review, eksekusi, serta penyimpanan. Co-editor dan TTS terikat proyek ikut diperiksa. |
| A02 | Transfer workspace ditolak bila hubungan M9 belum dapat dimigrasikan. Daftar tetap dapat dibuka bila ada orphan lama. Untuk orphan dengan satu workspace asal, kembalikan proyek ke workspace yang sudah memiliki seluruh item M9 melalui pengaturan proyek; akun harus dapat mengelola kedua workspace. |
| A05 | Efek M9 memakai track audio pilihan proyek. Proyek turunan dengan satu track memakai pemilihan audio baru yang valid. |
| A08 | Efek diproses dalam geometri media kanonis; ukuran tampilan, SAR dan rotasi diperiksa. Koordinat mask/overlay mengacu pada bidang tampilan tersebut. |
| A07 | Backup versi 2 membawa tulisan M9 dan bukti hasil/rekaman yang terikat proyek. ID dan path direbase ketika dipulihkan. |
| A04 | Asal sumber M2 dan provenance turunan M9 memakai adapter bertipe. Endpoint dan panel tidak lagi menganggap dictionary sebagai daftar segmen. |
| A10 | Target dan acceptance empat baris katalog M1 dan dua baris M2 dipisahkan memakai arsitektur 120 halaman yang checksum-nya diverifikasi. |

Normalisasi media dapat menambah waktu dan memakai ruang cache, terutama pada video panjang dengan beberapa track, SAR nonstandar atau rotasi. Target proses 30 menit pada perangkat pengguna belum dibuktikan oleh pengujian ini.

## Backup dan pemulihan proyek

Backup proyek membawa item M9 yang mempunyai `project_id` proyek tersebut. Tulisan dipulihkan sebagai `requires_review`. Rekaman dan kandidat/hasil lainnya dipulihkan sebagai **bukti** dengan jenis `restored_evidence`, bukan sebagai sesi/tugas yang dapat langsung dijalankan. File hasil dan metadata tetap dapat diperiksa. Untuk meneruskan pemrosesan, buat tugas baru setelah review.

Track/chunk rekaman lokal yang tersedia disertakan sebagai bukti. Undangan tamu, sesi akun, token, pekerjaan aktif, koneksi publikasi, dan aktivasi provider/model tidak dipulihkan. Provider/suara/aset global workspace yang tidak terikat proyek bukan cakupan backup proyek. Proyek sumber/original dan item lama tetap ada. Backup lama versi 1 tetap dapat dibaca. Batas paket adalah 30.000 anggota dan ukuran yang dipilih pengguna; pembuat backup menolak paket yang melampaui batas pemulihannya.

Hentikan atau batalkan tugas M9 proyek sebelum membuat backup. Bila data berubah selama pencadangan, paket ditolak. Bila ada hubungan M9 lintas workspace dari versi lama, kembalikan hubungan workspace terlebih dahulu.

Asal turunan M9 menampilkan provenance tanpa otomatis memberi akses ke berkas proyek induk. Buka proyek induk menggunakan akses workspace yang sesuai.

## Pulihkan versi kode

Hentikan semua proses Clipper, lalu jalankan **PULIHKAN_M8_M9_4_0_22.cmd**. Cadangan berada di `steezy_backups/complete-*` dalam folder mesin. Gunakan `--backup "path-cadangan"` untuk memilih cadangan tertentu.

Rollback kode akan ditahan jika versi lama tidak dapat memahami data baru, misalnya draf dengan penjagaan sumber, item hasil restore versi 2, atau antrean M9 baru. Jika memang ingin kembali ke checkpoint pra-upgrade, jalankan perintah berikut dari folder paket:

```powershell
py -3 complete_installer.py --target "C:\AI\clipper" --rollback --backup "C:\AI\clipper\steezy_backups\complete-CONTOH" --restore-project-state
```

Opsi tersebut mengembalikan state proyek ke saat sebelum upgrade. Installer mencadangkan SQLite terbaru terlebih dahulu. Edit setelah checkpoint tidak ikut aktif di state lama; pertahankan cadangan terbaru untuk pemulihan selanjutnya.

## Batas bukti

Laporan pengujian final ada di folder `verification` paket. Pengujian Linux memakai FFmpeg nyata, SQLite, HTTP lokal dan fixture buatan. Fixture Ollama/Piper menguji protokol dan penjagaan data; bukan pengukuran mutu model neural. Uji Windows/NVENC/RTX 3050, model Whisper/Qwen/Piper nyata, media podcast panjang, browser Chromium asli, serta impor CapCut 4.7.0 dan Resolve Free 18.6.6 masih perlu dilakukan pada mesin pengguna.

Tidak ada unduhan model, pemakaian API berbayar, login akun, unggahan sosial, broadcast, push GitHub atau deployment otomatis dalam paket ini.
