# Clipper Pro 4.0.19 — M8: distribusi, analytics, workspace dan API

Paket ini dipasang **di atas M7 4.0.18**, sesuai GitHub `f6f1f6a11631f800c1749f8cb6fbcae6dfff384d`. Paket mencakup jalur operasional enam paket M8.1–M8.6. **Gerbang seluruh M8 belum ditutup**: koneksi akun nyata, Windows/DPAPI, fitur bersyarat dan backlog tetap dicatat pada `M8_REQUIREMENTS.json`. Jangan mengartikan keberadaan kode sebagai bukti posting atau native acceptance.

## 1. Pemasangan

1. Ekstrak ZIP ke folder baru **di luar** folder mesin Clipper.
2. Selesaikan/batalkan antrean yang sedang aktif. Tutup server dengan Ctrl+C. Jika menjalankan worker CLI, hentikan juga worker tersebut.
3. Jalankan `CEK_SEBELUM_UPGRADE.cmd`, lalu isi folder mesin lama yang berisi `app.py` dan `.venv`.
4. Jika pemeriksaan lulus, jalankan `PASANG_M8_4_0_19.cmd` dan pilih folder yang sama.
5. Jalankan `JALANKAN_PRO.cmd` di folder mesin lama. Tekan Ctrl+F5 di browser.
6. Buka **Distribusi & workspace M8** pada header, atau panel M8 di **Periksa dan ekspor**.

Installer memeriksa checksum kode dasar dan payload, membuat cadangan kode serta SQLite, dan melakukan pemeriksaan import menggunakan Python mesin lama. Pemasangan ulang yang identik tidak menulis ulang kode. Perubahan lokal yang tidak dikenali menyebabkan pemeriksaan berhenti sebelum menimpa kode. Jangan menyalin folder payload manual.

Video, hasil sebelumnya, model, environment, font pribadi dan `.env` tidak menjadi payload. Tidak ada download model atau penggantian environment otomatis. Pipeline render tetap `4.0.18-m7`; M8 tidak mengubah algoritme render, sehingga final M7 yang masih fresh tidak harus dirender ulang hanya karena memasang M8.

## 2. Mulai dari unggah manual

Ini jalur awal yang dapat dipakai tanpa koneksi API akun:

1. Pastikan final dan paket M7 sudah dibuat dari revisi aktif.
2. Buka tab **Akun** di M8. Tambahkan profil handoff untuk TikTok, Instagram, Facebook, LinkedIn, X, YouTube manual atau platform lain. Nama profil membantu memastikan tujuan; profil ini belum merupakan bukti login ke platform.
3. Pada tab **Publikasi**, pilih final M7, akun, **Paket unggah manual**, judul, deskripsi/caption, tag dan privacy tujuan. Jadwal memakai **Asia/Jakarta** sebagai awal dan menyimpan instant UTC.
4. Klik **Buat draf publikasi**. Periksa receipt file, akun, metadata dan jadwal.
5. Klik **Periksa draf tersimpan**, lalu **Setujui draf ini dan antrekan**.
6. Worker menyiapkan ZIP. Status **Paket unggah manual siap** berarti ZIP tersedia, bukan video telah diposting.
7. Unduh ZIP, lalu unggah `video.mp4` melalui aplikasi platform. Pasang cover/subtitle sesuai kemampuan platform. `handoff.json` memuat metadata dan file checksum.
8. Sesudah unggah manual, catat ID, URL dan privacy aktual pada permintaan tersebut. Catatan berlabel **operator reported**, bukan verifikasi API.

ZIP membawa MP4 yang sama dengan final M7 terpilih serta sidecar dan publish kit yang tersedia untuk klip tersebut. Jika paket M7 dibuat tanpa publish kit, cover tidak diciptakan diam-diam oleh M8. Pembuatan profil tidak menghubungkan atau memposting akun.

## 3. YouTube API opsional

### Persiapan lokal

- Gunakan Google Cloud project milik Anda; aktifkan YouTube Data API dan, jika dipakai, YouTube Analytics API.
- Siapkan OAuth client bertipe **Desktop** dan pengaturan consent/test user yang sesuai akses project Anda.
- Di M8 → Akun, isi client ID, client secret dan nama profil. Nilai ini tidak dikirim melalui chat ini.
- Pilih izin manage hanya jika ingin mengubah metadata atau membatalkan schedule remote menjadi private. Izin ini berbeda dari unggah dasar.
- Klik **Mulai koneksi Google**, buka tautan persetujuan, lalu pilih channel tujuan. Listener callback hanya pada `127.0.0.1` dengan port sementara, state satu kali dan PKCE S256; proses kedaluwarsa setelah 10 menit.
- Kembali ke Clipper, periksa hasil koneksi dan klik **Periksa koneksi akun**. Probe memeriksa bahwa token memiliki channel tujuan; hasil berlaku 15 menit untuk approval.

Koneksi OAuth Desktop dilakukan pada komputer yang menjalankan callback. Menjalankan konsol pada komputer lain tidak otomatis membuat callback localhost menuju server. Untuk deployment tambahan, hubungkan akun pada host yang sesuai sebelum mengaktifkan akses server, atau gunakan handoff.

### Vault

Windows menggunakan **DPAPI milik user Windows** yang menjalankan aplikasi. File vault berada dalam folder kerja dan bukan berkas token plaintext. Pemindahan ke akun Windows/host lain memerlukan koneksi ulang.

Host non-Windows memerlukan `cryptography` dan `CLIPPER_M8_VAULT_KEY` berisi base64 dari kunci acak 32 byte yang disediakan **di luar proyek/ciphertext** oleh operator. Tidak ada fallback plaintext atau kunci yang dibuat di sebelah file terenkripsi. Jika vault belum siap, handoff dan inti lokal tetap tersedia; koneksi OAuth diblokir.

### Mengunggah

1. Pilih akun YouTube yang sudah tersambung dan diprobe.
2. Pilih **YouTube API setelah koneksi diperiksa**. Privacy harus dipilih eksplisit; nilai awal private.
3. Buat draf, periksa receipt, lalu setujui hash draf tersebut.
4. Status bergerak melalui queued, uploading, processing, kemudian hasil aktual. Remote ID, processing, privacy dan `publishAt` diperiksa dari platform.
5. Hasil berbeda dari permintaan diberi **remote_mismatch**. Kode tidak mengasumsikan bahwa privacy public pasti diterima.

Upload memakai sesi resumable yang disimpan terenkripsi sebelum byte video dikirim. Setiap chunk dibandingkan dengan digest snapshot yang disetujui. Jika respons chunk terakhir hilang, worker menanyakan sesi yang sama sebelum melanjutkan. Sesi hilang/kedaluwarsa setelah percobaan dapat berstatus **needs_reconcile**; sistem tidak membuat video kedua otomatis.

### Jadwal lokal dan jadwal remote

- Jadwal lokal: worker baru mengirim ketika instant UTC jatuh tempo. **Komputer dan worker harus tetap aktif**. Tidur/mati/offline tidak menjalankan jadwal.
- Jadwal remote YouTube: pilih tujuan **public**, waktu mendatang, lalu centang **Simpan jadwal di YouTube**. Unggahan awal private dengan `publishAt`. Status **scheduled_remote** hanya diberikan setelah waktu/privacy remote cocok. Pemrosesan dan publikasi aktual tetap dipantau.
- Zona waktu disimpan bersama waktu lokal dan UTC. Waktu DST yang tidak ada ditolak; waktu ambigu memerlukan pilihan fold melalui API.
- Tidak ada penyediaan server cloud atau pembukaan port otomatis. Worker pada host lain memerlukan source/ArtifactSet, database dan vault yang benar-benar dapat digunakan host tersebut.

### Cancel dan edit

Pembatalan sebelum pengiriman membatalkan antrean lokal. Setelah remote mungkin menerima video, pembatalan lokal tidak diberi label berhasil menghapus posting. Pilihan remote-to-private memerlukan izin manage, memeriksa remote ID, mengubah privacy menjadi private, menghapus schedule, lalu membaca kembali status. Video tidak dihapus otomatis.

Perubahan judul/deskripsi/tag remote tersedia melalui command `publish.remote_edit`, dengan version dan izin manage. Perubahan ini tidak mengubah privacy atau deklarasi konten anak. Jika akses tidak tersedia, gunakan YouTube Studio dan catat hasilnya. Posting manual dibatalkan melalui platform terkait.

## 4. Persetujuan dan perubahan proyek

Draf membekukan project revision, clip/ratio, ArtifactSet/package SHA, output SHA, chunk hashes, akun+versi, metadata, privacy dan waktu. Approval menunjuk hash tepat dari isi tersebut. Perubahan form membatalkan kesiapan persetujuan pada panel; perubahan proyek/akun memblokir pengiriman berikutnya.

Status dapat berarti:

| Status | Makna |
|---|---|
| draft | Belum disetujui |
| queued | Disetujui dan menunggu waktu/worker |
| uploading | Sesi upload aktif; belum berarti posting selesai |
| processing | Platform memiliki ID, pemrosesan belum selesai |
| scheduled_remote | Jadwal remote terverifikasi |
| published | Video terproses di platform; periksa privacy aktual, termasuk private/unlisted |
| handoff_ready | ZIP unggah manual siap, belum diposting |
| stale | Revisi/akses berubah sebelum pengiriman |
| needs_reconcile | Hasil remote belum pasti; inspeksi sebelum retry |
| remote_mismatch | Privacy/waktu/hasil remote berbeda dari permintaan |
| canceled | Pembatalan lokal atau hasil remote yang dijelaskan pada receipt |

File `work/m8-publish-receipts` mempertahankan jejak percobaan channel+output di luar SQLite. Ini mencegah pembuatan ulang unggahan diam-diam sesudah pemulihan database lama. Jangan menghapus receipt untuk memaksa retry. Pengulangan video yang disengaja memerlukan alasan eksplisit lewat `duplicate_reason` setelah hasil sebelumnya diperiksa.

## 5. Analytics dan catatan mutu

- Data API YouTube serta impor operator diberi asal berbeda. Nilai hilang adalah `null` dengan alasan; nol adalah pengukuran nol.
- Setiap observasi terikat publish ID, project revision, clip, ratio, ArtifactSet dan output SHA.
- Periode tidak digabungkan sembarangan. Rata-rata per post yang tersedia diberi definisi dan coverage; bukan rata-rata tertimbang penonton.
- Ekspor CSV/JSON dapat dibuka di luar aplikasi. String CSV yang dapat dianggap formula diberi perlindungan.
- API advanced menyediakan experiment dengan hypothesis, variant, context, primary metric dan assignment sebelum approval. Randomized assignment bukan bukti efek kausal atau signifikansi otomatis.
- `effort.record` menerima interval review/correction yang dikonfirmasi operator, masing-masing maksimal 120 detik, tanpa overlap. Waktu menunggu render bukan interval aktif.
- `cost.record` membedakan measured import/estimate, waktu proses, waktu GPU, disk dan biaya provider USD. Tidak ada tarif cloud yang diciptakan dari waktu GPU lokal.
- Topik dapat diimpor dengan provenance dan umur data; pengambilan tren otomatis belum disediakan.
- Prediksi drop-off tetap **not_calibrated/null** sampai ada corpus dan evaluasi held-out yang cukup.
- Promosi template memakai feedback A/B manusia dari core dan mempunyai rollback versi. Pelatihan ranking otomatis belum aktif.

## 6. Workspace, role, review dan backup

Mode solo tidak memerlukan login. Mode anggota menggunakan token sesi workspace 1–168 jam, hanya hash token disimpan pada SQLite. Token dapat dicabut; perubahan role berlaku pada perintah berikutnya, termasuk replay receipt.

| Role | Kemampuan |
|---|---|
| Owner | Membaca, edit, review, approval, publish dan pengelolaan workspace/akun |
| Editor | Membaca dan edit melalui proposal/revision core |
| Reviewer | Membaca, komentar dan review; tidak publish |
| Publisher | Membaca, review, approval dan publish; tidak mengelola credential atau role |

Konsol `/m8` memakai token hanya pada tab browser. Endpoint lama yang tidak memiliki scope workspace ditutup bagi sesi anggota dan pada mode server. Editor Studio lama tetap untuk solo lokal; kolaborasi melalui API proposal/apply dan konsol M8 menggunakan revision yang sama, bukan multi-cursor real-time.

`CLIPPER_M8_SERVER_MODE=1` mengaktifkan bearer-only untuk API M8. Ini **tidak membuka jaringan atau menyiapkan HTTPS/SSO**. Host eksternal harus diset operator melalui `CLIPPER_M8_ALLOWED_HOSTS`. Deployment produksi, TLS, pemisahan worker tidak dipercaya dan SSO memerlukan pekerjaan/validasi tambahan. Sesi anggota tidak dapat memilih path host, endpoint atau asset ID baru di luar bahan proyek; impor/relink host disiapkan operator lokal.

Koleksi dan arsip hanya mengubah organisasi metadata. Pemindahan workspace membutuhkan owner pada kedua workspace dan pemeriksaan antrean. Komentar menyimpan timecode sumber, source identity dan revision. Link review M7 memakai expiry dan revocation; preview bukan DRM. Endpoint M8 `/reviews` membuat link tanpa menyimpan token mentah dalam receipt perintah.

Backup memuat snapshot, transkrip, riwayat, berkas dan registry aset yang dirujuk. Checksum/CRC diperiksa. Restore oleh operator lokal membuat **proyek baru** dalam workspace berizin, mempertahankan snapshot revision dan memetakan source/take/asset paths. Proyek lama tetap tersedia. Periksa kembali freshness, font/relink dan render pada host tujuan. Credential, sesi akses, publikasi aktif dan link publik tidak diputar ulang. Cloud sync belum disediakan.

Paket diagnosis memuat status ringkas yang dapat ditinjau: tanpa media/transkrip/path sumber/token/log mentah. Tidak dikirim otomatis ke siapa pun.

## 7. Workflow dan webhook

Workflow dapat dijalankan pada proyek yang sudah ada atau folder lokal yang dipilih operator solo. Pemantauan hanya direct children (maksimal 200 nama per scan), menunggu ukuran/mtime stabil pada dua scan selama setidaknya 10 detik, menolak symlink, dan memakai content identity serta import operation ID. Atur folder khusus agar file di luar cakupan scan tidak terlewat.

Tahapan analyze → selection M3 → render batch → delivery M7 tetap memakai core. Job berat berjalan serial sesuai queue/resource guard lama. Guard yang meminta review menghentikan workflow pada `awaiting_review`, bukan dilewati. Sesudah delivery, state `awaiting_publish_approval`: tidak ada autopublish tanpa approval final tepat. Uji model dan kualitas cerita tetap mengikuti gerbang M2–M7.

Webhook/CMS umum memakai outbox event per workspace, ID tetap dan HMAC SHA-256. Operator harus mengisi `CLIPPER_M8_WEBHOOK_HOSTS` dengan hostname HTTPS tujuan yang dipilih. Resolusi DNS dipastikan beralamat publik dan IP dipin pada koneksi TLS; redirect tidak diikuti.

Setelah membuat subscription, klik **Buat kunci verifikasi webhook** untuk memperoleh kunci baru; kunci lama dicabut. Salin kunci sendiri ke penerima. Verifikasi `X-Clipper-Signature` terhadap HMAC dari `timestamp + '.' + body`, cek umur timestamp, dan deduplicate `X-Clipper-Event-ID`. Retry dapat mengirim event yang sama lebih dari sekali. Tidak ada secret akun dalam payload. Adapter CMS vendor tertentu belum dinyatakan teruji.

## 8. API, Python, CLI dan MCP

Layanan HTTP:

```text
POST /api/studio/m8/v1/command
GET  /api/studio/m8/v1/events
POST /api/studio/m8/v1/sessions
POST /api/studio/m8/v1/reviews
POST /api/studio/m8/v1/oauth/start
GET  /api/studio/m8/v1/oauth/{id}
GET  /api/studio/m8/v1/files/{id}
```

Contoh command baca:

```json
{"schema_version":1,"action":"project.list","args":{}}
```

Perintah mutasi membutuhkan `command_id` stabil (8–160 karakter). Ulangi ID hanya untuk isi dan aktor yang sama. Receipt selesai dikembalikan ulang tanpa menjalankan efek kedua. Hasil perintah yang terputus diberi status rekonsiliasi; inspeksi event/antrean sebelum menggunakan ID baru. Request maksimal 1 MiB.

Dari folder mesin Windows:

```powershell
.\.venv\Scripts\python.exe -m clipper.m8_cli command status
.\.venv\Scripts\python.exe -m clipper.m8_cli command project.list
.\.venv\Scripts\python.exe -m clipper.m8_cli command publish.list --args-file .\args.json --command-id daftar-publish-001
```

Python:

```python
from clipper.m8_client import Client
client = Client('http://127.0.0.1:8765')
receipt = client.command('project.list')
```

Token anggota dibaca dari `CLIPPER_M8_TOKEN`, bukan parameter CLI/URL. Server nonlokal memerlukan HTTPS pada client. Operator lokal dapat membuat sesi dari folder mesin:

```powershell
.\.venv\Scripts\python.exe -m clipper.m8_cli session --user reviewer1 --role reviewer --hours 24
```

Perintah tersebut menampilkan token satu kali untuk disalin operator. Simpan dengan baik; log/chat diagnosis tidak memerlukannya.

Worker tambahan pada host dengan database, media dan vault yang sesuai:

```powershell
.\.venv\Scripts\python.exe -m clipper.m8_cli worker
```

Worker menggunakan config `.env`, `.env.pro` dan brand lokal yang sama, serta lease database. Jangan menjalankan copy database independen sebagai worker kedua untuk akun/approval yang sama. Hentikan dengan Ctrl+C sebelum upgrade/rollback.

MCP stdio:

```powershell
.\.venv\Scripts\python.exe -m clipper.m8_cli mcp
```

Client meluncurkan proses, menjalankan initialize/notifications initialized, kemudian tools/list/tools/call. Tool tersedia: `clipper_status`, `clipper_projects`, `clipper_command`. Stdout hanya JSON-RPC per baris. Protocol version yang diiklankan adalah `2025-06-18`.

Daftar aksi, schema dan contoh tersedia di `docs/m8/COMMANDS.md` dan `docs/m8/command-v1.schema.json`. Registrasi provider/plugin menyimpan capabilities dan bukti probe, **tidak mengeksekusi kode pihak ketiga**. Isolasi deployment yang belum tersedia tidak dilabeli sandbox berhasil.

## 9. Pengujian dan rollback

`CEK_M8_RUNTIME.cmd` memeriksa import dan versi tanpa menghubungkan akun. `JALANKAN_UJI_M8.cmd` menjalankan pytest jika dependency pengujian tersedia. Fixture media adalah warna/tone dan transkrip buatan; fixture API bukan unggahan akun nyata. Bukti native browser/Windows, DPAPI Windows, akun platform nyata dan native editor tetap terpisah.

Rollback: hentikan server dan semua worker, lalu jalankan `PULIHKAN_M8_4_0_19.cmd`.

- Bila hanya kode yang berubah dan belum ada data M8 yang memerlukan fitur baru, rollback kode mempertahankan data kompatibel M7.
- Bila akun, sesi, publikasi, workflow/catatan atau workspace M8 sudah dipakai, installer menahan rollback biasa agar tidak meninggalkan state yang tidak dikenali M7.
- Setelah memahami pemulihan state, operator dapat menjalankan:

```powershell
py -3 complete_installer.py "D:\Folder\Clipper" --rollback --restore-project-state
```

SQLite terbaru dicadangkan ke `studio4-latest-before-rollback.sqlite3` sebelum checkpoint pra-upgrade dipulihkan. Aktivitas remote tidak dibatalkan dengan mengembalikan SQLite. Durable publish receipts tetap dipertahankan di folder kerja. Periksa akun/remote state sebelum membuat permintaan ulang setelah pemasangan kembali M8.

## 10. Cakupan yang masih terbuka

Trace 44 ID: 26 implemented_local, 8 implemented_conditional, 9 partial, 1 blocked. Pengujian lokal bukan pengganti acceptance akun/mesin Anda.

Belum ditutup: Meta direct publishing, thumbnail/subtitle upload API langsung, adapter CMS vendor, scouting tren otomatis, prediksi drop-off terkalibrasi, retraining ranking otomatis, cloud sync, provider SSO, eksekusi plugin baru dalam sandbox produksi dan deployment always-on otomatis. YouTube live acceptance serta Windows DPAPI belum dilakukan di lingkungan pengembangan ini. Backlog M7 Resolve teks/font EX05 dan native-import target tetap tercatat; M8 tidak menghapusnya.

Rujukan kontrak: arsitektur 120 halaman hlm. 54, 65–67, 106–111; dokumentasi resmi Google OAuth Desktop/YouTube resumable/Analytics, TikTok Content Sharing Guidelines dan MCP 2025-06-18. Tautan lengkap ada pada laporan rilis.
