import json
import subprocess
import unittest
from pathlib import Path


class ManualSummaryCounterBoundaryV247Tests(unittest.TestCase):
    def _run_summary(self, official_count="1", reference_count="5", photo_count="7"):
        source = Path("manual_official_verify_bridge.js").read_text(encoding="utf-8")
        start = source.index("function countFromCard(")
        end = source.index("function installSummaryObserver(")
        functions = source[start:end]

        script = functions + f'''
const card=(label,count)=>({{
 label:{{textContent:label}}, value:{{textContent:String(count)}}, removed:false,
 querySelector(s){{return s==='span'?this.label:(s==='b'?this.value:null)}},
 remove(){{this.removed=true}}
}});
const official=card('공식검증·학습반영',{json.dumps(official_count)});
const reference=card('참고학습 반영',{json.dumps(reference_count)});
const photos=card('실제 사진',{json.dumps(photo_count)});
const cert=card('인증번호 확보','3');
const summary={{children:[official,reference,photos,cert]}};
const footer={{textContent:''}};
global.document={{querySelector(s){{
 if(s.includes('.gpd-summary')) return summary;
 if(s.includes('.gpd-foot .gpd-safe')) return footer;
 return null;
}}}};
mergeVerifiedLearningSummary();
mergeVerifiedLearningSummary();
console.log(JSON.stringify({{
 official: official.value.textContent,
 reference: reference.value.textContent,
 photos: photos.value.textContent,
 referenceRemoved: reference.removed,
 photoRemoved: photos.removed,
 officialLabel: official.label.textContent,
 footer: footer.textContent
}}));
'''
        output = subprocess.check_output(["node", "-e", script], text=True)
        return json.loads(output)

    def test_official_reference_and_photo_counts_remain_independent(self):
        result = self._run_summary("1", "5", "7")
        self.assertEqual(result["official"], "1")
        self.assertEqual(result["reference"], "5")
        self.assertEqual(result["photos"], "7")
        self.assertFalse(result["referenceRemoved"])
        self.assertFalse(result["photoRemoved"])
        self.assertEqual(result["officialLabel"], "공식검증")
        self.assertIn("별도 집계", result["footer"])

    def test_reference_count_never_promotes_official_count(self):
        result = self._run_summary("0", "999", "2")
        self.assertEqual(result["official"], "0")
        self.assertEqual(result["reference"], "999")
        self.assertEqual(result["photos"], "2")

    def test_summary_code_has_no_legacy_max_merge_or_pair_inference(self):
        source = Path("manual_official_verify_bridge.js").read_text(encoding="utf-8")
        start = source.index("function mergeVerifiedLearningSummary(")
        end = source.index("function installSummaryObserver(")
        body = source[start:end]
        self.assertNotIn("Math.max", body)
        self.assertNotIn("reference.remove", body)
        self.assertNotIn("*2", body.replace(" ", ""))


if __name__ == "__main__":
    unittest.main()
