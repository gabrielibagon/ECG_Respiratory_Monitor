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


class GUI(QtGui.QWidget):
	def __init__(self, synthetic=False,data_buffer=None):
		super(GUI,self).__init__()
		

		self.db = data_buffer
		self.gui_setup()
		self.db.new_data.connect(self.unpack_data)
		signal.signal(signal.SIGINT, signal.SIG_DFL)

	def gui_setup(self):
		self.setWindowTitle("ECG-Respiratory Monitor")
		self.set_layout()
		
	def set_layout(self):
		layout = QtGui.QGridLayout()

		# Header
		header_font = QtGui.QFont('default',weight=QtGui.QFont.Bold)
		header_font.setPointSize(16)
		title = QtGui.QLabel("ECG-Respiratory Monitor")
		title.setFont(header_font)

		#Separator
		verticalLine0 = QtGui.QFrame()
		verticalLine0.setFrameShape(QtGui.QFrame().HLine)
		verticalLine0.setFrameShadow(QtGui.QFrame().Sunken)

		#Connect Buttom
		self.connect_button = QtGui.QPushButton("Start System")
		self.connect_button.clicked.connect(self.db.run)
		self.connect_button.setFixedWidth(200)

		# ECG Scroll
		self.ecg_scroll = pg.PlotWidget(title="ECG")
		self.ecg_scroll_time_axis = np.linspace(-7.3,0,2048)							# the y axis of the scroll plot
		self.ecg_scroll.setXRange(-7.2,-.1, padding=.0001)
		self.ecg_scroll.setYRange(-500,500)
		self.ecg_scroll.setLabel('bottom','Time','Seconds')
		self.ecg_scroll.setLabel('left','Amplitude','uV')
		self.ecg_curve = self.ecg_scroll.plot()

		#BPM Display
		self.bpm_display = QtGui.QLCDNumber(self)
		self.bpm_display.display("--")
		self.bpm_display.setFixedWidth(200)
		#Breaths Per Minute Display
		self.breathspermin_display = QtGui.QLCDNumber(self)
		self.breathspermin_display.display("--")
		self.breathspermin_display.setFixedWidth(200)


		#IBI-BPM-BPM Scroll
		self.analysis_scroll = pg.PlotWidget(title="Inter Beat Interval - Beats Per Minute - Breaths Per Minute")
		self.analysis_scroll_time_axis = np.linspace(-1000,0,500)
		self.analysis_scroll.setXRange(-500,0,padding=0.0001)
		self.analysis_scroll.setLabel('bottom','Samples')
		self.analysis_scroll.setLabel('left','Magnitude')			
		self.analysis_scroll.setYRange(0,1.5)
		#BPM Curve
		self.bpm_curve = self.analysis_scroll.plot()
		self.bpm_curve.setPen(color=(255,255,0))
		#IBi Curve
		self.ibi_curve = self.analysis_scroll.plot()
		self.ibi_curve.setPen(color=(255,0,0))
		#Breathing Curve
		self.breathing_curve = self.analysis_scroll.plot()
		self.breathing_curve.setPen(color=(0,0,255))


		#Respiratory meters
		self.resp_plot = pg.PlotWidget(title="Breath Monitor")
		self.resp_plot.setXRange(-0.5,2.5)
		self.resp_plot.hideAxis('left')
		self.rect1 = pg.BarGraphItem(x=[0,1,2],height=2,width=.2,brush='r')
		xdict = dict(enumerate(['Input 1','Input 2','Input 3']))
		axis = self.resp_plot.getAxis("bottom")
		axis.setTicks([xdict.items()])
		self.resp_plot.addItem(self.rect1)

		#Add all components to layout
		layout.addWidget(title,0,0)
		layout.addWidget(verticalLine0,1,0,1,3)
		layout.addWidget(self.connect_button,2,0)
		layout.addWidget(self.ecg_scroll,3,0,1,3)
		layout.addWidget(self.analysis_scroll,4,0,1,3)
		layout.addWidget(self.bpm_display,5,0)
		layout.addWidget(self.resp_plot,5,1)
		layout.addWidget(self.breathspermin_display,5,2)
		self.setLayout(layout)

		self.show()

	@pyqtSlot('PyQt_PyObject')	
	def unpack_data(self,data):
		'''
		This method receives the new data and analysis, and fixes it for plotting

		Unpacks the received array into 6 different components:
			1) ecg_plot_data: 				ECG data 
			2) ibi_array:							Array of 500 last inter beat interval values
			3) heart_rate_array: 			Array of 500 last beats per minute values
			4) breathing_rate_array:	Array of 500 last breaths per minute values
			5) current_bpm:						Current beats-per-minute value
			6) raw_rband:							Current values of the 3 resistance bands
		'''

		#Unpack the array
		ecg_data = data['ecg_data']
		ibi_array = data['ibi_array']
		heart_rate_array = data['heart_rate_array']
		current_bpm = data['current_bpm']
		breathing_rate_array = data['breathing_rate_array']
		raw_rband = data['raw_rband']

		#Process for plotting:
		ibi_array = np.asarray(ibi_array)									#convert deque to array
		heart_rate_array = np.asarray(heart_rate_array)	 	#convert deque to array
		heart_rate_array = heart_rate_array/180.0					#turn bpm into a percentage of 180 (theoretical bpm maximum)
		
		breathing_rate_array = np.asarray(breathing_rate_array)
		breathing_rate_array = breathing_rate_array/120 	#turn breaths into a percentage of 120 (thearetical maximum)
		heart_rate_array[0] = 10
		# Update plot
		self.ecg_curve.setData(x=self.ecg_scroll_time_axis,y=([point for point in ecg_data]))
		self.bpm_curve.setData(x=self.analysis_scroll_time_axis,y=([point for point in heart_rate_array]))
		self.ibi_curve.setData(x=self.analysis_scroll_time_axis,y=([point for point in ibi_array]))		

		#Update Displays
		if current_bpm == 0:
			current_bpm = "--"
		self.bpm_display.display(current_bpm)

		


class Data_Buffer(QThread):
	data_to_plot = []		
	new_data = pyqtSignal(object)

	def __init__(self):
		QThread.__init__(self)
		self.display_size = 2048
		self.buffer_size = 256
		self.rband_buffer_size = 1024
		self.display_buf = deque([0]*self.display_size)
		self.data_buf = deque([0]*self.buffer_size)
		self.display_filters = filters.Filters(self.display_size,8,20)
		self.analyze_filters = filters.Filters(self.buffer_size,5,12)
		self.rband_buf1 = deque([0]*self.rband_buffer_size)
		self.rband_buf2 = deque([0]*self.rband_buffer_size)
		self.rband_buf3 = deque([0]*self.rband_buffer_size)

		self.analysis = Analysis()
		self.count = 0
		self.board = None

	def run(self):
		self.initialize_board()
		time.sleep(1)
		lapse=-1

		boardThread = threading.Thread(target=self.board.start_streaming,args=(self.data_collect,lapse))
		boardThread.daemon = True
		boardThread.start()

	def disconnect(self):
		self.board.disconnect()
		atexit.register(disconnect)


	def initialize_board(self):
		self.board = bci.OpenBCIBoard()
		time.sleep(1)

		#turn off all channels except Channel 1
		self.board.ser.write(b'2')
		self.board.ser.write(b'3')
		self.board.ser.write(b'4')
		self.board.ser.write(b'5')
		self.board.ser.write(b'6')
		self.board.ser.write(b'7')
		self.board.ser.write(b'8')

	def data_collect(self,sample):
		'''
		Function: data_collect
		---------------------------------------------------------------
		Receives the data streaming in from the board and stores it in
		data_buffer. This buffer, once filled with new data, is sent to
		be filtered and then analyzed.
		'''
		global new_data
		ecg_sample = sample.channel_data[0]*-1
		raw_rband = sample.aux_data
		self.count+=1
		self.display_buf.popleft()
		self.display_buf.append(ecg_sample)
		

		self.data_buf.popleft()
		self.data_buf.append(ecg_sample)

		self.rband_buf1.popleft()
		self.rband_buf1.append(raw_rband[0])

		self.rband_buf2.popleft()
		self.rband_buf2.append(raw_rband[1])

		self.rband_buf3.popleft()
		self.rband_buf3.append(raw_rband[2])

		if not self.count%20:
			#ECG DATA
			ecg_display = self.display_filters.bandpass(self.display_buf)
			filtered = self.analyze_filters.bandpass(self.data_buf)
			self.analysis.peak_detect(filtered)
			#BREATHING DATA
			breathing_rate = self.analysis.respiratory_analysis(self.rband_buf3)

			#pack data into dictionary
			data_to_plot = {
				'ecg_data' : ecg_display,
				'ibi_array' : self.analysis.ibi_array,
				'heart_rate_array' : self.analysis.heart_rate_array,
				'current_bpm' : self.analysis.current_bpm,
				'breathing_rate_array' : self.analysis.breathing_rate_array,
				'raw_rband' : raw_rband
			}
			self.new_data.emit(data_to_plot)

class Analysis:
	def __init__(self):
		self.last_beat = 0
		self.last_breath = 0
		self.number_of_beats = 15
		self.beat_buffer = deque([0]*self.number_of_beats)
		self.breath_buffer = deque([0]*self.number_of_beats)
		self.ibi_array = deque([0]*500)
		self.hrv_diff = deque([0]*100)
		self.heart_rate_array = deque([0]*500)
		self.breathing_rate_array = deque([0]*500)
		self.current_bpm = 0
		self.BREATH = False



	def peak_detect(self,data_buf):
		peak_data = self.pan_tompkins(data_buf)
		self.peak_data = peak_data
		current_time = time.time()
		if self.current_bpm > 40:
			time_threshold = 1/(self.current_bpm+20) * 60 #the next beat can't be more than 10 bpm higher than the last
		else:
			time_threshold = .300	
		for i in range(25):
			# Threshold for heartbeat: 1) 300ms since last beat 2) peak detected
			if (current_time - self.last_beat >.300 and (peak_data[-(i+1)] - peak_data[-i]) > 10):
				#calculate the interbeat interval
				time_dif = current_time - self.last_beat
				self.last_beat = current_time
				#find the hrv interval
				self.ibi_array.popleft()
				self.ibi_array.append(time_dif)
				#calculate the bpm
				self.bpm()
				break


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
		# print(integral)
		return integral
		
	def bpm(self):
		self.beat_buffer.popleft()
		self.beat_buffer.append(self.last_beat)
		total_time = self.beat_buffer[-1] - self.beat_buffer[0]
		bpm = (60/total_time)*self.number_of_beats
		self.current_bpm = int(bpm)
		self.heart_rate_array.popleft()
		self.heart_rate_array.append(self.current_bpm)
		return self.current_bpm

	def respiratory_analysis(self,resp_buf):
		resp_diff = np.diff(resp_buf)
		current_time = time.time()
		if (not self.BREATH and (resp_buf[-150] - resp_buf[-1]) < -15):
			time_dif = current_time - self.last_breath
			self.last_breath = current_time
			self.breathing_rate_array.popleft()
			self.breathing_rate_array.append(time_dif)
			self.breaths_per_minute()
			self.BREATH = True
		elif (self.BREATH and (resp_buf[-150] - resp_buf[-1]) > 15):
			self.BREATH = False
			print("OUT")

	def breaths_per_minute(self):
		self.breath_buffer.popleft()
		self.breath_buffer.append(self.last_breath)
		total_time = self.breath_buffer[-1] - self.breath_buffer[0]
		bpm = (60/total_time)*len(self.breath_buffer)
		self.current_bpm = int(bpm)
		self.bpm_array.popleft()
		self.bpm_array.append(self.current_bpm)
		return self.current_bpm

def data_feed(db):
	'''
	Synthetic Data Feed
	'''	
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
	db = Data_Buffer()
	app = QtGui.QApplication(sys.argv)
	gui = GUI(data_buffer=db)
	sys.exit(app.exec_())

if __name__ == '__main__':
	main()