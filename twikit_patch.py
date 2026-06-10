"""
Patch untuk twikit 2.3.3 — memperbaiki ekstraksi 'KEY_BYTE indices'.

X mengubah format manifest webpack di halaman depannya. Dulu refer file
ondemand.s sebagai  "ondemand.s":"HASH"  (yang dicari regex bawaan twikit),
sekarang jadi dua mapping terpisah:

    <chunkId>:"ondemand.s"   (nama)
    <chunkId>:"<hash>"       (hash)

Akibatnya twikit gagal menyusun URL ondemand.s.<hash>a.js dan melempar
'Couldn't get KEY_BYTE indices', sehingga login gagal total.

Modul ini menambal ClientTransaction.get_indices agar mengenali format baru,
sambil tetap mendukung format lama sebagai fallback. Cukup `import twikit_patch`
sebelum login.
"""

import re

from twikit.x_client_transaction.transaction import (
    ClientTransaction,
    INDICES_REGEX,
    ON_DEMAND_FILE_REGEX,
)

# Mapping <chunkId>:"ondemand.s" pada manifest baru.
_CHUNK_ID_REGEX = re.compile(r'(\d+):"ondemand\.s"')


async def _patched_get_indices(self, home_page_response, session, headers):
    response = self.validate_response(home_page_response) or self.home_page_response
    page_source = str(response)

    on_demand_url = None

    # 1) Format lama: "ondemand.s":"HASH" -> tetap didukung.
    legacy = ON_DEMAND_FILE_REGEX.search(page_source)
    if legacy:
        on_demand_url = (
            "https://abs.twimg.com/responsive-web/client-web/"
            f"ondemand.s.{legacy.group(1)}a.js"
        )
    else:
        # 2) Format baru: cari chunk id untuk "ondemand.s", lalu hash-nya.
        chunk = _CHUNK_ID_REGEX.search(page_source)
        if chunk:
            chunk_id = chunk.group(1)
            values = re.findall(rf'{chunk_id}:"([^"]+)"', page_source)
            hashes = [v for v in values if re.fullmatch(r"[0-9a-f]+", v)]
            if hashes:
                on_demand_url = (
                    "https://abs.twimg.com/responsive-web/client-web/"
                    f"ondemand.s.{hashes[0]}a.js"
                )

    key_byte_indices = []
    if on_demand_url:
        resp = await session.request(method="GET", url=on_demand_url, headers=headers)
        for item in INDICES_REGEX.finditer(str(resp.text)):
            key_byte_indices.append(item.group(2))

    if not key_byte_indices:
        raise Exception("Couldn't get KEY_BYTE indices")

    key_byte_indices = list(map(int, key_byte_indices))
    return key_byte_indices[0], key_byte_indices[1:]


# Terapkan patch.
ClientTransaction.get_indices = _patched_get_indices


# ---------------------------------------------------------------------------
# Patch User.__init__ — twikit 2.3.3 mengakses banyak field 'legacy' secara
# langsung (mis. entities.description.urls, pinned_tweet_ids_str,
# withheld_in_countries) yang sebagian sudah tidak ada di respons X terbaru,
# menyebabkan KeyError saat membungkus data user. Versi ini memakai .get()
# dengan default aman agar tidak crash. Field penting (id, name, screen_name)
# tetap diisi benar.
# ---------------------------------------------------------------------------
import twikit.user as _usermod


def _patched_user_init(self, client, data):
    self._client = client
    legacy = data.get("legacy", {})
    core = data.get("core", {})
    entities = legacy.get("entities", {})

    self.id = data.get("rest_id") or data.get("id")
    self.created_at = legacy.get("created_at") or core.get("created_at")
    self.name = legacy.get("name") or core.get("name")
    self.screen_name = legacy.get("screen_name") or core.get("screen_name")
    self.profile_image_url = legacy.get("profile_image_url_https")
    self.profile_banner_url = legacy.get("profile_banner_url")
    self.url = legacy.get("url")
    self.location = legacy.get("location")
    self.description = legacy.get("description")
    self.description_urls = entities.get("description", {}).get("urls", [])
    self.urls = entities.get("url", {}).get("urls", [])
    self.pinned_tweet_ids = legacy.get("pinned_tweet_ids_str", [])
    self.is_blue_verified = data.get("is_blue_verified", False)
    self.verified = legacy.get("verified", False)
    self.possibly_sensitive = legacy.get("possibly_sensitive", False)
    self.can_dm = legacy.get("can_dm", False)
    self.can_media_tag = legacy.get("can_media_tag", False)
    self.want_retweets = legacy.get("want_retweets", False)
    self.default_profile = legacy.get("default_profile", False)
    self.default_profile_image = legacy.get("default_profile_image", False)
    self.has_custom_timelines = legacy.get("has_custom_timelines", False)
    self.followers_count = legacy.get("followers_count", 0)
    self.fast_followers_count = legacy.get("fast_followers_count", 0)
    self.normal_followers_count = legacy.get("normal_followers_count", 0)
    self.following_count = legacy.get("friends_count", 0)
    self.favourites_count = legacy.get("favourites_count", 0)
    self.listed_count = legacy.get("listed_count", 0)
    self.media_count = legacy.get("media_count", 0)
    self.statuses_count = legacy.get("statuses_count", 0)
    self.is_translator = legacy.get("is_translator", False)
    self.translator_type = legacy.get("translator_type")
    self.withheld_in_countries = legacy.get("withheld_in_countries", [])
    self.protected = legacy.get("protected", False)


_usermod.User.__init__ = _patched_user_init
