"""Do not present frozen legacy dashboard claims as current device evidence."""
from html.parser import HTMLParser

STATUS_BODY = '''
<details class="compact-details system-check"><summary>검사 결과 · 확인이 필요한 항목</summary>
<p class="muted" role="status">현재 기기의 검사 결과를 이 화면에서 확인하지 못했습니다. 코드 검사 통과와 실제 수집·연결 상태는 별도로 확인해야 합니다.</p>
<div class="grid2">
<div class="metric">전체 자동검사<b>현재 기기 결과 미확인</b></div>
<div class="metric">구매처 링크<b>접속 결과 미확인</b></div>
<div class="metric">행사 자료<b>출처별 확인 시각 점검 필요</b></div>
<div class="metric">서버 API<b>응답 상태 미확인</b></div>
<div class="metric">자동 동기화<b>실행 상태 미확인</b></div>
<div class="metric">보안 검사<b>현재 검사 결과 미확인</b></div>
</div>
<a href="/index.html?feature=code-audit" data-tcg903-link>현재 기기 검사 열기</a>
<p class="muted">확인하지 못한 결과를 성공으로 표시하지 않습니다. 개별 기능의 검사 결과와 자료 출처를 확인하세요.</p>
</details>
'''


class StatusSection(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=False)
        self.lines = [0] + [i + 1 for i, c in enumerate(source) if c == '\n']
        self.depth = self.matches = 0
        self.start = self.span = None
        self.feed(source)
        self.close()

    def markup_offset(self):
        line, col = self.getpos()
        return self.lines[line - 1] + col

    def handle_starttag(self, tag, attrs):
        if tag != 'section':
            return
        if dict(attrs).get('id') == 'v31testdashboard':
            self.matches += 1
            if self.matches != 1:
                raise ValueError('duplicate status section')
            self.start = self.markup_offset() + len(self.get_starttag_text())
            self.depth = 1
        elif self.depth:
            self.depth += 1

    def handle_endtag(self, tag):
        if tag == 'section' and self.depth:
            self.depth -= 1
            if not self.depth:
                self.span = self.start, self.markup_offset()


def replace_legacy_status(document):
    parser = StatusSection(document)
    if parser.depth:
        raise ValueError('unclosed status section')
    if parser.span is None:
        return document
    start, end = parser.span
    return document[:start] + STATUS_BODY + document[end:]
