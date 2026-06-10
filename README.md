# x-tracker

Bot untuk memantau **siapa saja yang di-follow** oleh akun X (Twitter) tertentu.
Tiap interval, bot mengambil daftar following target, membandingkan dengan
snapshot sebelumnya, lalu mengirim notif **follow baru / unfollow** ke Discord.

> ⚠️ **Peringatan:** bot ini login pakai akun dan memakai internal API X lewat
> [`twikit`](https://github.com/d60/twikit). Ini **melanggar ToS X** dan akun bisa
> kena suspend. **Gunakan akun throwaway**, jangan akun utama. Jangan set interval
> terlalu pendek (default 30 menit sudah aman).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cp config.example.json config.json   # lalu isi
```

Edit `config.json`:

| Field | Keterangan |
|-------|-----------|
| `account` | Username/email/password akun X (dipakai hanya untuk fallback login) |
| `cookies` | **Cara utama login** — `auth_token` & `ct0` dari browser (lihat di bawah) |
| `targets` | Akun yang dicek **tiap siklus** (cocok untuk akun yang follow-nya sedikit) |
| `rotate_targets` | Akun besar (follow ribuan) yang dicek **bergantian** 1 per siklus, agar tiap akun dapat jatah rate-limit penuh dan terambil utuh |
| `discord_webhook` | URL webhook Discord. Buat di: Server Settings → Integrations → Webhooks |
| `poll_interval_minutes` | Jeda antar pengecekan (default 30) |
| `notify_on_first_run` | `true` kalau mau notif saat snapshot pertama dibuat |

> **Kenapa ada `rotate_targets`?** X membatasi ~100–115 halaman following per
> 15 menit. Akun yang follow ribuan menghabiskan jatah itu, sehingga kalau semua
> dicek sekaligus, sebagian terpotong dan memicu notif palsu. Bot otomatis
> melewati pengambilan yang tidak utuh, dan `rotate_targets` menyebar beban agar
> akun besar bisa terambil penuh secara bergiliran.

### Ambil cookie (WAJIB — login password diblok Cloudflare)

X sekarang memblok login username/password dari skrip (Cloudflare challenge).
Jadi kita pakai cookie dari sesi browser yang sudah login:

1. Login ke **https://x.com** lewat browser (pakai akun throwaway-mu).
2. Buka **DevTools** (F12) → tab **Application** (Chrome) / **Storage** (Firefox).
3. Buka **Cookies → https://x.com**.
4. Salin nilai 2 cookie ini:
   - `auth_token`
   - `ct0`
5. Tempel ke `config.json` bagian `cookies`:
   ```json
   "cookies": { "auth_token": "isi_auth_token", "ct0": "isi_ct0" }
   ```

> Cookie ini = sesi login-mu. Jangan dibagikan. Kalau kamu logout di browser,
> cookie-nya hangus dan harus diambil ulang.


## Jalankan

```bash
.venv/bin/python tracker.py          # mode loop (jalan terus)
.venv/bin/python tracker.py --once   # sekali jalan (untuk cron)
```

Login pertama menyimpan `cookies.json`, jadi run berikutnya tidak login ulang.
Kalau X minta verifikasi/2FA, hapus `cookies.json` dan login ulang.

### Contoh cron (tiap 30 menit)

```cron
*/30 * * * * cd /path/x-tracker && .venv/bin/python tracker.py --once >> tracker.log 2>&1
```

## Jalan terus & auto-restart

### A. Server dengan systemd (paling tahan banting)

Pakai `x-tracker.service` (sesuaikan path/user di dalamnya bila perlu):

```bash
sudo cp x-tracker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now x-tracker      # start + auto-start saat boot
journalctl -u x-tracker -f                 # lihat log
sudo systemctl restart x-tracker           # restart manual
```

Service ini auto-restart 30 detik setelah crash, dan otomatis hidup lagi
setelah server reboot.

### B. Tanpa systemd (watchdog sederhana)

`run-forever.sh` menjalankan bot dan me-restart otomatis kalau mati:

```bash
nohup ./run-forever.sh >/dev/null 2>&1 &   # jalan di background
```

> Catatan: watchdog tetap berhenti kalau mesin/sesi-nya mati total. Untuk
> ketahanan penuh lintas-reboot, pakai opsi systemd di atas pada server yang
> selalu nyala.

## Cara kerja

1. Login via `twikit` (pakai cookie tersimpan kalau ada).
2. Untuk tiap target: ambil seluruh following (dipaginasi, ada jeda antar halaman).
3. Bandingkan dengan `state/<username>.json` (snapshot lama).
4. Selisihnya → kirim ke Discord, lalu simpan snapshot baru.

## Catatan & batasan

- **Following list yang besar** ditarik bertahap; ada batas `MAX_PAGES` (100 hal ×
  100 = 10.000) di `tracker.py` sebagai pengaman — naikkan kalau perlu.
- Bot ini deteksi perubahan **antar polling**, bukan realtime. Follow yang terjadi
  lalu di-unfollow dalam satu interval tidak akan terdeteksi.
- Kalau sering kena rate limit / error, perpanjang interval dan `PAGE_DELAY_SECONDS`.
- Akun X yang **protected/private** following-nya tidak bisa dibaca kecuali akun
  bot-mu sudah di-follow balik / approved.
