import configparser
import unittest
from unittest.mock import Mock, patch

import numpy as np
import torch
from ultralytics.engine.results import Results

import model


class ClassificationIntegrationTests(unittest.TestCase):
    def setUp(self):
        settings = configparser.ConfigParser()
        settings.read_dict({
            'GENERIC': {'ShowCaptureVid': 'False', 'CameraFPS': '0', 'Verbose': 'False'},
            'DETECTION': {
                'HasExpectedObject': 'True', 'ClassificationConfidence': '0.8',
                'ExpectedObject_1': 'can', 'ExpectedObject_2': 'plastic',
            },
        })
        patcher = patch.object(model, 'config', settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.frame = np.zeros((32, 32, 3), dtype=np.uint8)
        self.names = {0: 'compressible', 1: 'paper', 2: 'plastic', 3: 'can'}

    def run_frame(self, probabilities):
        result = Results(self.frame, 'frame.jpg', self.names, probs=torch.tensor(probabilities))
        worker = model.Model.__new__(model.Model)
        worker.timestamp = 'test'
        worker.model_path = 'classifier.pt'
        worker.vc = Mock()
        worker.vc.read.return_value = (True, self.frame)
        worker.serial = Mock()
        worker.serial.read.return_value = False
        worker.serial_ignore = False
        worker.captured = False

        def predict(**kwargs):
            worker.captured = True
            return iter([result])

        with patch.object(model, 'YOLO') as loader:
            classifier = loader.return_value.to.return_value
            classifier.task = 'classify'
            classifier.names = self.names
            classifier.predict.side_effect = predict
            worker.liveFeedCapture()
            self.assertNotIn('task', loader.call_args.kwargs)
            self.assertNotIn('conf', classifier.predict.call_args.kwargs)
        worker.vc.release.assert_called_once()
        return worker

    def test_plastic_triggers_only_output_two(self):
        worker = self.run_frame([0.01, 0.01, 0.95, 0.03])
        worker.serial.write.assert_called_once_with('obj2_detect[plastic]\n')

    def test_can_triggers_only_output_one(self):
        worker = self.run_frame([0.01, 0.01, 0.03, 0.95])
        worker.serial.write.assert_called_once_with('obj1_detect[can]\n')

    def test_uncertain_classification_does_not_trigger_output(self):
        worker = self.run_frame([0.01, 0.01, 0.55, 0.43])
        worker.serial.write.assert_not_called()
        self.assertEqual(worker.names, [])

    def test_unmapped_class_does_not_trigger_output(self):
        worker = self.run_frame([0.01, 0.95, 0.03, 0.01])
        worker.serial.write.assert_not_called()
        self.assertEqual(worker.names, ['paper'])

    def test_detection_results_remain_supported(self):
        worker = model.Model.__new__(model.Model)
        result = Results(self.frame, 'frame.jpg', self.names,
                         boxes=torch.tensor([[0, 0, 20, 20, 0.9, 3]]))
        recognized = worker._recognized_objects(result)
        self.assertEqual(recognized[0][0], 'can')
        self.assertAlmostEqual(recognized[0][1], 0.9)
        empty = Results(self.frame, 'frame.jpg', self.names, boxes=torch.empty((0, 6)))
        self.assertEqual(worker._recognized_objects(empty), [])


if __name__ == '__main__':
    unittest.main()
