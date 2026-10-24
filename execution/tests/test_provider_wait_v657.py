"""Long and HTTP-date provider waits persist; fixture failures never hit network."""
import datetime as dt
from email.message import Message
from email.utils import format_datetime
import unittest
from unittest.mock import patch
import urllib.error
from execution import official_social_discovery as d


class ProviderWaitTests(unittest.TestCase):
    now=2_000_000_000
    account={'username':'pokemon','platform':'instagram','game':'포켓몬 카드','region':'KR',
             'profile_url':'https://www.instagram.com/pokemon/'}

    def blocked(self,code,retry):
        headers=Message();headers['Retry-After']=retry
        failure=urllib.error.HTTPError('https://news.google.com/rss/search',code,'limited',headers,None)
        with patch.object(d,'safe_urlopen',side_effect=failure) as request:
            rows,errors,status=d._provider('google',[self.account],{},None,self.now)
        self.assertEqual(request.call_count,1);self.assertFalse(rows);self.assertTrue(errors)
        return status

    def test_two_day_wait_is_preserved_after_restart(self):
        status=self.blocked(429,'172800')
        self.assertEqual(status['blocked_until'],self.now+172800)
        with patch.object(d,'safe_urlopen',side_effect=AssertionError('premature request')):
            for offset in (1,86401,172799):
                rows,errors,current=d._provider('google',[self.account],{},status,self.now+offset)
                self.assertEqual(current['state'],'COOLDOWN')
                self.assertEqual(current['attempted'],0)
                self.assertEqual(current['blocked_until'],status['blocked_until'])

    def test_http_date_retry_after_is_honored(self):
        future=dt.datetime.fromtimestamp(self.now+3*86400,dt.timezone.utc)
        status=self.blocked(429,format_datetime(future,usegmt=True))
        self.assertEqual(status['blocked_until'],self.now+3*86400)

    def test_short_or_bad_header_does_not_reduce_default_cooldown(self):
        for code,minimum in ((403,86400),(429,21600)):
            for value in ('1','-10','garbage','inf','9'*129):
                with self.subTest(code=code,value=value):
                    self.assertEqual(self.blocked(code,value)['blocked_until'],self.now+minimum)

    def test_expired_cooldown_can_collect_next_slot(self):
        status=self.blocked(429,'172800')
        with patch.object(d,'safe_urlopen',side_effect=ValueError('fixture')) as request:
            d._provider('google',[self.account],{},status,self.now+172801)
        request.assert_called_once()

    def test_invalid_persisted_timestamps_do_not_crash(self):
        for value in (True,None,float('nan'),float('inf'),-1):
            with patch.object(d,'safe_urlopen',side_effect=ValueError('fixture')) as request:
                d._provider('google',[self.account],{}, {'blocked_until':value},self.now)
            request.assert_called_once()


if __name__=='__main__':unittest.main()
