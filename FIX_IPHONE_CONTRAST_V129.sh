#!/data/data/com.termux/files/usr/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

python - <<'PY'
from pathlib import Path
import re

path = Path('index.html')
if not path.exists():
    raise SystemExit('index.html not found')

text = path.read_text(encoding='utf-8')
backup = Path('index.html.before_iphone_v129')
if not backup.exists():
    backup.write_text(text, encoding='utf-8')

style = r'''
<style id="tcg-readability-inline-v129">
/* Inline repair for iPhone/Chrome/Safari opened through the tablet HTTP server.
   Do not depend on an external CSS file or service worker. */
.simple-grade-card,.validation-hub,.workflow-card,.precision-hub,.economics-card,
.grading-total-panel,.multi-market-panel,.auto-validation-panel,.graded-photo-dashboard,
.update-panel,.workflow-part,.precision-step,.precision-tool,.compact-details,
.validation-stats .metric,.economics-result,.v13-result-card,.capture-tile{
  color-scheme:light!important;
}

.simple-grade-title,
.simple-grade-card h1,.simple-grade-card h2,.simple-grade-card h3,.simple-grade-card h4,
.validation-hub h1,.validation-hub h2,.validation-hub h3,.validation-hub h4,
.workflow-card h1,.workflow-card h2,.workflow-card h3,.workflow-card h4,
.precision-hub h1,.precision-hub h2,.precision-hub h3,.precision-hub h4,
.economics-card h1,.economics-card h2,.economics-card h3,.economics-card h4,
.grading-total-panel h1,.grading-total-panel h2,.grading-total-panel h3,.grading-total-panel h4,
.multi-market-panel h1,.multi-market-panel h2,.multi-market-panel h3,.multi-market-panel h4,
.auto-validation-panel h1,.auto-validation-panel h2,.auto-validation-panel h3,.auto-validation-panel h4,
.graded-photo-dashboard h1,.graded-photo-dashboard h2,.graded-photo-dashboard h3,.graded-photo-dashboard h4,
.update-panel h1,.update-panel h2,.update-panel h3,.update-panel h4,
.workflow-part h3,.precision-step-title,.precision-tool h4,.capture-label,
.validation-stats .metric b,.economics-result b,.v13-result-title,
#v30validation h2,#v30validation h3,#v30validation h4,
#v30calibration h2,#v30calibration h3,#v30calibration h4{
  color:#0f172a!important;
  -webkit-text-fill-color:#0f172a!important;
  opacity:1!important;
  text-shadow:none!important;
  mix-blend-mode:normal!important;
  filter:none!important;
}

.simple-grade-sub,.simple-grade-card .simple-note,.simple-grade-card .muted,
.validation-hub p,.validation-hub label,.validation-hub legend,.validation-hub .muted,
.workflow-card p,.workflow-card label,.workflow-card legend,.workflow-card .muted,
.precision-hub p,.precision-hub label,.precision-hub legend,.precision-hub .muted,
.economics-card p,.economics-card label,.economics-card legend,.economics-card .muted,
.grading-total-panel p,.grading-total-panel label,.grading-total-panel .muted,
.multi-market-panel p,.multi-market-panel label,.multi-market-panel .muted,
.auto-validation-panel p,.auto-validation-panel label,.auto-validation-panel .muted,
.graded-photo-dashboard p,.graded-photo-dashboard label,.graded-photo-dashboard .muted,
.update-panel p,.update-panel label,.update-panel .muted,.update-step-note,
.capture-tile .muted,.guide-note,.analysis-native,.analysis-sub,.v13-result-native,
.validation-stats .metric,#v30validation label,#v30validation p,#v30validation .muted,
#v30calibration label,#v30calibration p,#v30calibration .muted{
  color:#475569!important;
  -webkit-text-fill-color:#475569!important;
  opacity:1!important;
  text-shadow:none!important;
  mix-blend-mode:normal!important;
  filter:none!important;
}

.validation-hub .workflow-part,.validation-hub .compact-details,
.validation-stats .metric,.workflow-card .workflow-part,
.precision-hub .precision-step,.precision-hub .precision-tool,
.capture-tile,.economics-result,.v13-result-card{
  background:#fff!important;
  border-color:#cbd5e1!important;
}

.validation-hub input,.validation-hub select,.validation-hub textarea,
.workflow-card input,.workflow-card select,.workflow-card textarea,
.precision-hub input,.precision-hub select,.precision-hub textarea,
.economics-card input,.economics-card select,.economics-card textarea,
.grading-total-panel input,.grading-total-panel select,.grading-total-panel textarea,
.simple-grade-card input,.simple-grade-card select,.simple-grade-card textarea,
#v30validation input,#v30validation select,#v30validation textarea{
  background:#fff!important;
  color:#0f172a!important;
  -webkit-text-fill-color:#0f172a!important;
  border-color:#64748b!important;
  opacity:1!important;
}

.validation-hub input::placeholder,.validation-hub textarea::placeholder,
.workflow-card input::placeholder,.workflow-card textarea::placeholder,
.precision-hub input::placeholder,.precision-hub textarea::placeholder,
.economics-card input::placeholder,.economics-card textarea::placeholder,
.simple-grade-card input::placeholder,.simple-grade-card textarea::placeholder,
#v30validation input::placeholder,#v30validation textarea::placeholder{
  color:#64748b!important;
  -webkit-text-fill-color:#64748b!important;
  opacity:1!important;
}

/* Keep intentional dark action/status blocks readable. */
.simple-grade-card button,.validation-hub button,.workflow-card button,
.precision-hub button,.economics-card button,.grading-total-panel button,
.update-panel button,.camera-status,.gpd-company{
  -webkit-text-fill-color:currentColor!important;
}
.simple-grade-card button:not(.simple-game),.validation-hub button,.workflow-card button,
.precision-hub button,.economics-card button,.grading-total-panel button,.update-panel button{
  color:#fff!important;
}
.simple-game,.simple-game .game-label{
  color:#0f172a!important;
  -webkit-text-fill-color:#0f172a!important;
}

/* The dark status rows in the validation center stay dark with light text. */
#validationSummary,#learningSyncStatus,#calibrationStatus,#qualityStatus,#v11statsOut,#v11rules{
  -webkit-text-fill-color:currentColor!important;
}

@media(max-width:650px){
  .validation-hub .grid2,.validation-actions,.validation-stats{
    grid-template-columns:1fr!important;
    min-width:0!important;
  }
  .validation-hub input,.validation-hub select,.simple-grade-card input,.simple-grade-card select{
    max-width:100%!important;
    min-width:0!important;
  }
}
</style>
'''.strip()

text = re.sub(r'\n?<style id="tcg-readability-inline-v129">.*?</style>\n?', '\n', text, flags=re.S)
if '</head>' not in text:
    raise SystemExit('index.html has no </head>')
text = text.replace('</head>', style + '\n</head>', 1)
path.write_text(text, encoding='utf-8')
print('OK: injected tcg-readability-inline-v129 into index.html')
PY

if grep -q 'tcg-readability-inline-v129' index.html; then
  echo 'OK: local index contains v129 contrast patch'
else
  echo 'ERROR: v129 marker missing' >&2
  exit 1
fi

if curl -fsS 'http://127.0.0.1:8765/index.html?v=129' | grep -q 'tcg-readability-inline-v129'; then
  echo 'OK: running server is serving v129 contrast patch'
else
  echo 'WARN: server response does not show v129 yet. Restart the tablet server once.' >&2
fi
