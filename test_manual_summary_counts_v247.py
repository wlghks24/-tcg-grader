import json
import subprocess
import unittest
from pathlib import Path


class ManualSummaryCountsV247Tests(unittest.TestCase):
    @staticmethod
    def _summary_functions() -> str:
        source = Path("manual_official_verify_bridge.js").read_text(encoding="utf-8")
        start = source.index("function countFromCard(")
        end = source.index("function installSummaryObserver(")
        return source[start:end]

    def test_official_reference_and_existing_photo_counts_remain_independent(self):
        functions = self._summary_functions()
        script = functions + r'''
const card=(label,value)=>({
 label:{textContent:label}, value:{textContent:value}, removed:false,
 querySelector(selector){return selector==='span'?this.label:selector==='b'?this.value:null},
 remove(){this.removed=true}
});
const official=card('공식검증','1건');
const reference=card('참고학습 반영','5건');
const photos=card('사진 검증','7건');
const cert=card('인증번호 확보','3개');
const summary={children:[official,reference,photos,cert]};
const footer={textContent:'기존 문구'};
global.document={querySelector(selector){
 if(selector==='#gpdBody .gpd-summary')return summary;
 if(selector==='#gpdBody .gpd-foot .gpd-safe')return footer;
 return null;
}};
const first=mergeVerifiedLearningSummary();
const second=mergeVerifiedLearningSummary();
console.log(JSON.stringify({
 first,second,
 officialLabel:official.label.textContent,
 officialValue:official.value.textContent,
 referenceValue:reference.value.textContent,
 referenceRemoved:reference.removed,
 photoValue:photos.value.textContent,
 certValue:cert.value.textContent,
 footer:footer.textContent
}));
'''
        output = subprocess.check_output(["node", "-e", script], text=True)
        result = json.loads(output)
        self.assertTrue(result["first"])
        self.assertTrue(result["second"])
        self.assertEqual(result["officialLabel"], "공식검증")
        self.assertEqual(result["officialValue"], "1건")
        self.assertEqual(result["referenceValue"], "5건")
        self.assertFalse(result["referenceRemoved"])
        self.assertEqual(result["photoValue"], "7건")
        self.assertEqual(result["certValue"], "3개")
        self.assertEqual(
            result["footer"],
            "공식검증과 참고학습은 별도 집계 · 사진 첨부 및 학습 가능 여부는 개별 검증 결과로 확인",
        )

    def test_summary_bridge_does_not_synthesize_photo_or_merged_counts(self):
        source = Path("manual_official_verify_bridge.js").read_text(encoding="utf-8")
        functions = self._summary_functions()
        self.assertNotIn("Math.max(countFromCard(official),countFromCard(reference))", functions)
        self.assertNotIn("merged*2", functions)
        self.assertNotIn("reference.remove()", functions)
        self.assertNotIn("공식검증·학습반영", functions)
        self.assertIn("공식검증과 참고학습은 별도 집계", source)


if __name__ == "__main__":
    unittest.main()
