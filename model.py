from datetime import datetime
from teachable_machine import TeachableMachine
import cv2 as cv
import configparser as config
import os

class Model:
	def __init__(self, model, labels):
		try:
			self.timestamp = datetime.now().strftime('%H:%M:%S')
			self.vc = cv.VideoCapture(0)
			self.model = TeachableMachine(model_path=model, labels_flie_path=labels)
			self.path = f"./files/captures/capture_{self.timestamp}.png"
			self.captured = False	
			self.cfg = config.ConfigParser()
			if(self.vc.isOpened() == False):
				print(f"[{self.timestamp}] [ModelRecog] Failed to init camera. check if camera is available.")
				quit()
			print(f"[{self.timestamp}] [ModelRecog] available camera: {self.vc.getBackendName()}")
			try:
				self.cfg.read('./files/model_conf.ini')
				print(f"[{self.timestamp}] [ModelRecog] model configuration loaded: {self.cfg.sections()}")
			except FileNotFoundError:
				print(f"[{self.timestamp}] [ModelRecog] Failed to read model configuration file. FileNotFoundException")
				quit()
		except:
			print(f"[{self.timestamp}] [ModelRecog] Failed to init model recog. Check if the files are available.")

	def capture(self):
		while self.captured == False:
			_, img = cv.read()
			cv.imwrite(self.path, img)
			result = self.model.classify_image(self.path)
			img_result = self.model.show_prediction_on_image(self.path, result)

			print(f"[{self.timestamp}] [ModelRecog] class_index: {result['class_index']}, confidence: {result['class_confidence']}, predicted: {result['predictions']}")
			if self.cfg['GENERIC']['ShowCaptureVid'] == True:
				cv.imshow("stream", img_result)
				k = cv.waitKey(1)
				if k == 27:
					return result['predictions']
			return result['predictions']
		
	def getIsitCaptured(self):
		return self.captured
