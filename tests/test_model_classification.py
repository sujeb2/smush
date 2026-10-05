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
        worker.serial.poll_machine_status.return_value = (False, 0)
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
        worker.serial.write_detection.assert_called_once_with('obj2_detect[plastic]\n', 0)

    def test_can_triggers_only_output_one(self):
        worker = self.run_frame([0.01, 0.01, 0.03, 0.95])
        worker.serial.write_detection.assert_called_once_with('obj1_detect[can]\n', 0)

    def test_uncertain_classification_does_not_trigger_output(self):
        worker = self.run_frame([0.01, 0.01, 0.55, 0.43])
        worker.serial.write_detection.assert_not_called()
        self.assertEqual(worker.names, [])

    def test_unmapped_class_does_not_trigger_output(self):
        worker = self.run_frame([0.01, 0.95, 0.03, 0.01])
        worker.serial.write_detection.assert_not_called()
        self.assertEqual(worker.names, ['paper'])

    def test_detection_results_remain_supported(self):
        worker = model.Model.__new__(model.Model)
        result = Results(self.frame, 'frame.jpg', self.names,
                         boxes=torch.tensor([[0, 0, 20, 20, 0.9, 3]]))
        recognized = worker.foundObjs(result)
        self.assertEqual(recognized[0][0], 'can')
        self.assertAlmostEqual(recognized[0][1], 0.9)
        empty = Results(self.frame, 'frame.jpg', self.names, boxes=torch.empty((0, 6)))
        self.assertEqual(worker.foundObjs(empty), [])

    def gated_worker(self):
        worker = model.Model.__new__(model.Model)
        worker.timestamp, worker.model_path = 'test', 'classifier.pt'
        worker.vc = Mock()
        worker.serial = Mock()
        worker.serial_ignore = worker.captured = False
        worker.names, worker.confident = ['stale can'], [.99]
        self.machine_state = (False, 0)
        worker.serial.poll_machine_status.side_effect = lambda: self.machine_state
        return worker

    def test_busy_frames_skip_all_inference_then_idle_resumes(self):
        worker = self.gated_worker()
        states = iter([(True, 1), (True, 1), (False, 2), (False, 2)])

        def read():
            self.machine_state = next(states)
            return True, self.frame

        def predict(**kwargs):
            worker.captured = True
            return iter([Results(self.frame, 'frame.jpg', self.names,
                                 probs=torch.tensor([.01, .01, .03, .95]))])

        worker.vc.read.side_effect = read
        with patch.object(model, 'YOLO') as loader, patch.object(model.time, 'sleep'):
            classifier = loader.return_value.to.return_value
            classifier.task = 'classify'
            classifier.predict.side_effect = predict
            worker.liveFeedCapture()
            classifier.predict.assert_called_once()
        self.assertEqual(worker.vc.read.call_count, 4)
        worker.serial.write_detection.assert_called_once_with('obj1_detect[can]\n', 2)
        worker.serial.read.assert_not_called()

    def test_busy_during_inference_discards_every_result(self):
        for final_state in ((True, 1), (False, 2)):
            with self.subTest(final_state=final_state):
                worker = self.gated_worker()
                worker.vc.read.return_value = True, self.frame
                worker.foundObjs = Mock()

                def predict(**kwargs):
                    worker.captured = True
                    self.machine_state = final_state
                    yield Results(self.frame, 'frame.jpg', self.names,
                                  probs=torch.tensor([.01, .01, .03, .95]))

                with patch.object(model, 'YOLO') as loader:
                    classifier = loader.return_value.to.return_value
                    classifier.task = 'classify'
                    classifier.predict.side_effect = predict
                    worker.liveFeedCapture()
                worker.foundObjs.assert_not_called()
                worker.serial.write_detection.assert_not_called()
                self.assertEqual(worker.names, [])
                self.assertEqual(worker.confident, [])

    def test_fallback_also_skips_inference_until_idle(self):
        worker = self.gated_worker()
        worker.model_path = 'tiny-yolov3.pt'
        worker.camera = worker.vc
        states = iter([(True, 1), (False, 2), (False, 2)])

        def read():
            self.machine_state = next(states)
            return True, self.frame

        def detect(**kwargs):
            worker.captured = True
            return self.frame, []

        worker.camera.read.side_effect = read
        with patch.object(model, 'ObjectDetection') as detector, patch.object(model.time, 'sleep'), \
                patch.object(model.cv2, 'VideoWriter') as writer:
            detector.return_value.detectObjectsFromImage.side_effect = detect
            worker.fallbackLiveFeed(False)
            detector.return_value.detectObjectsFromImage.assert_called_once()
            self.assertEqual(writer.return_value.write.call_count, 3)
            writer.return_value.release.assert_called_once()
        self.assertEqual(worker.camera.read.call_count, 3)


if __name__ == '__main__':
    unittest.main()
