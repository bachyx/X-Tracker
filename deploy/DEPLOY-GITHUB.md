# Deploy x-tracker ke GitHub Actions (gratis, tanpa kartu kredit)

Bot berjalan terjadwal lewat GitHub Actions. Tidak perlu server. Cookie &
webhook disimpan aman di **GitHub Secrets** (tidak pernah masuk kode).

> ⚠️ **Dua hal yang harus kamu sadari:**
> 1. **Pakai repo PUBLIK.** Akun yang kamu pantau besar (ribuan following), satu
>    siklus makan ~6–10 menit. Repo privat hanya dapat 2.000 menit/bulan gratis —
>    tidak cukup. Repo publik = menit Actions **tak terbatas**. Konsekuensinya:
>    folder `state/` (daftar following yang dipantau) ikut publik. Itu data publik
>    X, **bukan** rahasia. Cookie & webhook tetap aman di Secrets.
> 2. **IP datacenter.** Runner GitHub pakai IP datacenter — X bisa lebih sering
>    rate-limit. Kalau cookie ditolak, perbarui Secrets (lihat bawah).

---

## 1. Siapkan repo & push kode

Di komputermu, dari dalam folder `x-tracker`:

```bash
git init
git add .
git status        # WAJIB cek: pastikan config.json & cookies.json TIDAK muncul
```

> `config.json` dan `cookies.json` sudah di `.gitignore` — pastikan keduanya
> **tidak** ada di daftar `git status`. Kalau muncul, JANGAN lanjut (cookie bisa
> bocor). 

Lalu commit & push ke repo **publik** baru (buat dulu di github.com → New repository → Public):

```bash
git commit -m "init x-tracker"
git branch -M main
git remote add origin https://github.com/USERNAME/x-tracker.git
git push -u origin main
```

## 2. Tambahkan Secrets

Di repo GitHub: **Settings → Secrets and variables → Actions → New repository secret**.
Buat 3 secret ini:

| Name | Value |
|------|-------|
| `X_AUTH_TOKEN` | nilai cookie `auth_token` dari browser |
| `X_CT0` | nilai cookie `ct0` dari browser |
| `DISCORD_WEBHOOK` | URL webhook Discord-mu |

## 3. Aktifkan & uji workflow

1. Buka tab **Actions** di repo. Kalau diminta, klik **"I understand my workflows, enable them"**.
2. Pilih workflow **x-tracker** → klik **Run workflow** (tombol dari `workflow_dispatch`) untuk uji manual sekarang, tanpa menunggu jadwal.
3. Klik run yang muncul → lihat log step **"Jalankan tracker"**. Harusnya muncul
   `@bachyx: snapshot awal disimpan ...` dst.
4. Run pertama membuat baseline (tidak ada notif kecuali `notify_on_first_run`).
   Mulai run berikutnya, perubahan follow/unfollow dikirim ke Discord.

Setelah itu workflow jalan otomatis tiap ~30 menit.

## 4. Mengubah daftar target

Edit `targets.json`, commit, push. Tidak perlu sentuh Secrets.

```json
{
  "targets": ["bachyx", "GuarEmperor"],
  "rotate_targets": ["Tma_420", "CrypSaf"],
  "notify_on_first_run": false
}
```

- `targets` → dicek **tiap run**.
- `rotate_targets` → akun besar, dicek **bergantian** 1 per run.

## 5. Mengubah frekuensi

Edit `.github/workflows/track.yml`, baris `cron`. Contoh tiap 15 menit:
`cron: "5,20,35,50 * * * *"`. Minimum GitHub 5 menit, dan jadwal sering molor
5–15 menit (wajar di tier gratis).

---

## Kalau cookie kedaluwarsa / ditolak

1. Di browser: login ulang ke x.com, ambil `auth_token` & `ct0` baru.
2. Di repo: **Settings → Secrets → Actions** → update `X_AUTH_TOKEN` & `X_CT0`.
3. Tab Actions → Run workflow untuk uji.

## Catatan penting

- **Jadwal mati setelah 60 hari tanpa aktivitas repo.** GitHub menonaktifkan
  cron workflow kalau repo tidak ada commit selama 60 hari. Karena bot meng-commit
  snapshot tiap ada perubahan, biasanya tetap aktif — tapi kalau lama sepi,
  cukup buka tab Actions dan Run workflow sekali untuk menghidupkan lagi.
- **Riwayat commit jadi ramai** oleh commit "update snapshot" otomatis. Itu normal.
- Snapshot `state/` publik = orang bisa lihat daftar following akun yang kamu
  pantau (data publik). Kalau ini mengganggu, pilihannya repo privat + perpanjang
  interval agar muat di 2.000 menit/bulan, atau self-host.
