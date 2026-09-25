from pathlib import Path

replacements={
    'test_card_core_crosscheck_v292.py':[("version:'v309'","version:'v315'")],
    'test_card_tablet_runtime_v300.py':[("version:'v309'","version:'v315'")],
    'test_pokemon_generation_display_v207.py':[
        ('mixed_script_conflict','edition_evidence_conflict'),
        ('v309-edition-isolated-ocr-learning','v315-evidence-isolated-confirmed-learning'),
        ("version:'v309'","version:'v315'"),
        ('Pokémon generation runtime v309: PASS','Pokémon generation runtime v315: PASS'),
        ('self.assertIn("confidence:.72", source)','self.assertIn("confidence:year?.78:.72", source)'),
    ],
}
for filename,pairs in replacements.items():
    p=Path(filename);text=p.read_text(encoding='utf-8')
    for old,new in pairs:
        if old not in text:raise RuntimeError(f'{filename}: missing {old!r}')
        text=text.replace(old,new)
    p.write_text(text,encoding='utf-8')
print('v315 regression contracts aligned')
