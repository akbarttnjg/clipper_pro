# Perubahan Studio 3.1

- Core editorial terhubung ke `story.review_candidate`, memakai respons Qwen yang
  sama. Kontrak bukti pembuka/isi/payoff dengan ID segmen, kutipan dan waktu sumber.
- Kandidat tidak lolos otomatis bila bukti gagal, konteks/akhir bermasalah,
  terdapat risiko editorial, atau angka/waktu ASR mencurigakan.
- Signature keputusan mengikat transkrip, judul, batas dan penonton. Perubahan isi
  menandai keputusan stale. Kegagalan pemeriksaan ulang membatalkan status lama.
- Cold open memindahkan kalimat utuh sekali; rentang sumbernya dikurangi dari body.
  Pembulatan frame tidak membuat kata terakhir muncul dua kali.
- Penekanan frasa semantik ikut dipetakan ke timeline output dan caption.
- B-roll dapat dilewati; pemilihan aset memakai perbandingan metadata kontekstual
  dengan alasan/kutipan metadata, fallback pembicara jika tidak cocok atau AI gagal.
- Mode otomatis untuk sesi baru dan tombol melanjutkan sesi lama sampai MP4/paket editor.
- Tab Cerita menampilkan bukti bertimestamp. Preset Shorts dinamis dan preview aktual.
- Cache/output versi 3.1, laporan pemeriksaan, dan pembuat paket upgrade ber-checksum.
- Tidak ada model/dependensi wajib baru. Sesi lama, posisi manual dan ekspor editor
  yang ada tetap didukung. Batas vision dan impor native dijelaskan dalam panduan.
