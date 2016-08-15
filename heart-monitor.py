import open_bci_v3 as bci
import filters
import numpy as np
import sympy
from scipy import integrate
import csv
import time
from collections import deque
from pyqtgraph.Qt import QtGui, QtCore
import pyqtgraph as pg
from PyQt4.QtCore import QThread, pyqtSignal, pyqtSlot, SIGNAL
import signal
import sys
import threading
import atexit
# np.set_printoptions(threshold=np.inf)


class GUI():
	def __init__(self, synthetic=False,data_buffer=None, parent=None):
		self.app = QtGui.QApplication([])  		# new instance of QApplication
		super(self.__class__,self).__init__()
		db = data_buffer
		db.new_data.connect(self.update_plot)			# Threading connect for plotting
		self.window = self.ApplicationWindow(db)
		self.window.show()
		signal.signal(signal.SIGINT, signal.SIG_DFL) #close on exit
		sys.exit(self.app.exec_())

	class ApplicationWindow(QtGui.QMainWindow):
		def __init__(self,db):
			QtGui.QMainWindow.__init__(self)
			self.setAttribute(QtCore.Qt.WA_DeleteOnClose)
			self.setWindowTitle("Heart Monitor")
			# self.board = lambda: bci.OpenBCIBoard()
			self.board = None
			self.db = db
			main_widget = QtGui.QWidget(self)

			self.setCentralWidget(main_widget)

			
			layout = QtGui.QGridLayout()
			self.connect_button = QtGui.QPushButton("Connect Board")
			self.connect_button.clicked.connect(db.run)
			self.connect_button.setFixedWidth(200)
			layout.addWidget(self.connect_button,0,0)

			# self.stream_button = QtGui.QPushButton("Start Streaming")
			# self.stream_button.clicked.connect(db.stream)
			# self.stream_button.setFixedWidth(200)

			# layout.addWidget(self.stream_button,0,1)


			self.ecg_scroll = pg.PlotWidget(title="ECG")
			self.ecg_scroll_time_axis = np.linspace(-7.3,0,2048)							# the y axis of the scroll plot
			last_data_window = []												# saves last data for smoothing() function			
			self.ecg_scroll.setXRange(-7.3,0, padding=.0001)
			self.ecg_scroll.setYRange(-500,500)
			self.ecg_scroll.setLabel('bottom','Time','Seconds')
			self.ecg_curve = self.ecg_scroll.plot()

			layout.addWidget(self.ecg_scroll,1,0,1,2)

			self.bpm_display = QtGui.QLCDNumber(self)
			self.bpm_display.display("--")
			layout.addWidget(self.bpm_display,2,0)

			self.hrv_scroll = pg.PlotWidget(title="Inter Beat Interval")
			self.hrv_scroll_time_axis = np.linspace(-1000,0,500)
			self.hrv_scroll.setXRange(-500,0,padding=0.0001)
			self.hrv_scroll.setYRange(0,1.5)

			self.bpm_curve = self.hrv_scroll.plot()
			self.bpm_curve.setPen(color=(255,255,0))

			self.hrv_curve = self.hrv_scroll.plot()
			self.hrv_curve.setPen(color=(255,0,0))

			self.breathing_curve = self.hrv_scroll.plot()
			self.breathing_curve.setPen(color=(0,0,255))

			layout.addWidget(self.hrv_scroll,2,1)
			main_widget.setLayout(layout)


	# def update_plot(self,data_to_plot,hrv_array,beat_buffer, bpm):
	@pyqtSlot('PyQt_PyObject')	
	def update_plot(self,data_to_plot,hrv_array,bpm_array, bpm,breathing_rate_array):
		# print('signal 2')
		bpm_array = np.asarray(bpm_array)/180.0 #get bpm as a percentage of 180 (a theoretical bpm "maximum")
		hrv_array = np.asarray(hrv_array)
		breathing_rate_array = np.asarray(breathing_rate_array)/100
		# breathing_buf = np.asarray(breathing_buf - np.min(breathing_buf))/(np.max(breathing_buf)-np.min(breathing_buf))
		# self.window.hrv_scroll.clear()
		self.window.bpm_curve.setData(x=self.window.hrv_scroll_time_axis,y=([point for point in bpm_array]))
		self.window.hrv_curve.setData(x=self.window.hrv_scroll_time_axis,y=([point for point in hrv_array]))		
		self.window.ecg_curve.setData(x=self.window.ecg_scroll_time_axis,y=([point for point in data_to_plot]))
		# self.window.breathing_curve.setData(x=self.window.hrv_scroll_time_axis,y=([point for point in breathing_rate_array]))
		if bpm == 0:
			bpm = "--"
		self.window.bpm_display.display(bpm)
		self.app.processEvents()

		


class Data_Buffer(QThread):
	data_to_plot = []		
	new_data = pyqtSignal(object,object,object,object,object)


	def __init__(self):
		QThread.__init__(self)
		self.display_size = 2048
		self.buffer_size = 256
		self.display_buf = deque([0]*self.display_size)
		self.data_buf = deque([0]*self.buffer_size)
		self.display_filters = filters.Filters(self.display_size,8,20)
		self.analyze_filters = filters.Filters(self.buffer_size,5,12)
		self.breath_buf = deque([0]*self.buffer_size)
		self.analysis = Analysis()
		self.count = 0
		self.board = None

	def run(self):
		# data_feed(self)
		self.initialize_board()
		time.sleep(1)
		lapse=-1

		boardThread = threading.Thread(target=self.board.start_streaming,args=([self],lapse))
		boardThread.daemon = True
		boardThread.start()

	def disconnect(self):
		signal.signal(signal.SIGINT, self.original_sigint)
		self.board.disconnect()
		sys.exit(1)


	def initialize_board(self):

		# QThread.__init__(self)
		self.original_sigint = signal.getsignal(signal.SIGINT)
		signal.signal(signal.SIGINT, self.disconnect)
		self.board = bci.OpenBCIBoard()
		time.sleep(1)
		#turn off all channels except CH1
		self.board.ser.write(b'2')
		self.board.ser.write(b'3')
		self.board.ser.write(b'4')
		self.board.ser.write(b'5')
		self.board.ser.write(b'6')
		self.board.ser.write(b'7')
		self.board.ser.write(b'8')



	
	'''
	Function: data_collect
	---------------------------------------------------------------
	Receives the data streaming in from the board and stores it in
	data_buffer. This buffer, once filled with new data, is sent to
	be filtered and then analyzed.
	# '''
	# @pyqtSlot('PyQt_PyObject')
	def data_collect(self,sample):
		global new_data

		ecg_sample = np.array(sample.channel_data[-1]*-1)
		breath = sample.aux_data[2]
		self.count+=1
		self.display_buf.popleft()
		self.display_buf.append(ecg_sample)
		

		self.data_buf.popleft()
		self.data_buf.append(ecg_sample)

		self.breath_buf.popleft()
		self.breath_buf.append(breath)

		# self.data_buf*0
		if not self.count%20:
			#ECG DATA
			display = self.display_filters.bandpass(self.display_buf)
			filtered = self.analyze_filters.bandpass(self.data_buf)
			analyzed = self.analysis.peak_detect(filtered)
			#BREATHING DATA
			breathing_rate = self.analysis.respiratory_analysis(self.breath_buf)
			# print('signal 1')
			self.new_data.emit(display,np.array(self.analysis.hrv_array),self.analysis.bpm_array,self.analysis.current_bpm,self.breath_buf)
			# self.new_data.emit('','','','')

class Analysis:
	def __init__(self):
		self.last_beat = 0
		self.number_of_beats = 15
		self.beat_buffer = deque([0]*self.number_of_beats)
		self.hrv_array = deque([0]*500)
		self.hrv_diff = deque([0]*100)
		self.bpm_array = deque([0]*500)
		self.breathing_rate_array = deque([0]*500)
		self.current_bpm = 0


	def peak_detect(self,data_buf):
		peak_data = self.pan_tompkins(data_buf) # apply the altered pan-tomkins algorithm to the data
		current_time = time.time()
		if self.current_bpm > 40:
			time_threshold = 1/(self.current_bpm+20) * 60 #the next beat can't be more than 10 bpm higher than the last
		else:
			time_threshold = .300	
		for i in range(25):
			# if a heart beat is detected after a certain amount of time
			if (current_time - self.last_beat >.300 and (peak_data[-(i+1)] - peak_data[-i]) > 10):
				print("BEAAAAAAAAAAAAAAAAAAAAAAT ")
				#calculate the interbeat interval
				time_dif = current_time - self.last_beat
				self.last_beat = current_time
			
				#find the hrv interval
				self.hrv_array.popleft()
				self.hrv_array.append(time_dif)
				#calculate the bpm
				self.bpm()

	def pan_tompkins(self,data_buf):
		'''
		1) 3rd differential of the data_buffer (512 samples)
		2) square of that
		3) integrate -> integrate(data_buffer)
		4) take the pulse from that 
		'''
		order = 3
		diff = np.diff(data_buf,3)
		for i in range(order):
			diff = np.insert(diff,0,0)
		square = np.square(diff)
		window = 64
		integral = np.zeros((len(square)))
		for i in range(len(square)):
			integral[i] = np.trapz(square[i:i+window])
		return integral
		
	def bpm(self):
		self.beat_buffer.popleft()
		self.beat_buffer.append(self.last_beat)
		total_time = self.beat_buffer[-1] - self.beat_buffer[0]
		bpm = (60/total_time)*self.number_of_beats
		self.current_bpm = int(bpm)
		self.bpm_array.popleft()
		self.bpm_array.append(self.current_bpm)
		return self.current_bpm

	def respiratory_analysis(self,resp_buf):
		print(resp_buf)
		if 0 and 1 and -1 in np.diff(resp_buf):
			print("breathing")
		pass


'''
Synthetic Data Feed
'''
def data_feed(db):
	channel_data = []
	with open('raw_data.txt', 'r') as file:
		reader = csv.reader(file, delimiter=',')
		for j,line in enumerate(reader):
			line = [x.replace(' ','') for x in line]
			channel_data.append(line) #list
	start = time.time()

	# Mantain the 250 Hz sample rate when reading a file
	for i,sample in enumerate(channel_data):
		end = time.time()
		# Wait for a period of time if the program runs faster than real time
		time_of_recording = i/250
		time_of_program = end-start
		# print('i/250 (time of recording)', time_of_recording)
		# print('comp timer (time of program)', time_of_program)
		if time_of_recording > time_of_program:
			time.sleep(time_of_recording-time_of_program)
		db.data_collect(float(sample[-1]) * -1)




def main():
	# board = bci.OpenBCIBoard()
	# board.start_streaming(data_collect)
	db = Data_Buffer()
	gui = GUI(data_buffer=db)


if __name__ == '__main__':
	main()