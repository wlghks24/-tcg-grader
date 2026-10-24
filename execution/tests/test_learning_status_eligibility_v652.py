"""Public progress must distinguish retained history from eligible training data."""
import unittest
from unittest.mock import patch
import tcg_updater as runtime
import verified_collection_neural as query
import verified_collection_job_neural as job


class LearningStatusEligibilityTests(unittest.TestCase):
    def tearDown(self):
        with runtime.COLLECTION_NEURAL_STATUS_LOCK:
            runtime.COLLECTION_NEURAL_STATUS_CACHE.update(signature=None, value=None)

    def test_stored_legacy_labels_do_not_inflate_training_progress(self):
        with patch.object(runtime,"_collection_neural_signature",return_value=None), \
             patch.object(query,"status",return_value={"ok":True,"active":False,"label_count":285,
                                                       "eligible_training_labels":0,"minimum_labels":1000}), \
             patch.object(job,"status",return_value={"ok":True,"active":False,"label_count":551,"minimum_labels":1000}):
            result=runtime.collection_neural_status()
        self.assertEqual(836,result["label_count"])
        self.assertEqual(551,result["eligible_training_labels"])
        self.assertEqual(1449,result["labels_remaining"])
        self.assertEqual(27.55,result["progress_percent"])
        self.assertFalse(result["active"])
        self.assertFalse(result["verification_bypass"])


if __name__=="__main__":unittest.main()
