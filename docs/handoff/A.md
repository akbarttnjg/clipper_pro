# Serah terima A — upgrade 01–22

Tanggal: 5 Oktober 2026. Acuan: pembagian paralel revisi 2 yang dikirim pengguna.

- Baseline: `b4772099c5591e8a83152a767ecb1004972b266b`, Clipper 3.3.
- Base patch / C0 yang sudah diambil: `f67b03280774089f8f95ae8d94018377c4897b93` dari `integration/upgrade43`.
- Branch: `feature/upgrade01-22`. Head final tercantum dalam `manifest.json` paket pengiriman dan dapat dilihat melalui `git rev-parse HEAD`.
- Producer pertukaran: `A-01-22.1`; envelope C0 versi 1 dengan `state` dan `payload`.
- Status: implementasi A, kompatibilitas validator C0 nyata dan tes terarah tersedia. Integrasi layanan produksi, UI utama, scheduler baru dan paket rilis gabungan dimiliki B dan **belum diverifikasi end-to-end**.
- Patch ini tidak mengedit `app.py`, `config.py`, `pipeline.py`, `storage.py`, `qc.py`, `editplan.py`, `illustrations.py`, kerangka UI, requirements, launcher atau installer.
- Prototype sebelum pembagian paralel disimpan terpisah. Jangan menggabungkan prototype tersebut atau menimpa folder aplikasi dengan ZIP lama.

## 1. Status per nomor

Semua baris di bawah diimplementasikan pada modul A dan mengikuti envelope C0 yang diterbitkan B. “Tes” menyebut bukti yang benar-benar dijalankan, bukan jaminan mutu model pada video pengguna. Belum ada baris yang dinyatakan sebagai rilis gabungan C0/B.

| No. | Hasil A | Bukti tes | Penyambungan oleh B |
|---|---|---|---|
| 01 | Alias topik/konteks, istilah keuangan, alasan dan asal koreksi | Istilah XAUUSD, bearish dan timeframe; percakapan umum tidak ikut diganti | Daftarkan konfigurasi dan memori proyek |
| 02 | Pemeriksaan ulang audio berbasis frasa, alignment konservatif, gabung lineage; angka/negasi/manual dilindungi | Mock hasil ASR, confidence, waktu dan penggabungan frasa | Fingerprint ASR harus menyertakan budget dan alias revision; akurasi Whisper nyata belum diukur |
| 03 | OCR CPU berbatas sampel; saran waktu/box/teks/keyakinan, tanpa mengganti ucapan otomatis | RapidOCR nyata pada fixture dan satu frame hasil pengguna; saran tidak memodifikasi transkrip | Scan media kanonis, lampirkan bukti ke transkrip |
| 04 | Heard words tetap utuh; teks tampilan membersihkan spasi/tanda baca | Tes angka `1.250,50`, negasi, sumber asli dan lineage | Simpan heard/display/override terpisah |
| 05 | Alias dapat dibuat, diubah, diganti ID, dinonaktifkan dan dihapus; helper perubahan murni | Tes scope topik, rename, disable, angka dan negasi | Jalankan `propose_change` di transaksi revisi B |
| 06 | Komponen antrean tinjauan: alasan, saran, konteks audio, koreksi dan draf | Browser nyata dengan layanan simulasi: konflik, refresh, respons klip terlambat | Sambungkan pemutar audio dan mutation service |
| 07 | Pemenggalan frasa/baris memperhitungkan istilah majemuk, negasi dan laju baca | Tes compound dan kata negatif, render nyata fixture | Berikan kata render dari timeline B |
| 08 | Kalibrasi cap-height tujuh font; ukuran aksen dan kata biasa lebih konsisten | Tujuh font + render 9:16 dan 16:9 | Hash isi font menjadi dependensi caption |
| 09 | Meaning emphasis valid dipertahankan; penekanan frasa menyertakan negasi | Tes keyword majemuk, fallback dan suite intelligence lama | Batalkan hint yang tidak cocok dengan revisi transkrip |
| 10 | Durasi diam lebih panjang, gerak masuk/keluar terikat durasi; QC seluruh envelope animasi | Lima gaya × dua rasio; batas gambar, kata/frasa hilang, alignment | Delegasikan QC ke `caption_checks` dan tampilkan peringatan waktu baca |
| 11 | Komposisi materi/pembicara menyesuaikan rasio/aspek materi | FFmpeg nyata dua rasio dengan geometri kanonis fixture | MediaContext dan normalisasi rotasi B38 |
| 12 | Kotak OCR/wajah/materi dilindungi; posisi panel tetap jika masih aman | Koordinat, slide lama, collision dan render fixture | Gunakan hasil scene untuk anchor caption varian |
| 13 | Pencarian pendek/panjang, jembatan batas dan putaran tujuan tambahan | Tes jendela akhir sumber dan panggilan pencarian baru; model disimulasikan | Teruskan daftar kandidat lama saat “cari lagi” |
| 14 | Alasan format/waktu/evidence/editorial dicatat dan tersedia di panel | Tes seleksi dan laporan penolakan | Simpan laporan sesuai analysis revision, tautkan tinjau batas |
| 15 | Bukti konteks sebelum/sesudah, rekam batas sebelum/sesudah perbaikan | Suite review/grounding/boundary lama + baru | Edit batas tetap memakai timeline/revision service B |
| 16 | Petunjuk pergantian slide, perubahan gambar, energi suara dan awal ucapan | OCR/audio fixture nyata, pemilihan jendela cue | Jalankan tahap source evidence sebelum discovery |
| 17 | Pemeriksaan semantik lokal untuk parafrasa; beda jenis cerita/angka/negasi tidak dibuang sembarang | Respons Ollama disimulasikan; pengecualian diuji | Benchmark keragaman pada sumber mentah dengan model lokal |
| 18 | Coverage, putaran, revision, asal legacy/manual/analysis dan kandidat siap dibedakan | Tes “cari lagi”, histori dan status legacy stale | ID konten/kandidat/proyek stabil dari C0 |
| 19 | Poster dari frame terbaca, durasi/status/error/retry dalam komponen | Decode video nyata dan browser memuat poster/metadata | B menyajikan URL aset aman dan menyinkronkan hasil scheduler |
| 20 | Beberapa kueri konkret/sinonim, ranking metadata, kandidat berikutnya bila visual ditolak; cache pilihan divalidasi | Cache rusak diperbaiki; pencarian lokal; kandidat kedua dicoba | Kunci provider tetap di pengaturan B; invalidasi koleksi/intent |
| 21 | Sampel frame aktual, kualitas, biaya proses dan vision lokal opsional; status metadata terpisah | Frame nyata, payload tiga gambar dengan model mock, cache dan mode required | Model multimodal nyata belum diunduh/diuji; gunakan antrean GPU berurutan |
| 22 | Materi OCR sumber, koleksi lokal bertag, asal/izin, diagram DBD/RBR dengan SVG editable | Sumber/diagram/MP4/poster nyata; metadata lokal | B menjadwalkan aset dan menyediakan tautan unduh/pemutar |

Tidak ada kuota wajib 10 klip. Jumlah hasil tetap mengikuti gagasan valid dan budget pencarian; lulus tes tidak membuktikan hasil akan selalu sebanyak Opus/Vizard.

## 2. Batas modul dan facade

Modul tambahan A: `analysis_options`, `analysis_adapter`, `api_analysis`, `correction_memory`, `evidence`, `discovery`, `caption_checks`, `illustration_catalog`, `asset_review`, `source_assets`.

Komponen UI hanya ada di `static/features/analysis.js` dan `analysis.css`; tes/fixture di `clipper/tests/parallel_a/`.

Facade `illustrations.py` dari C0 sudah meneruskan `recipe_path`, `propose`, dan `prepare` ke `illustration_catalog`. Signature `prepare(..., proposer=...)` dipertahankan agar injection point legacy tetap bekerja. Pertahankan `attach`, pemetaan waktu, credits dan scheduling di sisi B. Jangan menyalin ulang implementasi lama menimpa katalog A. Adapter katalog menerima `input_fingerprint` sebagai keyword pada `recipe_path` dan `prepare`.

Facade `qc.py` C0 sudah mengimpor pemeriksaan milik A. B masih perlu memasok daftar kata melalui `caption_checks.inspect_caption_plan(plan, cfg, expected_words=render_words)` untuk mengaktifkan pemeriksaan tambahan dalam jalur final. `expected_words=True` hanya memeriksa kosong/tidak; berikan daftar kata agar **hilangnya satu frasa** juga terdeteksi.

## 3. Kontrak C0 v1 dan urutan integrasi

Adapter A memakai `clipper.contracts.envelope` dan `validate` dari C0 `f67b032`. Tes dua arah A/C0 lulus: snapshot A diterima validator bersama, MediaContext dari C0 diterima A, dan `AnalysisHost`/`mount` tetap kompatibel. Capability layanan produksi tetap harus diuji ketika B menyambungkannya.

1. B memasok `source_id` berbasis isi, ID proyek/klip/varian stabil, revision, dan fingerprint dependensi. Path bukan identitas sumber. Semua rentang sumber memakai detik `[start,end)`.
2. B menyiapkan `MediaContext` kanonis, ukuran display, audio stream, durasi, sumber waktu dan working path; jika belum kanonis, `analyze_scenes` mengembalikan blocked. Adapter tidak menerapkan rotasi/normalisasi kedua kali. Rotasi 90/270, VFR dan audio track alternatif masih gate B38.
3. Jalankan `evidence.scan(media,cfg,duration,input_fingerprint=...)`; hasil `suggestions(words,report)` ditaruh pada `transcript['ocr_suggestions']`. OCR hanya mendukung peninjauan. Tulisan subtitle yang sudah terbakar juga dapat terbaca sehingga tidak boleh diterima otomatis sebagai ucapan.
4. `transcript_snapshot(...)` menghasilkan envelope `{schema_version, producer_version, kind, source_id, input_fingerprint, state, payload}`. Heard words, display tokens, origin mapping, review queue dan corrected words berada di `payload`. Field `payload.words` adalah salinan kompatibilitas heard words; jangan memperlakukannya sebagai teks tampilan terpisah. B mempertahankan raw words sebelum koreksi pertama. ID token berubah antar ASR take; token gabungan yang terpotong batas klip ditandai `requires_alignment`.
5. Panggil `story.select(transcript,cfg,progress,existing=current_candidates)` ketika mencari pembahasan tambahan. `existing=None` adalah pencarian awal. Kandidat lama digunakan sebagai pengecualian, bukan dihitung hasil baru. Simpan `selection-report.json`/coverage sesuai sumber dan analysis revision.
6. `caption_plan` mengonsumsi kata dengan `token_id`, `origin_word_ids`, serta waktu **output dari B**. `frame_mapper(start,end,fps)` wajib disuntikkan B; frame akhir eksklusif. Plan membawa variant ID, timeline revision, fps rasional dan token references.
7. Panggil `illustration_catalog.prepare(...,input_fingerprint=...)`, lalu `asset_proposal_set(...)`. Usulan membawa span sumber, referensi frasa, fingerprint isi aset, poster, provenance/rights dan `usage_status=not_scheduled`. B23 menentukan durasi terpakai, offset aset dan pemakaian lintas shot.
8. B mengaktifkan optional router/panel hanya setelah layanan revisi tersedia. Menambahkan file A saja **belum memasang endpoint atau panel pada aplikasi**.

`correction_proposal` membedakan `expected_revision` proyek dari `expected_transcript_revision` snapshot. Keduanya bukan angka yang harus sama. B memeriksa ulang target, provenance, teks sebelumnya, lineage dan revision dalam satu transaksi atomik.

`manual_candidate_policy(count)` tidak membatasi 20 kandidat. B masih perlu menghapus batas route lama sambil mempertahankan validasi waktu dan revision; A tidak mengedit route lama.

### Layanan yang disuntikkan ke API dan UI

```python
from clipper.api_analysis import create_router
# Fungsi di bawah disediakan C0/B; jangan memakai penyimpanan fixture di produksi.
app.include_router(create_router({
    'get_snapshot': project_analysis_snapshot,
    'submit_changes': commit_analysis_changes,
    'run_stage': enqueue_analysis_stage,
}))
```

Optional endpoints: GET `/api/analysis/capabilities`, GET `/snapshot`, POST `/changes`, POST `/stage`. Seluruh callback boleh sync atau async. Factory juga menerima `AnalysisHost(snapshot, submit_changes, get_words_page, run_stage)` dari C0, dan `mount(app, host, create_router)` tidak menggandakan prefix. Pagination tetap dilayani B melalui host.

`get_snapshot(target)` menerima tiga ID stabil dan menghasilkan:

```json
{
  "schema_version": 1,
  "target": {"project_id":"stable-project","clip_id":"stable-clip","variant_id":"portrait"},
  "revision": 19,
  "capabilities": {"correction":true,"aliases":true,"shared_utterance":false,"assets":true,"asset_changes":true,"discovery":true},
  "data": {"transcript":null,"aliases":[],"discovery":null,"boundary_context":null,"asset_proposals":null,"caption_preview":null}
}
```

Isi `transcript` dan `asset_proposals` dengan envelope C0 A lengkap, bukan hanya payload. Sediakan transkrip untuk konteks klip aktif, bukan seluruh transkrip 10.001 kata. B43 menyediakan pemuatan bertahap. `caption_preview` harus memuat `url` dan revision proyek yang cocok. B mengubah path aset menjadi URL yang diotorisasi (`preview_url`, `poster_url`, `editable_url`) sebelum mengirim ke browser.

`submit_changes` menerima target, `expected_revision`, `operation_id`, dan operations. Operasi A: `correct_token`, `alias_upsert`, `alias_remove`, `asset_enabled`, `asset_metadata`, `analysis_settings`. Balasan berhasil `{status:'ready',revision:N}`, konflik `{status:'conflict',revision:N,conflicts:[...]}`. B wajib idempotent terhadap operation ID, menjaga draf, memvalidasi operasi dan menulis atomik. Route A meneruskan konflik dengan HTTP 409. Wrapper fetch harus mengembalikan body konflik ke komponen.

`run_stage` menerima target, revision dan stage ID: `source_evidence`, `correction`, `discovery`, `boundary_review`, `asset_proposals`, `asset_visual_review`. B memiliki queue/cancel/fingerprint/commit; respons queued bukan hasil analisis selesai. Komponen memperlihatkan status yang diberikan host.

```javascript
import {mountAnalysis} from '/static/features/analysis.js';
// Muat analysis.css satu kali pada shell milik B.
const panel = mountAnalysis(root, {
  api: {get_snapshot, submit_changes, run_stage},
  target: {project_id, clip_id, variant_id}, revision,
  onChange: refreshHostSnapshot,
  onListen: playCanonicalSourceSpan,
  onPreview: enqueueCurrentPreview
});
// Pindah klip/varian: panel.update({target: newTarget, revision: newRevision}).
// Tutup panel: panel.destroy(). Tidak ada akses state global editor lama.
```

## 4. Konfigurasi, dependensi, cache dan pemulihan

`analysis_options.SETTINGS` berisi tipe, default, batas dan tahap yang terdampak. `DEPENDENCIES` adalah deklarasi untuk cache graph B31. `AnalysisConfig` hanya adapter baseline/tes; B dapat mendaftarkan field setara pada konfigurasi bersama.

- OCR default maksimal 48 frame, jarak target 8 detik; sampling direntangkan ke seluruh sumber. Ini bukan inspeksi setiap frame. Boleh dinonaktifkan; OCR tidak tersedia menghasilkan status/peringatan.
- Discovery tambahan default 8 jendela, batas 24; tidak ada kuota klip. Cue membantu prioritas tetapi tidak menjamin seluruh demonstrasi tertangkap.
- Query B-roll default 3, kandidat visual default 2 per sumber/provider; batas masing-masing 5 dan 3.
- `vision_model=''`, policy `optional` secara default. Tanpa model, frame dibaca dan status visual tetap belum terverifikasi. `required` menolak aset yang belum berhasil diverifikasi; `off` melewati pemeriksaan model.
- Tambahan OCR yang **diuji**: `rapidocr-onnxruntime==1.4.4`. Pillow/OpenCV/requests/FFmpeg menggunakan dependency aplikasi yang sudah ada. B memiliki requirements/installer; patch A tidak mengubahnya.
- Vision memerlukan model multimodal lokal yang dipilih dan tersedia di Ollama. Tidak ada unduhan model otomatis. Model teks dan vision dilepas setelah tahap (`keep_alive=0`). Untuk RTX 3050 4 GB, B perlu antrean GPU berurutan dan pengukuran perangkat; belum ada klaim muat/kecepatan model tertentu.
- Playwright adalah dependency pengujian pengembang, bukan dependency pengguna aplikasi.

`asr_fingerprint(...)` memuat budget recheck dan revisi alias selain identitas audio/konten/model. Cache ASR lama `storage.source_key` belum otomatis berubah; B harus memakai fingerprint A dalam layanan cache, bukan hanya memperbarui slider budget.

`evidence.scan` dan katalog menerima fingerprint penuh dari B. Tanpa fingerprint, scan menandai `legacy_metadata_only`; jangan menyebutnya identitas konten yang kuat. B harus memisahkan work/cache per proyek dan sumber. Alias, timeline, font, media/context, aset dan varian termasuk dependensi yang dijelaskan pada registry.

Penilaian stock memvalidasi index, alasan dan kutipan metadata sebelum cache. Penilaian visual dan poster memakai SHA-256 seluruh isi aset. Katalog memeriksa berkas/fingerprint aset sebelum memakai recipe cache. Berkas berubah pada path, ukuran dan timestamp sama tetap terdeteksi oleh hash isi aset. Revision sumber/metadata koleksi tetap perlu dimasukkan fingerprint B.

Tidak ada migrasi proyek, penghapusan berkas atau penghapusan cache pengguna dalam patch A. Memori file legacy tersedia untuk kompatibilitas; produksi memakai `correction_memory.propose_change(rows, operation)` di storage B. Bila tahap dibatalkan/gagal, B tidak boleh mengesahkan keluaran parsial sebagai revisi terbaru. Callback checkpoint A tersedia pada scan/scene/proposal adapter; penghentian proses/model yang sedang berlangsung dan resume adalah B41.

## 5. Bukti pengujian dan cara menjalankan

Lingkungan: Linux, Python 3.12, FFmpeg 6.1.1, CPU. Suite baseline dipertahankan.

```sh
python -m pytest clipper/tests -q
python -m clipper.tests.parallel_a.exchange_demo --output qa-a/exchange
python -m clipper.tests.parallel_a.media_smoke --output qa-a/media
```

Hasil suite pada paket ini: **294 passed**, satu peringatan deprecation Starlette/httpx, tanpa tes dilewati. Sebanyak 245 adalah tes warisan, 47 tambahan A dan 2 tes C0 B. Suite ini memuat mock untuk ASR/Ollama/provider; tes fungsi bukan benchmark mutu model.

`exchange_demo` menghasilkan contoh input/output dan request koreksi dengan revision proyek 19 serta revision transkrip 3. Source ID fixture bukan hash video produksi.

`media_smoke` membuat sumber sintetis 14 detik dengan gambar materi dan suara sine, membaca OCR nyata, merender **540×960 dan 960×540**, memeriksa durasi/kanvas/phrase, lalu membuat aset sumber, poster dan diagram SVG. Bahan ini sengaja bukan sampel akurasi transkripsi atau mutu cerita.

Pengujian browser memakai layanan revisi simulasi pada `ui_fixture.html`: payload revision, draf saat konflik, draf setelah refresh, respons klip terlambat diabaikan, poster, metadata video dan tombol retry tersembunyi setelah berhasil. Tidak ada page error. Untuk menjalankan pada mesin lain:

1. Jalankan media smoke dengan output folder yang tersedia melalui HTTP; sesuaikan dua URL `/qa-parallel-a/synthetic-source.*` di fixture bila perlu.
2. Sajikan root kerja melalui server HTTP.
3. Pasang Playwright/browser pada lingkungan pengembang, lalu jalankan `node clipper/tests/parallel_a/ui_smoke.cjs URL_FIXTURE screenshot.png`. `PLAYWRIGHT_CHROMIUM_EXECUTABLE` opsional.

**Belum diverifikasi:** benchmark sumber mentah 1–2 jam dengan transkrip acuan; angka akurasi Whisper/OCR; kualitas hasil semantik/vision Ollama nyata; Windows/NVENC/VRAM RTX 3050; rotasi/VFR/audio track melalui C0 nyata; 30–120 klip produksi; konflik/undo end-to-end di storage B; native import CapCut/DaVinci. ASS/MP4/SVG bukan bukti seluruh elemen dapat diedit identik di editor native.

## 6. Menerapkan patch

Paket berisi patch Git berurutan, catatan, fixture dan bukti pengujian; **bukan ZIP aplikasi untuk ditimpa**. Head/base/daftar perubahan tercantum dalam manifest. Jangan terapkan commit prototype lama.

Pada checkout integrasi yang bersih dan sudah memuat C0 `f67b032`, B meninjau lalu menerapkan patch berurutan:

```powershell
git switch integration/upgrade43
Get-ChildItem PATH_PAKET/patches/*.patch | Sort-Object Name | ForEach-Object { git am --3way $_.FullName; if ($LASTEXITCODE -ne 0) { throw "Selesaikan konflik sebelum lanjut" } }
python -m pytest clipper/tests -q
```

Alternatif bundle Git di paket: `git fetch PATH_PAKET/clipper-A.bundle feature/upgrade01-22:review/upgrade01-22`, lalu tinjau/merge branch tersebut. Pilih salah satu cara, jangan terapkan patch dan bundle dua kali.

Jika ada konflik, pertahankan kontrak C0 B dan logika analisis A, selesaikan secara eksplisit, lalu jalankan tes. `git am --abort` mengembalikan keadaan sebelum rangkaian patch jika rangkaian gagal. Tidak ada force-push atau perubahan main dalam pengiriman ini.

Urutan integrasi yang paling mendesak: (1) layanan revision/media context produksi di atas validator C0 yang sudah tersedia, (2) konfigurasi dan fingerprint, (3) facade katalog + QC + pipeline, (4) panel dan layanan audio/preview, (5) scheduler B23 dan pengujian render gabungan. B membuat satu paket rilis setelah gate gabungan lulus.
