"""Validate social-platform captures before they enter factual cross-checking."""
import hashlib
from datetime import datetime, timezone
from urllib.parse import urlsplit


PLATFORMS = {
    "x": {"hosts": {"x.com"}, "max_age": 86400},
    "instagram": {"hosts": {"www.instagram.com", "instagram.com"}, "max_age": 86400},
    "youtube": {"hosts": {"www.youtube.com", "youtube.com", "youtu.be"}, "max_age": 86400},
    "reddit": {"hosts": {"www.reddit.com", "reddit.com"}, "max_age": 86400},
}


def _stamp(value):
    if not isinstance(value, str):
        raise ValueError("TIMESTAMP_REQUIRED")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("TIMEZONE_REQUIRED")
    return parsed.timestamp()


class SocialEvidenceGate:
    """Makes social posts supporting evidence, never stand-alone verification."""

    def assess(self, capture, *, now=None):
        if not isinstance(capture, dict):
            raise ValueError("CAPTURE_REQUIRED")
        platform = capture.get("platform")
        policy = PLATFORMS.get(platform)
        if not policy:
            raise ValueError("UNSUPPORTED_PLATFORM")
        for key in ("post_id", "author_id", "handle", "url", "created_at", "fetched_at",
                    "capture_reference", "account_reference", "text"):
            if not isinstance(capture.get(key), str) or not capture[key]:
                raise ValueError("INCOMPLETE_SOCIAL_CAPTURE")
        url = urlsplit(capture["url"])
        if url.scheme != "https" or url.hostname not in policy["hosts"] or url.username or url.password:
            raise ValueError("SOCIAL_URL_MISMATCH")
        current = _stamp(now) if now else datetime.now(timezone.utc).timestamp()
        created, fetched = _stamp(capture["created_at"]), _stamp(capture["fetched_at"])
        if created > fetched or fetched > current or current - fetched > policy["max_age"]:
            raise ValueError("STALE_OR_FUTURE_SOCIAL_CAPTURE")
        if capture.get("api_capture_verified") is not True:
            raise ValueError("API_CAPTURE_PROOF_REQUIRED")
        if capture.get("official_account_verified") is not True:
            return {"status": "DISCOVERY_ONLY", "eligible_for_crosscheck": False,
                    "can_verify_alone": False, "reason": "OFFICIAL_ACCOUNT_NOT_VERIFIED"}
        fingerprint = hashlib.sha256((platform + "\0" + capture["post_id"] + "\0" +
                                      capture["author_id"] + "\0" + capture["text"]).encode()).hexdigest()
        return {"status": "SUPPORTING_EVIDENCE", "eligible_for_crosscheck": True,
                "can_verify_alone": False, "origin_key": platform + ":" + capture["post_id"],
                "fingerprint": fingerprint, "account_reference": capture["account_reference"],
                "capture_reference": capture["capture_reference"]}

