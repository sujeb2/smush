from teachable_machine import TeachableMachine
import cv2 as cv
import configparser as config

class Model:
	def __init__(self, model, labels):
		try:
			self.vc = cv.VideoCapture(0)
			self.model = TeachableMachine(model_path=model, labels_flie_path=labels)
			self.path = "capture.png"
			self.captured = False	
			self.cfg = config.ConfigParser()
			try:
				self.cfg.read('./files/model_conf.ini')
			except FileNotFoundError:
				print("Failed to read model configuration file. FileNotFoundException")
				quit()
		except:
			print("Failed to init model recog. Check if the camera and files are available.")

	def capture(self):
		while self.captured == False:
			_, img = cv.read()
			cv.imwrite(self.path, img)
			result = self.model.classify_image(self.path)
			img_result = self.model.show_prediction_on_image(self.path, result)

			print(f'class_index: {result["class_index"]}, confidence: {result["class_confidence"]}, predicted: {result["predictions"]}')
			if self.cfg['GENERIC']['ShowCaptureVid'] == True:
				cv.imshow("stream", img_result)
				k = cv.waitKey(1)
				if k == 27:
					return result['predictions']
			return result['predictions']
