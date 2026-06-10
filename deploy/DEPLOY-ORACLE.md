# Deploy x-tracker ke Oracle Cloud (Always Free)

Panduan menjalankan bot 24/7 di VM gratis-selamanya Oracle Cloud. Perkiraan
waktu: ~20–30 menit (sekali setup).

> ⚠️ **Catatan IP datacenter:** X/Cloudflare lebih galak ke IP datacenter
> dibanding IP rumahan. Cookie login biasanya masih tembus, tapi bisa lebih
> sering kena rate-limit dan sedikit menaikkan risiko akun di-flag. Pakai akun
> throwaway. Kalau cookie tiba-tiba ditolak di VM, ambil ulang `auth_token` &
> `ct0` dari browser dan perbarui `config.json` di VM.

---

## 1. Buat akun Oracle Cloud

1. Daftar di **https://www.oracle.com/cloud/free/**
2. Butuh **kartu kredit/debit** untuk verifikasi identitas (tidak ditagih untuk
   resource Always Free). Akan ada charge verifikasi kecil yang dikembalikan.
3. Pilih **Home Region** yang dekat (mis. Singapore / Tokyo). Region ini permanen
   untuk resource gratis — pilih yang baik-baik.

## 2. Buat VM (Instance)

1. Menu → **Compute → Instances → Create Instance**
2. **Image:** Canonical **Ubuntu 22.04** (atau 24.04)
3. **Shape:** klik *Change shape* → **Ampere (ARM)** → `VM.Standard.A1.Flex`
   - Set **1 OCPU / 6 GB RAM** (cukup; sisakan kuota untuk VM lain bila perlu)
   - Kalau muncul **"Out of capacity"**, coba region/AD lain, atau pakai shape
     AMD `VM.Standard.E2.1.Micro` (always-free juga, lebih kecil).
4. **Add SSH keys:** pilih *Generate a key pair for me* lalu **download private
   key** (atau tempel public key milikmu).
5. Klik **Create**. Tunggu status **Running**, catat **Public IP address**.

> Bot ini hanya butuh koneksi keluar (ke x.com & Discord) — **tidak perlu**
> membuka port masuk apa pun selain SSH (sudah default).

## 3. Masuk ke VM via SSH

Dari komputermu (ganti `KEY.key` & `IP`):

```bash
chmod 600 KEY.key
ssh -i KEY.key ubuntu@IP_PUBLIK_VM
```

## 4. Kirim file bot ke VM

**Dari komputermu** (di folder yang berisi x-tracker), kirim seluruh folder.
Cara paling mudah — `scp` (jalankan di komputer lokal, bukan di VM):

```bash
scp -i KEY.key -r ./x-tracker ubuntu@IP_PUBLIK_VM:~/x-tracker
```

> `config.json` (berisi cookie) ikut terkirim. Kalau kamu lebih suka aman,
> kirim tanpa config lalu buat ulang `config.json` langsung di VM.

Alternatif via git (kalau bot kamu taruh di repo **privat**):
```bash
# di VM
git clone https://github.com/USERNAME/x-tracker.git ~/x-tracker
# lalu buat config.json di VM (scp khusus file ini, atau nano)
```

## 5. Jalankan setup otomatis

**Di dalam VM:**

```bash
cd ~/x-tracker
bash deploy/setup-oracle.sh
```

Script ini memasang Python, dependensi, dan membuat service systemd
`x-tracker` yang **auto-start saat boot** dan **auto-restart saat crash**.

## 6. Pastikan config terisi

Kalau `config.json` belum ada/ belum lengkap di VM:

```bash
cd ~/x-tracker
cp config.example.json config.json   # kalau belum ada
nano config.json                      # isi cookies, targets, discord_webhook
sudo systemctl restart x-tracker
```

## 7. Pantau

```bash
systemctl status x-tracker      # status service
journalctl -u x-tracker -f      # log realtime (Ctrl+C untuk keluar)
```

Kamu akan lihat baris seperti `@bachyx: tidak ada perubahan (132 following)`.
Begitu ada follow/unfollow baru, notif embed masuk ke Discord.

---

## Perintah berguna

```bash
sudo systemctl restart x-tracker   # restart
sudo systemctl stop x-tracker      # hentikan
sudo systemctl start x-tracker     # jalankan
sudo systemctl disable x-tracker   # matikan auto-start saat boot
```

## Update bot nanti

```bash
# kirim ulang file yang berubah (dari lokal), lalu di VM:
sudo systemctl restart x-tracker
```

## Kalau cookie kedaluwarsa / ditolak

1. Di browser: login ulang ke x.com, ambil `auth_token` & `ct0` baru.
2. Di VM: `nano ~/x-tracker/config.json` → ganti nilai cookie.
3. Hapus cookie lama: `rm -f ~/x-tracker/cookies.json`
4. `sudo systemctl restart x-tracker`
