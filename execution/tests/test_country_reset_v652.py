"""Country button selection follows programmatic reset without a second render."""
from pathlib import Path
import shutil
import subprocess
import unittest
ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(shutil.which('node'),'Node required')
class CountryResetTests(unittest.TestCase):
    def test_reset_highlight_after_other_handlers_set_all(self):
        text=(ROOT/'feature_category_nav.js').read_text()
        fn=text[text.index('  function installCountryButtons('):text.index('  ["analysisCountry","tradeCountry","releaseFilter","promoFilter"]')]
        script="""
const assert=require('node:assert/strict');const tasks=[];const queueMicrotask=fn=>tasks.push(fn);
class Node{constructor(){this.dataset={};this.attrs={};this.listeners={};this.children=[]}setAttribute(k,v){this.attrs[k]=v}addEventListener(k,fn){this.listeners[k]=fn}append(x){this.children.push(x)}}
const select=new Node(),reset=new Node();select.value='CN';select.parentElement={};select.options=['ALL','KR','JP','US','CN'].map(value=>({value}));select.getAttribute=()=>null;
let bar,changes=0;select.insertAdjacentElement=(_,node)=>bar=node;select.dispatchEvent=()=>changes++;
const document={getElementById:id=>({analysisCountry:select,analysisClearBtn:reset}[id]||null),createElement:()=>new Node()};
"""+fn+"""
assert.equal(installCountryButtons('analysisCountry'),true);
const cn=bar.children.find(x=>x.dataset.country==='CN'),all=bar.children.find(x=>x.dataset.country==='ALL');
assert.equal(cn.attrs['aria-pressed'],'true');
reset.listeners.click();select.value='ALL';tasks.splice(0).forEach(fn=>fn());
assert.equal(cn.attrs['aria-pressed'],'false');assert.equal(all.attrs['aria-pressed'],'true');assert.equal(changes,0);
"""
        run=subprocess.run(['node','-e',script],capture_output=True,text=True,timeout=10)
        self.assertEqual(0,run.returncode,run.stdout+run.stderr)
