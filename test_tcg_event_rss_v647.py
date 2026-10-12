#!/usr/bin/env python3
"""V647 offline RSS/Atom user-provided event source import reliability."""
import csv
from datetime import date
import io
import unittest

import tcg_event_rss_v647 as rss
import tcg_event_intelligence_v644 as ledger

NOW=date(2026,10,12)


class EventFeedV647(unittest.TestCase):
    def test_rss_duplicate_articles_and_movie_gift_promo_categorization(self):
        raw=b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel>
<item><title>30thプロモカードパック配布イベント</title>
<link>https://www.30th.pokemon-card.com/event/30thgym</link></item>
<item><title>30thプロモカードパック配布イベント</title>
<link>https://www.30th.pokemon-card.com/event/30thgym?utm_source=feed</link></item>
<item><title>映画コラボ プレゼント</title>
<link>https://www.30th.pokemon-card.com/event</link></item>
<item><title>Today's unrelated technology briefing</title>
<link>https://example.com/unrelated</link></item>
</channel></rss>"""
        result=rss.ingest([raw],game_id="pokemon",region="JP",observed_at=NOW)
        self.assertEqual(4,result["feed_items_read"])
        self.assertEqual(1,result["skipped_items"])
        self.assertEqual(0,sum(x["start_date"]!="" for x in result["sightings"]))
        self.assertIn("PROMO",{x["category"] for x in result["sightings"]})
        self.assertIn("MOVIE",{x["category"] for x in result["sightings"]})
        self.assertIn("COLLAB",{x["category"] for x in result["sightings"]})
        self.assertTrue(any(x["source_type"]=="manufacturer" for x in result["sightings"]))
        self.assertEqual(1,sum(x["category"]=="PROMO" for x in result["sightings"]))

    def test_atom_with_external_https_link(self):
        body=b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>TCG movie giveaway</title><link rel="alternate"
href="https://example.com/event?id=14"/></entry></feed>"""
        entries=rss.parse_feed(body)
        self.assertEqual(1,len(entries))
        result=rss.ingest([body],game_id="pokemon",region="US",observed_at=NOW)
        self.assertIn("MOVIE",{x["category"] for x in result["sightings"]})
        self.assertIn("GIVEAWAY",{x["category"] for x in result["sightings"]})
        self.assertTrue(all(x["source_type"]=="news" for x in result["sightings"]))

    def test_feed_dtd_xxe_block_and_private_links_rejected(self):
        with self.assertRaisesRegex(ValueError,"DTD_DISABLED"):
            rss.parse_feed(b'<!DOCTYPE rss [ <!ENTITY xxe SYSTEM "file:///etc/passwd"> ]><rss/>')
        with self.assertRaises(ValueError):
            rss.parse_feed(b'<p>not a feed</p>')
        with self.assertRaises(ValueError):
            rss.parse_feed(b"x"*(rss.MAX_FEED_BYTES+1))
        body=b'<rss><channel><item><title>movie giveaway</title><link>http://127.0.0.1/x</link></item></channel></rss>'
        self.assertEqual([],rss.parse_feed(body))

    def test_rss_to_csv_to_ledger_keeps_start_date_unknown(self):
        xml=b'<rss><channel><item><title>promo card giveaway</title><link>https://example.com/a</link></item></channel></rss>'
        result=rss.ingest([xml],game_id="pokemon",region="US",observed_at=NOW)
        output=rss.csv_out(result["sightings"])
        staged=ledger.load_rows_csv(output)
        self.assertEqual(len(result["sightings"]),len(staged))
        grouped=ledger.group_records(staged,today=NOW)
        self.assertEqual(len(staged),grouped["unique_events"])
        self.assertTrue(all(e["start_date"] is None for e in grouped["events"]))
        self.assertTrue(all(not e["confirmed"] for e in grouped["events"]))

    def test_game_scope_validation_and_keyword_filtering(self):
        self.assertEqual([],rss.classify("unrelated news about GPU","KR"))
        self.assertIn(("PROMO","프로모 카드"),rss.classify("한정 프로모 카드 배포","KR"))
        with self.assertRaises(ValueError):
            rss.ingest([],game_id="unknown",region="JP")
        with self.assertRaises(ValueError):
            rss.ingest([],game_id="pokemon",region="CN")


if __name__=="__main__":
    unittest.main(verbosity=2)
