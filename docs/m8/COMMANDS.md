# Aksi M8 v1

Semua aksi memakai POST `/api/studio/m8/v1/command`. `args` divalidasi per aksi oleh facade; field tak dikenal ditolak. Mutasi memakai command_id stabil. Endpoint credential/sesi/review capability terpisah agar token mentah tidak masuk receipt.

| Aksi | Izin awal |
|---|---|
| account.disconnect | manage |
| account.list | read (scope/role tambahan diperiksa aksi) |
| account.probe | manage |
| account.save | manage |
| analytics.export | read |
| analytics.get | read (scope/role tambahan diperiksa aksi) |
| analytics.observe | review |
| analytics.refresh | review |
| backup.create | manage |
| backup.restore | manage |
| capabilities | read (scope/role tambahan diperiksa aksi) |
| comment.save | review |
| cost.record | edit |
| diagnostics.create | read |
| effort.record | edit |
| events | read (scope/role tambahan diperiksa aksi) |
| experiment.assign | publish |
| experiment.create | review |
| feedback.policy | manage |
| feedback.rollback | manage |
| job.cancel | edit |
| job.list | read (scope/role tambahan diperiksa aksi) |
| job.resume | edit |
| job.submit | edit |
| plugin.list | read (scope/role tambahan diperiksa aksi) |
| plugin.register | manage |
| project.apply | edit |
| project.create | edit |
| project.get | read (scope/role tambahan diperiksa aksi) |
| project.list | read (scope/role tambahan diperiksa aksi) |
| project.propose | edit |
| publish.approve | approve |
| publish.cancel | publish |
| publish.draft | publish |
| publish.get | read (scope/role tambahan diperiksa aksi) |
| publish.list | read (scope/role tambahan diperiksa aksi) |
| publish.manual_receipt | publish |
| publish.preflight | read (scope/role tambahan diperiksa aksi) |
| publish.remote_edit | approve |
| publish.retry | publish |
| publish.revise | publish |
| record.list | read (scope/role tambahan diperiksa aksi) |
| review.list | read |
| review.revoke | review |
| session.revoke | manage |
| status | read (scope/role tambahan diperiksa aksi) |
| topic.import | review |
| webhook.list | manage |
| webhook.save | manage |
| workflow.resume | edit |
| workflow.run | edit |
| workflow.save | manage |
| workspace.configure | manage |
| workspace.create | manage |
| workspace.get | read (scope/role tambahan diperiksa aksi) |
| workspace.member | manage |
| workspace.organize | edit |

Untuk project.propose: project_id, expected_revision, operations (1–100), clip_id/variant_id sesuai target. Gunakan draft_id yang dihasilkan pada project.apply dengan revision aktif. Publish: buat draf dari package_content_id, clip_id, variant_id, akun dan metadata; ambil preflight hash sebelum approval.

Endpoint khusus: POST /sessions, POST /reviews, POST /oauth/start, GET /oauth/{id}, POST /webhooks/{id}/signing-key. Semuanya di bawah /api/studio/m8/v1 dan memeriksa actor/role.

Contoh baca:

```json
{"schema_version":1,"action":"publish.list","args":{"project_id":"GANTI_DENGAN_PROJECT_ID"}}
```
