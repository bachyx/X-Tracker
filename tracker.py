#!/usr/bin/env python3
"""
x-tracker — pantau siapa saja yang di-follow oleh akun X tertentu.

Login pakai akun (throwaway disarankan) via library twikit, ambil daftar
following tiap target, bandingkan dengan snapshot sebelumnya, lalu kirim
notifikasi follow/unfollow baru ke Discord webhook.

PERINGATAN: cara ini melanggar ToS X. Pakai akun cadangan, jangan akun utama.

Pemakaian:
    python tracker.py            # mode loop (polling terus sesuai interval)
    python tracker.py --once     # sekali jalan lalu keluar (cocok untuk cron)
"""

import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from twikit import Client
from twikit.errors import TwitterException, TooManyRequests

# Menambal twikit 2.3.3 agar login tidak gagal di 'KEY_BYTE indices'
# (X mengubah format manifest). Harus diimpor sebelum login.
import twikit_patch  # noqa: F401

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
TARGETS_PATH = BASE_DIR / "targets.json"
COOKIES_PATH = BASE_DIR / "cookies.json"
STATE_DIR = BASE_DIR / "state"

# Batas pengaman supaya tidak menarik halaman tanpa henti untuk akun
# yang follow puluhan ribu orang.
MAX_PAGES = 100
PAGE_SIZE = 100
PAGE_DELAY_SECONDS = 2  # jeda antar halaman agar tidak gampang kena rate limit


def log(message: str) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def load_config() -> dict:
    """
    Sumber konfigurasi (berurutan):
      1. config.json (lokal, berisi cookie) — kalau ada.
      2. targets.json (tanpa rahasia) — dipakai di GitHub Actions; cookie &
         webhook diambil dari environment variable.
    Environment variable selalu menimpa: X_AUTH_TOKEN, X_CT0, DISCORD_WEBHOOK.
    """
    config: dict = {}
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open(encoding="utf-8") as fh:
            config = json.load(fh)
    elif TARGETS_PATH.exists():
        with TARGETS_PATH.open(encoding="utf-8") as fh:
            config = json.load(fh)

    # Override dari environment (untuk CI / GitHub Actions — cookie via Secrets).
    config.setdefault("cookies", {})
    if os.environ.get("X_AUTH_TOKEN"):
        config["cookies"]["auth_token"] = os.environ["X_AUTH_TOKEN"]
    if os.environ.get("X_CT0"):
        config["cookies"]["ct0"] = os.environ["X_CT0"]
    if os.environ.get("DISCORD_WEBHOOK"):
        config["discord_webhook"] = os.environ["DISCORD_WEBHOOK"]
    if os.environ.get("HEARTBEAT_WEBHOOK"):
        config["heartbeat_webhook"] = os.environ["HEARTBEAT_WEBHOOK"]
    if os.environ.get("HEALTHCHECK_URL"):
        config["healthcheck_url"] = os.environ["HEALTHCHECK_URL"]

    if not config.get("targets") and not config.get("rotate_targets"):
        log("Tidak ada target. Isi config.json atau targets.json.")
        sys.exit(1)
    return config


def state_file(username: str) -> Path:
    return STATE_DIR / f"{username.lower()}.json"


def load_snapshot(username: str) -> dict | None:
    path = state_file(username)
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as fh:
        return json.load(fh)


def save_snapshot(username: str, following: dict[str, dict]) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    payload = {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "following": following,
    }
    with state_file(username).open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)


def post_discord(webhook: str, payload: dict) -> None:
    """Kirim payload mentah ke Discord webhook (pakai stdlib, tanpa dependensi)."""
    if not webhook or "discord.com/api/webhooks" not in webhook:
        log("Webhook Discord belum diatur dengan benar — notifikasi dilewati.")
        return
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook,
        data=data,
        headers={
            "Content-Type": "application/json",
            # Tanpa User-Agent, Discord (Cloudflare) balas 403 error 1010.
            "User-Agent": "x-tracker/1.0 (+https://github.com)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
    except Exception as exc:  # noqa: BLE001 — webhook gagal tidak boleh menghentikan bot
        log(f"Gagal kirim ke Discord: {exc}")


def send_discord(webhook: str, content: str) -> None:
    """Kirim pesan teks biasa."""
    post_discord(webhook, {"content": content[:1990]})


def _bigger_avatar(url: str | None) -> str | None:
    # X memberi avatar versi '_normal' (48px); '_400x400' jauh lebih tajam.
    return url.replace("_normal.", "_400x400.") if url else None


def build_change_embed(target: str, info: dict, is_follow: bool) -> dict:
    """Satu embed untuk satu akun yang baru di-follow / di-unfollow."""
    screen_name = info["screen_name"]
    return {
        "color": 0x2ECC71 if is_follow else 0xE74C3C,  # hijau / merah
        "author": {
            "name": f"@{target}",
            "url": f"https://x.com/{target}",
        },
        "title": f"{info.get('name') or screen_name}  (@{screen_name})",
        "url": f"https://x.com/{screen_name}",
        "description": (
            "➕ **Mulai di-follow**" if is_follow else "➖ **Di-unfollow**"
        ),
        "thumbnail": {"url": _bigger_avatar(info.get("avatar")) or ""},
    }


def send_change_notifications(webhook: str, target: str, added: list, removed: list) -> None:
    """Bangun embed untuk tiap perubahan, kirim maksimal 10 embed per pesan."""
    embeds = [build_change_embed(target, info, True) for info in added]
    embeds += [build_change_embed(target, info, False) for info in removed]

    header = f"🔔 **@{target}** — {len(added)} follow baru, {len(removed)} unfollow"
    for i in range(0, len(embeds), 10):
        chunk = embeds[i : i + 10]
        payload = {"embeds": chunk}
        if i == 0:
            payload["content"] = header
        post_discord(webhook, payload)


async def login(config: dict) -> Client:
    client = Client("en-US")

    # 1) Sesi tersimpan dari run sebelumnya.
    if COOKIES_PATH.exists():
        client.load_cookies(str(COOKIES_PATH))
        log("Cookie tersimpan ditemukan, memakai sesi itu.")
        return client

    # 2) Cookie dari browser (cara yang andal — login password diblok Cloudflare).
    cookies = config.get("cookies") or {}
    auth_token = cookies.get("auth_token", "").strip()
    ct0 = cookies.get("ct0", "").strip()
    if auth_token and ct0:
        client.set_cookies({"auth_token": auth_token, "ct0": ct0})
        client.save_cookies(str(COOKIES_PATH))
        log("Memakai cookie dari config (auth_token + ct0).")
        return client

    # 3) Fallback: login username/password (sering gagal karena Cloudflare).
    acc = config.get("account") or {}
    if not acc.get("password"):
        log(
            "Belum ada cookie maupun kredensial. Isi 'cookies' (auth_token & ct0) "
            "di config.json — lihat README bagian 'Ambil cookie'."
        )
        sys.exit(1)
    log("Mencoba login username/password (kemungkinan diblok Cloudflare)...")
    await client.login(
        auth_info_1=acc["username"],
        auth_info_2=acc.get("email", ""),
        password=acc["password"],
    )
    client.save_cookies(str(COOKIES_PATH))
    log("Login sukses, cookie disimpan.")
    return client


async def fetch_following(client: Client, screen_name: str) -> tuple[dict[str, dict], bool]:
    """
    Tarik seluruh daftar following sebuah akun, dipaginasi sampai habis.

    Mengembalikan (following, complete). complete=False bila pengambilan
    terputus (rate-limit / error / kena batas MAX_PAGES) sehingga daftarnya
    kemungkinan tidak utuh — pemanggil harus mengabaikan hasil parsial ini
    agar tidak menghasilkan notifikasi follow/unfollow palsu.
    """
    user = await client.get_user_by_screen_name(screen_name)
    result = await user.get_following(count=PAGE_SIZE)

    following: dict[str, dict] = {}
    pages = 0
    complete = False
    while result and pages < MAX_PAGES:
        for u in result:
            following[str(u.id)] = {
                "screen_name": u.screen_name,
                "name": u.name,
                "avatar": getattr(u, "profile_image_url", None),
            }
        pages += 1
        if not getattr(result, "next_cursor", None):
            complete = True  # habis secara wajar
            break
        await asyncio.sleep(PAGE_DELAY_SECONDS)
        try:
            result = await result.next()
        except TooManyRequests:
            log(f"  rate-limit X saat ambil @{screen_name} di halaman {pages}.")
            break
        except TwitterException as exc:
            log(f"  error saat paginasi @{screen_name}: {exc}")
            break
        if not result:
            complete = True  # halaman kosong = sudah habis
            break
    return following, complete


def diff_following(old: dict[str, dict], new: dict[str, dict]) -> tuple[list, list]:
    added = [info for uid, info in new.items() if uid not in old]
    removed = [info for uid, info in old.items() if uid not in new]
    return added, removed


async def check_target(client: Client, config: dict, screen_name: str) -> None:
    log(f"Mengecek @{screen_name} ...")
    try:
        current, complete = await fetch_following(client, screen_name)
    except TwitterException as exc:
        log(f"Gagal ambil following @{screen_name}: {exc}")
        return

    # Pengambilan tidak utuh (rate-limit dll). Jangan simpan & jangan bandingkan,
    # supaya tidak memicu notifikasi palsu. Pertahankan snapshot lama.
    if not complete:
        log(
            f"@{screen_name}: pengambilan TIDAK lengkap ({len(current)} terambil) "
            f"— ronde ini dilewati, snapshot lama dipertahankan."
        )
        return

    snapshot = load_snapshot(screen_name)
    save_snapshot(screen_name, current)

    if snapshot is None:
        log(f"@{screen_name}: snapshot awal disimpan ({len(current)} following).")
        if config.get("notify_on_first_run"):
            send_discord(
                config["discord_webhook"],
                f"📌 Mulai memantau **@{screen_name}** — {len(current)} following tersimpan.",
            )
        return

    added, removed = diff_following(snapshot["following"], current)
    if not added and not removed:
        log(f"@{screen_name}: tidak ada perubahan ({len(current)} following).")
        return

    log(
        f"@{screen_name}: {len(added)} follow baru, {len(removed)} unfollow. "
        f"Mengirim notif Discord..."
    )
    for info in added:
        log(f"  ➕ @{info['screen_name']} ({info['name']})")
    for info in removed:
        log(f"  ➖ @{info['screen_name']} ({info['name']})")
    send_change_notifications(config["discord_webhook"], screen_name, added, removed)


ROTATION_FILE = STATE_DIR / "_rotation.json"


def _load_rotation_index() -> int:
    try:
        with ROTATION_FILE.open(encoding="utf-8") as fh:
            return int(json.load(fh).get("index", 0))
    except Exception:  # noqa: BLE001 — file belum ada / rusak: mulai dari 0
        return 0


def _save_rotation_index(index: int) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    with ROTATION_FILE.open("w", encoding="utf-8") as fh:
        json.dump({"index": index}, fh)


def select_targets(config: dict) -> list[str]:
    """
    Akun di 'targets' dicek tiap siklus. Akun di 'rotate_targets' (yang
    follow-nya ribuan) dicek BERGANTIAN satu per siklus, agar tiap akun besar
    mendapat jatah rate-limit penuh dan bisa terambil utuh.
    """
    always = list(config.get("targets", []))
    rotate = list(config.get("rotate_targets", []))
    if not rotate:
        return always
    idx = _load_rotation_index() % len(rotate)
    chosen = rotate[idx]
    _save_rotation_index((idx + 1) % len(rotate))
    log(f"Rotasi akun besar: giliran @{chosen} ({idx + 1}/{len(rotate)}).")
    return always + [chosen]


HEARTBEAT_FILE = STATE_DIR / "_heartbeat.json"


def _load_last_heartbeat() -> datetime | None:
    try:
        with HEARTBEAT_FILE.open(encoding="utf-8") as fh:
            ts = json.load(fh).get("last")
        return datetime.fromisoformat(ts) if ts else None
    except Exception:  # noqa: BLE001 — file belum ada / rusak
        return None


def _save_last_heartbeat(now: datetime) -> None:
    STATE_DIR.mkdir(exist_ok=True)
    with HEARTBEAT_FILE.open("w", encoding="utf-8") as fh:
        json.dump({"last": now.isoformat()}, fh)


def _account_counts(config: dict) -> list[tuple[str, str]]:
    accounts = list(config.get("targets", [])) + list(config.get("rotate_targets", []))
    rows = []
    for sn in accounts:
        snap = load_snapshot(sn)
        rows.append((sn, str(len(snap["following"])) if snap else "—"))
    return rows


def maybe_send_heartbeat(config: dict) -> None:
    """Kirim ping 'masih hidup' ke Discord tiap heartbeat_hours jam."""
    hours = config.get("heartbeat_hours", 12)
    if not hours or hours <= 0:
        return  # fitur dimatikan
    now = datetime.now(timezone.utc)
    last = _load_last_heartbeat()
    if last is not None and (now - last).total_seconds() < hours * 3600:
        return  # belum waktunya

    webhook = config.get("heartbeat_webhook") or config.get("discord_webhook")
    fields = [
        {"name": f"@{sn}", "value": f"{cnt} following", "inline": True}
        for sn, cnt in _account_counts(config)
    ]
    embed = {
        "color": 0x2ECC71,
        "title": "🟢 x-tracker aktif",
        "description": (
            f"Bot berjalan normal. Pesan ini dikirim tiap ~{hours} jam.\n"
            "Kalau berhenti muncul, kemungkinan bot mati — cek tab Actions di GitHub."
        ),
        "fields": fields,
        "footer": {"text": "Pengecekan terakhir (UTC)"},
        "timestamp": now.isoformat(),
    }
    log("Mengirim heartbeat ke Discord.")
    post_discord(webhook, {"embeds": [embed]})
    _save_last_heartbeat(now)


def ping_healthcheck(url: str | None, suffix: str = "") -> None:
    """Ping healthchecks.io (dead-man switch). Gagal ping tidak boleh ganggu bot."""
    if not url:
        return
    try:
        req = urllib.request.Request(
            url.rstrip("/") + suffix, headers={"User-Agent": "x-tracker/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
    except Exception as exc:  # noqa: BLE001
        log(f"Gagal ping healthcheck: {exc}")


async def run_once(config: dict) -> None:
    hc_url = config.get("healthcheck_url")
    try:
        client = await login(config)
        for screen_name in select_targets(config):
            await check_target(client, config, screen_name)
            await asyncio.sleep(PAGE_DELAY_SECONDS)
        maybe_send_heartbeat(config)
    except Exception:
        # Beri tahu healthchecks bahwa run ini GAGAL → memicu alert lebih cepat.
        ping_healthcheck(hc_url, "/fail")
        raise
    # Run sukses → ping. Kalau ping berhenti muncul, healthchecks kirim alarm.
    ping_healthcheck(hc_url)


async def run_loop(config: dict) -> None:
    interval = config.get("poll_interval_minutes", 30) * 60
    while True:
        try:
            await run_once(config)
        except Exception as exc:  # noqa: BLE001 — loop harus tetap hidup
            log(f"Error pada siklus: {exc}")
        log(f"Selesai. Tidur {interval // 60} menit...")
        await asyncio.sleep(interval)


def main() -> None:
    config = load_config()
    once = "--once" in sys.argv
    asyncio.run(run_once(config) if once else run_loop(config))


if __name__ == "__main__":
    main()
