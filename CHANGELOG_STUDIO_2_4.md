# Perubahan 2.4

Basis: fork `akbarttnjg/clipper_pro` commit `05eefb4ad40f022071ec124591f765f408461a53`, beserta pembaruan lokal 2.3 dan 2.3.1. Paket ini menyertakan perbaikan posisi/perataan serta penghapusan banner judul sebelumnya.

- B-roll lokal dan adapter Pexels, Pixabay, Coverr; pencarian kontekstual memakai Qwen lokal, cache, batas unduh, metadata kredit, serta fallback sumber asli.
- Editor ilustrasi per clip: preview, waktu sumber, alasan dan centang aktif. Waktu sisipan dipetakan kembali setelah pemangkasan jeda. Audio stok dibuang.
- Ekspor video sumber, sisipan B-roll, tipografi dan suara dalam layer terpisah. Dua rasio didukung; sisipan tidak menyatu ke video dasar paket editor.
- Sasaran penonton per sumber dan per clip. Prompt pemilihan/batas menekankan pembahasan mandiri dan penutup tuntas; pertanyaan baru di akhir ditandai.
- Pemenggalan frasa dan susunan baris berbasis pengukuran font. Mengurangi kata tunggal, kata penghubung menggantung, dan pembesaran aksen berlebihan.
- Preset Studio editorial baru; enam preview template dirender ulang dengan mesin versi ini. Gerak narasi mengikuti penekanan, bukan pergantian arah acak tiap frasa.
- Komposisi materi 16:9 berdampingan, materi 9:16 bertingkat, serta perlindungan jeda menulis. Materi tidak ditutup B-roll.
- Perapian tampilan kata dengan durasi ASR terlalu panjang; peringatan angka tetap perlu review sumber. Audio/transkrip asli dipertahankan.
- Panel edit Tipografi / Visual / Cerita / Audio. Pengaturan koleksi/API tersendiri; key tidak kembali ke UI atau paket.
- Mode pembuka sesi baru mengikuti urutan asli. Tidak ada banner judul otomatis. Preferensi kutipan pembuka sesi lama tetap dapat dimatikan pada Cerita.
- Polling UI memperbarui hasil proses singkat walaupun status aktif terlewat; alasan B-roll tidak tersedia tetap dapat dibaca.
- Versi render/cache 2.4. Kualitas teknis dan catatan review editorial dilaporkan terpisah.

Tidak ada dependensi atau model wajib baru. Adapter API diuji dengan respons simulasi; akses akun langsung dan impor native pada editor pengguna masih memerlukan verifikasi.
