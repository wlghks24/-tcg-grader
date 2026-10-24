"""Optional image-worker failures never replace a live or advisory champion."""
import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from execution import tablet_image_autonomy as adapter,tablet_image_training as images
from execution.tests import test_tablet_image_training as fixtures

class ImageWorkerIsolationTests(unittest.TestCase):
    def test_malformed_real_challenger_is_held_and_champion_is_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inbox=root/'GRADE_TRAINING_INBOX';inbox.mkdir()
            row,manifest,registry=fixtures.ImageTrainingTests().fixture(inbox)
            manifest.rename(inbox/'verified_raw_photos.json')
            state=root/'state';state.mkdir();key=images.digest((('pokemon','JP','PSA'),'identity'))[:20]
            challenger=state/(key+'.challenger.json');challenger.write_text('[]')
            champion=state/(key+'.champion.json');champion.write_bytes(b'previous-reviewed-champion')
            with patch.object(adapter,'resource_budget',return_value=None),patch('verified_grade_learning_v135.registry_index',return_value=registry):
                result=adapter.run(root=root,state=state,train=True)
            self.assertEqual('HOLD',result['status']);self.assertEqual('ValueError',result['reason'])
            self.assertFalse(result['production_model_changed'])
            self.assertEqual(b'previous-reviewed-champion',champion.read_bytes())
            self.assertEqual('[]',challenger.read_text())
            self.assertTrue((state/'admitted_features_v2.json').exists())

    def test_optional_dependency_and_numerical_errors_are_contained_but_interrupts_propagate(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);inbox=root/'GRADE_TRAINING_INBOX';inbox.mkdir()
            (inbox/'verified_raw_photos.json').write_text('{"schema":1,"rows":[]}')
            for error in (AttributeError('unsupported API'),OverflowError('invalid numeric artifact')):
                with self.subTest(error=type(error).__name__),patch.object(adapter,'resource_budget',return_value=None),patch.object(images,'run',side_effect=error):
                    result=adapter.run(root=root,state=root/'state',train=True)
                    self.assertEqual('HOLD',result['status']);self.assertEqual(type(error).__name__,result['reason'])
            with patch.object(adapter,'resource_budget',return_value=None),patch.object(images,'run',side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):adapter.run(root=root,state=root/'state',train=True)
