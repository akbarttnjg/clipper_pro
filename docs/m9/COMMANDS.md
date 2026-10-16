# Kontrak perintah M9 v1

Semua aksi memakai POST /api/studio/m8/v1/command, schema_version 1, action dan args object. Aksi mutasi wajib command_id stabil. Tidak menerima filter FFmpeg atau shell bebas.

| Aksi | Izin minimum |
|---|---|
| `m9.buffer.submit` | edit |
| `m9.creative.generate` | edit |
| `m9.creative.propose` | edit |
| `m9.creative.save` | edit |
| `m9.dub.plan` | read |
| `m9.dub.submit` | edit |
| `m9.dub.accept` | edit |
| `m9.effects.submit` | edit |
| `m9.generate.submit` | edit |
| `m9.get` | read |
| `m9.job.cancel` | edit |
| `m9.job.get` | read |
| `m9.job.resume` | edit |
| `m9.list` | read |
| `m9.lut.register` | manage |
| `m9.media.import` | edit |
| `m9.podcast.submit` | edit |
| `m9.preset.export` | edit |
| `m9.preset.import` | edit |
| `m9.preset.load` | edit |
| `m9.preset.save` | edit |
| `m9.provider.probe` | manage |
| `m9.provider.reconcile` | manage |
| `m9.provider.register` | manage |
| `m9.record.create` | edit |
| `m9.record.finalize` | edit |
| `m9.record.get` | read |
| `m9.record.offset` | edit |
| `m9.record.pause` | edit |
| `m9.record.recover` | edit |
| `m9.record.revoke` | edit |
| `m9.record.seal` | edit |
| `m9.record.stage` | edit |
| `m9.status` | read |
| `m9.tts.submit` | edit |
| `m9.voice.register` | manage |

Endpoint media terpisah: POST /api/studio/m9/v1/tracks; PUT /api/studio/m9/v1/tracks/{id}/chunks/{seq} dengan X-Chunk-SHA256 dan X-Elapsed-Seconds; GET /api/studio/m9/v1/clock; POST /api/studio/m9/v1/invites (token sekali di respons, di luar receipt). Guest capability hanya berlaku di /api/studio/m9/guest/{room}/... .

Lihat signature/only() pada clipper/m9_recording.py, m9_effects.py, m9_creative.py, m9_providers.py dan m9_delivery.py untuk field serta batas tepat. UI /m9 menyediakan alur utama.

Contoh file args untuk m9.list:

```json
{"kind":"recording"}
```

Jalankan dari Python mesin: python -m clipper.m8_cli --url http://127.0.0.1:8765 command m9.list --args-file args.json . Nilai port mengikuti server Anda. Token berasal dari CLIPPER_M8_TOKEN.

## Tambahan 4.0.21

`m9.dub.plan`: project_id, expected_revision, clip_id, track_id (M2 disetujui), voice_id; audio_index dan max_rate opsional. Respons mengandung plan_digest dan semua cue.

`m9.dub.submit`: field plan yang sama ditambah plan_digest, reviewed_cue_ids (set tepat ID string), facts_reviewed=true, rights_reviewed=true. Menghasilkan tugas dubbing_m9, lalu item kind=dubbing status=awaiting_listening. Belum membuat proyek editor.

`m9.dub.accept`: id, expected_version, output_content_id (sha256:...), listened=true, timing_reviewed=true, facts_reviewed=true. Tugas dubbing_accept_m9 memeriksa kembali semua media dan sumber, lalu membuat proyek baru.

`m9.creative.save/generate`: clip_id, variant_id, start/end opsional untuk konteks sebelum batas jumlah unit/karakter. Co-editor hanya dapat diusulkan pada klip/rasio asal.
