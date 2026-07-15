from datetime import datetime
import os, cv2, numpy, cv2, h5py
from keras.models import load_model
from PIL import Image, ImageOps
import configparser as cfg

config = cfg.ConfigParser()
config.read('./files/model_conf.ini', encoding='utf-8')
numpy.set_printoptions(suppress=False)

class Model:
	def __init__(self, model_path, labels_path):
		try:
			self.timestamp = datetime.now().strftime('%H:%M:%S')
			self.vc = cv2.VideoCapture(0)
			
			os.makedirs("./files/captures", exist_ok=True)
			self.path = f"./files/captures/capture_{self.timestamp}.png"
			self.captured = False
			print(f"[{self.timestamp}] [ModelRecog] model path: {model_path}, labels path: {labels_path}")
			
			if not self.vc.isOpened():
				print(f"[{self.timestamp}] [ModelRecog] Failed to init camera. Check if camera is connected.")
				quit()
				
			print(f"[{self.timestamp}] [ModelRecog] Available camera: {self.vc.getBackendName()}")
			
			try:
				self.convert_h5(model_path)
				self.model = load_model(model_path, compile=False)
				self.names = open(labels_path, "r").readlines()
				print(f"[{self.timestamp}] [ModelRecog] Model config loaded: {config.sections()}")
			except Exception as e:
				print(f"[{self.timestamp}] [ModelRecog] failed to read model configuration sections.")
				print(f"[{self.timestamp}] [ModelRecog] Detailed log: \n{e}")
			print(f"[{self.timestamp}] [ModelRecog] Model recog init done.")
			
		except IOError as e:
			print(f"[{self.timestamp}] [ModelRecog] IOError: failed to init model recog. Check if files exist.")
			print(f"[{self.timestamp}] [ModelRecog] Detailed log: \n{e}")
		except Exception as e:
			print(f"[{self.timestamp}] [ModelRecog] Exception: failed to init model recog.")
			print(f"[{self.timestamp}] [ModelRecog] Detailed log: \n{e}")
	
	def convert_h5(self, file_path: str):
		f = h5py.File(file_path, mode="r+")
		model_config_string = f.attrs.get("model_config")
		if model_config_string.find('"groups": 1,') != -1:
			model_config_string = model_config_string.replace('"groups": 1,', '')
			f.attrs.modify('model_config', model_config_string)
			f.flush()
			model_config_string = f.attrs.get("model_config")
			assert model_config_string.find('"groups": 1,') == -1
			print(f"[{self.timestamp}] [ModelRecog] reconfigured model file: {file_path}")
		else:
			print(f"[{self.timestamp}] [ModelRecog] reconfiguring not required, skipping.")
		f.close()

	def capture(self):
		while not self.captured:
			ret, img = self.vc.read()
			
			if not ret or img is None:
				print(f"[{self.timestamp}] [ModelRecog] failed to grab frame. retry")
				continue
			show_vid = 'False'
			data = numpy.ndarray(shape=(1, 224, 224, 3), dtype=numpy.float32)
			if 'GENERIC' in config and 'ShowCaptureVid' in config['GENERIC']:
				show_vid = config['GENERIC']['ShowCaptureVid']
			
			# predict part
			self.image = Image.open(self.path).convert("RGB")
			self.image = ImageOps.fit(self.iamge, (224, 224), Image.Resampling.LANCZOS)
			image_array = numpy.asarray(self.image)
			normal_array = (image_array.astype(numpy.float32) / 127.5)-1
			self.datas[0] = normal_array

			prediction = self.model.predict(self.data)
			index = numpy.argmax(prediction)
			class_name = self.names[index]
			confidence_score = prediction[0][index]
			print(f"[{self.timestamp}] [ModelRecog] prediction: {class_name} score: {confidence_score}")
			return class_name.strip()

	def cancel_capture(self):
		self.captured = True
		print(f"[{self.timestamp}] [ModelRecog] capture cancelled.")
		
	def getIsitCaptured(self):
		return self.captured