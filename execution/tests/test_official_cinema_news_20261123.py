"""Synthetic short paraphrases of schedule facts; no copied article fixtures."""
import datetime as dt
from email.utils import format_datetime
from unittest import mock
import unittest
from urllib.parse import parse_qs, urlsplit
import xml.etree.ElementTree as ET

from execution import official_cinema_news_20261123 as cinema

NOW = dt.datetime(2026, 11, 23, 1, 0, tzinfo=dt.timezone.utc)
PUBLISHED = dt.datetime(2026, 11, 3, 2, 0, tzinfo=dt.timezone.utc)
SOURCE = 'https://cjnews.cj.net/november-cinema/'
# Synthetic paraphrase, under 30 words: film title + factual start/recurrence only.
SCHEDULE = '20일부터 ‘원피스 필름 골드’를 3주간 매주 금·토·일요일 재상영합니다.'
TITLE = 'CGV 11월 영화 안내'


def item(content=SCHEDULE, *, title=TITLE, published=PUBLISHED, source=SOURCE):
    return {'title': title, 'pubDate': format_datetime(published),
            'link': source, cinema.CONTENT: '<p>'+content+'</p>'}


def feed(items):
    root = ET.Element('rss')
    channel = ET.SubElement(root, 'channel')
    for row in items:
        node = ET.SubElement(channel, 'item')
        for name, value in row.items():
            ET.SubElement(node, name).text = value
    return ET.tostring(root, encoding='unicode')


class CinemaNewsTests(unittest.TestCase):
    def run_collect(self, items=None, article=None, feeds=None):
        if items is None:
            items = [item()]
        feeds = feeds or {'원피스': feed(items)}
        article = article if article is not None else '<html><p>'+SCHEDULE+'</p></html>'
        calls = []
        def fetch(url):
            calls.append(url)
            if '/feed/' in url:
                return feeds.get(parse_qs(urlsplit(url).query)['s'][0], feed([]))
            if isinstance(article, Exception):
                raise article
            return article
        rows, errors = cinema.collect(fetch, NOW)
        return rows, errors, calls

    def test_exact_repeat_dates_and_last_show_not_publication_day(self):
        rows, errors, calls = self.run_collect()
        self.assertEqual(1, len(rows))
        row = rows[0]
        self.assertEqual('2026-11-20', row['start_date'])
        self.assertEqual('2026-12-06', row['end_date'])
        self.assertEqual(['2026-11-20', '2026-11-21', '2026-11-22',
                          '2026-11-27', '2026-11-28', '2026-11-29',
                          '2026-12-04', '2026-12-05', '2026-12-06'], row['schedule_dates'])
        self.assertIn('계산', row['schedule_basis'])
        self.assertIn('매일 상영 아님', row['condition'])
        self.assertIn('3주간', row['condition'])
        self.assertEqual(PUBLISHED.isoformat(timespec='seconds'), row['source_published_at'])
        self.assertEqual(3, sum('/feed/' in url for url in calls))
        self.assertEqual(1, sum('/feed/' not in url for url in calls))

    def test_no_reward_deadline_is_manufactured(self):
        row = self.run_collect()[0][0]
        self.assertIsNone(row['claim_deadline'])
        self.assertEqual('카드 특전 확인 안 됨', row['reward'])
        self.assertEqual('official', row['source_grade'])
        self.assertEqual('theatrical_film', row['media_type'])
        self.assertEqual('KR', row['region'])
        self.assertEqual('정상', row['link_status'])
        self.assertEqual(NOW.isoformat(timespec='seconds'), row['content_checked_at'])
        self.assertEqual(row['link_checked_at'], row['content_checked_at'])
        self.assertEqual(row['source'], row['collection_source'])
        self.assertIn('/feed/', row['discovery_source'])
        self.assertEqual(row['content_checked_at'], row['discovered_at'])

    def test_single_opening_uses_explicit_internal_review_date(self):
        sentence = '11월 20일에 ‘원피스 필름 골드’가 개봉합니다.'
        rows, _, _ = self.run_collect([item(sentence)], '<p>'+sentence+'</p>')
        row = rows[0]
        self.assertEqual('start-only', row['date_precision'])
        self.assertTrue(row['tracking_only'])
        self.assertEqual('2027-02-18', row['internal_review_until'])
        self.assertEqual(row['end_date'], row['internal_review_until'])
        self.assertIn('종료일 미발표', row['date_label'])
        self.assertIn('상영 종료일이 아님', row['condition'])

    def test_missing_actual_film_title_is_not_a_confirmed_movie(self):
        rows, errors, calls = self.run_collect([item('20일에 ‘원피스’를 재상영합니다.')])
        self.assertEqual([], rows)
        self.assertTrue(any('NO_CONFIRMED' in e for e in errors))
        self.assertEqual(3, len(calls))

    def test_publication_date_does_not_become_event_start(self):
        rows, _, calls = self.run_collect([item('‘원피스 필름 골드’를 재상영합니다.')])
        self.assertEqual([], rows)
        self.assertEqual(3, len(calls))

    def test_cancelled_or_unconfirmed_release_is_not_a_schedule(self):
        for suffix in ('개봉이 취소되었습니다.', '상영하지 않습니다.', '개봉을 검토합니다.', '개봉일은 미정입니다.'):
            sentence = '11월 20일에 ‘원피스 필름 골드’의 '+suffix
            with self.subTest(suffix=suffix):
                rows, errors, _ = self.run_collect([item(sentence)], '<p>'+sentence+'</p>')
                self.assertEqual([], rows)
                self.assertTrue(any('NO_CONFIRMED' in e for e in errors))

    def test_news_search_and_faq_mentions_do_not_publish(self):
        for content in ('‘원피스 필름 골드’ 관련기사 모음입니다.',
                        'A. 20일부터 ‘원피스 필름 골드’를 재상영합니다.',
                        'Q: 20일부터 ‘원피스 필름 골드’를 재상영하나요?'):
            with self.subTest(content=content):
                self.assertEqual([], self.run_collect([item(content)])[0])

    def test_unconfirmed_article_does_not_pass_link_success(self):
        rows, errors, _ = self.run_collect(article='<p>CGV 기사 목록입니다.</p>')
        self.assertEqual([], rows)
        self.assertTrue(any('CONTENT_MISMATCH' in e for e in errors))

    def test_different_article_schedule_is_rejected(self):
        wrong = '<p>'+SCHEDULE.replace('20일', '27일')+'</p>'
        rows, errors, _ = self.run_collect(article=wrong)
        self.assertEqual([], rows)
        self.assertTrue(any('CONTENT_MISMATCH' in e for e in errors))

    def test_article_failure_is_explicit_and_never_link_verified(self):
        rows, errors, _ = self.run_collect(article=OSError('private error details'))
        self.assertEqual([], rows)
        self.assertTrue(any('ARTICLE 원피스: OSError' in e for e in errors))
        self.assertFalse(any('private error' in e for e in errors))
        from urllib.error import URLError
        rows, errors, _ = self.run_collect(article=URLError('dns lookup failed https://user:secret@example.test/'))
        self.assertEqual([], rows)
        self.assertTrue(any('URLError: dns lookup failed' in e for e in errors))
        self.assertFalse(any('secret' in e or 'example.test' in e for e in errors))

    def test_exact_host_no_auth_no_unsafe_scheme_and_no_redirector(self):
        for source in ('https://cjnews.cj.net.evil.test/article/',
                       'http://cjnews.cj.net/article/', 'https://evil.test/cjnews.cj.net/',
                       'https://user@cjnews.cj.net/article/', 'https://cjnews.cj.net:444/a/',
                       'https://cjnews.cj.net:bad/a/', 'https://cjnews.cj.net/feed/',
                       'https://cjnews.cj.net/\\evil.test/', 'https://cjnews.cj.net/a/\n'):
            with self.subTest(source=source):
                rows, errors, calls = self.run_collect([item(source=source)])
                self.assertEqual([], rows)
                self.assertEqual(3, len(calls))
                self.assertTrue(any('ARTICLE' in e for e in errors))

    def test_utm_is_removed_and_duplicates_are_checked_once(self):
        entries = [item(source=SOURCE+'?utm_source=rss&utm_medium=rss'), item(source=SOURCE+'#top')]
        rows, _, calls = self.run_collect(entries)
        self.assertEqual([SOURCE], [r['source'] for r in rows])
        self.assertEqual(1, calls.count(SOURCE))

    def test_same_article_can_have_a_distinct_game_without_cross_assignment(self):
        pokemon = '20일부터 ‘극장판 포켓몬스터 합성 테스트’를 3주간 매주 금·토·일요일 재상영합니다.'
        feeds = {'원피스': feed([item()]), '포켓몬': feed([item(pokemon)])}
        rows, _, _ = self.run_collect(feeds=feeds, article='<p>'+SCHEDULE+'</p><p>'+pokemon+'</p>')
        self.assertEqual({'원피스 카드', '포켓몬 카드'}, {r['game'] for r in rows})
        self.assertEqual(2, len(rows))

    def test_future_and_stale_announcements_are_rejected_without_article_fetch(self):
        for published in (NOW+dt.timedelta(seconds=1), NOW-dt.timedelta(days=90, seconds=1)):
            with self.subTest(published=published):
                rows, _, calls = self.run_collect([item(published=published)])
                self.assertEqual([], rows)
                self.assertEqual(3, len(calls))

    def test_ambiguous_or_invalid_date_is_a_gap(self):
        for content, title in ((SCHEDULE, 'CGV 영화 안내'),
                               (SCHEDULE, 'CGV 11월 12월 영화 안내'),
                               (SCHEDULE.replace('20일', '31일'), TITLE),
                               ('11월 20일부터 12월 1일까지 ‘원피스 필름 골드’를 재상영합니다.', TITLE)):
            with self.subTest(content=content, title=title):
                self.assertEqual([], self.run_collect([item(content, title=title)])[0])

    def test_recurrence_is_not_inferred_from_incomplete_or_conflicting_text(self):
        for content in (SCHEDULE.replace('3주간 ', ''), SCHEDULE.replace('매주 금·토·일요일 ', ''),
                        SCHEDULE.replace('20일', '19일'), SCHEDULE.replace('3주간', '9주간')):
            with self.subTest(content=content):
                self.assertEqual([], self.run_collect([item(content)])[0])

    def test_paragraphs_do_not_borrow_another_films_date(self):
        row = item('‘원피스 필름 골드’를 재상영합니다.')
        row[cinema.CONTENT] += '<p>20일부터 다른 영화를 상영합니다.</p>'
        self.assertEqual([], self.run_collect([row])[0])

    def test_scripts_related_cards_and_hidden_paragraphs_are_ignored(self):
        for wrapped in ('<script><p>'+SCHEDULE+'</p></script>',
                        '<aside><p>'+SCHEDULE+'</p></aside>',
                        '<div class="related-news"><p>'+SCHEDULE+'</p></div>',
                        '<div hidden><p>'+SCHEDULE+'</p></div>',
                        '<section id="faq"><p>'+SCHEDULE+'</p></section>'):
            row = item()
            row[cinema.CONTENT] = wrapped
            with self.subTest(wrapped=wrapped):
                self.assertEqual([], self.run_collect([row], wrapped)[0])

    def test_dtd_entities_and_malformed_xml_are_rejected(self):
        for raw in ('<!DOCTYPE rss><rss><channel/></rss>',
                    '<!DOCTYPE rss [<!ENTITY x "x">]><rss/>', '<rss><channel>'):
            rows, errors, calls = self.run_collect(feeds={'원피스': raw})
            self.assertEqual([], rows)
            self.assertTrue(any('FEED 원피스' in e for e in errors))
            self.assertEqual(3, len(calls))

    def test_oversize_or_wrong_type_feed_has_explicit_error(self):
        for raw in ('x'*(cinema.MAX_BYTES+1), None, 42):
            rows, errors, _ = self.run_collect(feeds={'원피스': raw})
            self.assertEqual([], rows)
            self.assertTrue(any('FEED 원피스' in e for e in errors))

    def test_oversize_article_has_no_success_row(self):
        rows, errors, _ = self.run_collect(article='x'*(cinema.MAX_BYTES+1))
        self.assertEqual([], rows)
        self.assertTrue(any('ARTICLE 원피스' in e for e in errors))

    def test_first_thirty_items_only_and_reports_truncation(self):
        entries = [item('관계 없는 소식', source=SOURCE+str(i)) for i in range(30)]+[item()]
        rows, errors, calls = self.run_collect(entries)
        self.assertEqual([], rows)
        self.assertTrue(any('ITEM_LIMIT' in e for e in errors))
        self.assertEqual(3, len(calls))

    def test_four_article_attempts_total_across_games_including_failures(self):
        entries = [item(source=SOURCE+str(i)) for i in range(6)]
        feeds = {'원피스': feed(entries), '포켓몬': feed([item('20일에 ‘포켓몬스터 합성 테스트’가 개봉합니다.')])}
        rows, errors, calls = self.run_collect(feeds=feeds, article=OSError('offline'))
        self.assertEqual([], rows)
        self.assertEqual(4, sum('/feed/' not in u for u in calls))
        self.assertTrue(any('ARTICLE_LIMIT' in e for e in errors))

    def test_budget_exhaustion_stops_new_requests_and_reports_missing_games(self):
        calls = []
        with mock.patch.object(cinema.time, 'monotonic', side_effect=[0, 0, 61, 61, 61]):
            rows, errors = cinema.collect(lambda u: calls.append(u) or feed([item()]), NOW)
        self.assertEqual([], rows)
        self.assertEqual(1, len(calls))
        self.assertEqual(3, sum('BUDGET_EXHAUSTED' in e for e in errors))

    def test_normal_html_doctype_can_confirm_but_foreign_operator_cannot(self):
        rows, _, _ = self.run_collect(article='<!DOCTYPE html><html><p>'+SCHEDULE+'</p></html>')
        self.assertEqual(1, len(rows))
        rows, errors, _ = self.run_collect([item(title='11월 영화 안내')])
        self.assertEqual([], rows)
        self.assertTrue(any('ARTICLE' in e for e in errors))

    def test_existing_event_schema_accepts_verified_repeat_and_start_only_rows(self):
        from update_promo_events import valid
        repeat = self.run_collect()[0][0]
        single = '11월 20일에 ‘원피스 필름 골드’가 개봉합니다.'
        start_only = self.run_collect([item(single)], '<p>'+single+'</p>')[0][0]
        self.assertTrue(valid(repeat))
        self.assertTrue(valid(start_only))


if __name__ == '__main__':
    unittest.main()
