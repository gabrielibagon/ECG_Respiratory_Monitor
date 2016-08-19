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

		#IBI-BPM-BPM Scroll
		self.analysis_scroll = pg.PlotWidget()
		self.analysis_scroll_time_axis = np.linspace(-300000,0,15000)
		self.analysis_scroll.setXRange(-10000,0,padding=0.0001)
		self.analysis_scroll.setLabel('bottom','Samples')
		self.analysis_scroll.setLabel('left','Magnitude')			
		self.analysis_scroll.setYRange(0,1.5)
		#BPM Curve
		self.bpm_curve = self.analysis_scroll.plot()
		self.bpm_curve.setPen(color=(255,255,0))
		#IBi Curve
		self.ibi_curve = self.analysis_scroll.plot()
		self.ibi_curve.setPen(color=(255,0,0))
		#Breathing Curves
		self.breathing_curve1 = self.analysis_scroll.plot()
		self.breathing_curve1.setPen(color=(135,206,235))
		self.breathing_curve2 = self.analysis_scroll.plot()
		self.breathing_curve2.setPen(color=(0,191,255))
		self.breathing_curve3 = self.analysis_scroll.plot()
		self.breathing_curve3.setPen(color=(102,102,250))
		self.breathing_curves = [self.breathing_curve1,self.breathing_curve2,self.breathing_curve3]
		#Legend
		self.legend = self.analysis_scroll.addLegend()
		self.legend.addItem(self.bpm_curve,'Heart Rate')
		self.legend.addItem(self.ibi_curve,'Inter Beat Interval')
		self.BREATHING_LEGEND = [False,False,False]

		#BPM Display
		self.bpm_display = QtGui.QLCDNumber(self)
		self.bpm_display.display("--")
		self.bpm_display.setFixedWidth(200)
		#BPM Display Title
		self.bpm_display_title = QtGui.QLabel("Heart Beats Per Min")
		self.bpm_display_title.setFixedHeight(20)
		#Breaths Per Minute Display
		self.breathspermin_display = QtGui.QLCDNumber(self)
		self.breathspermin_display.display("--")
		self.breathspermin_display.setFixedWidth(200)
		self.breathspermin_display_title = QtGui.QLabel("Est. Breaths Per Minute")
		self.breathspermin_display_title.setFixedHeight(20)

		#Respiratory meters
		self.resp_plot = pg.PlotWidget(title="Breath Monitor")
		self.resp_plot.setXRange(-0.5,2.5)
		self.resp_plot.setYRange(0,200)
		self.resp_plot.hideAxis('left')
		self.rect1 = pg.BarGraphItem(x=[0,1,2],height=200,width=.2,brush='r')
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
		layout.addWidget(self.bpm_display_title,5,0)
		layout.addWidget(self.bpm_display,6,0)
		layout.addWidget(self.breathspermin_display_title,5,2)
		layout.addWidget(self.breathspermin_display,6,2)
		layout.addWidget(self.resp_plot,5,1,2,1)


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
		current_breathing_rate = data['current_breathing_rate']
		breathing_rate_array = data['breathing_rate_array']
		raw_rband = data['raw_rband']

		#Process for plotting:
		ibi_array = np.asarray(ibi_array)									#convert deque to array
		heart_rate_array = np.asarray(heart_rate_array)	 	#convert deque to array
		heart_rate_array = heart_rate_array/180.0					#turn bpm into a percentage of 180 (theoretical bpm maximum)
		heart_rate_array[0] = 10													#quick fix for plotting issues

		# Update plot
		self.ecg_curve.setData(x=self.ecg_scroll_time_axis,y=([point for point in ecg_data]))
		self.bpm_curve.setData(x=self.analysis_scroll_time_axis,y=([point for point in heart_rate_array]))
		self.ibi_curve.setData(x=self.analysis_scroll_time_axis,y=([point for point in ibi_array]))		
		# Update the breathing rate curves
		

		for i,chan in enumerate(breathing_rate_array):
			if np.mean(chan) == 0:
				self.breathing_curves[i].setVisible(False)
				# self.legend.removeItem("Breathing %s Rate" % i)
			elif np.mean!=0 and not self.BREATHING_LEGEND[i]:
				self.legend.addItem(self.breathing_curves[i], "Breathing {} Rate".format(i+1))
				self.BREATHING_LEGEND[i] = True
			else:
				chan = np.asarray(chan)
				chan = chan/40 	#turn breaths into a percentage of 120 (thearetical maximum)
				self.breathing_curves[i].setVisible(True)
				self.breathing_curves[i].setData(x=self.analysis_scroll_time_axis,y=([point for point in chan]))
			


		#update the breathing bands
		for i,ch in enumerate(raw_rband):
			if ch != 0:
				raw_rband[i] = ch - 400
		self.resp_plot.removeItem(self.rect1)
		self.rect1 = pg.BarGraphItem(x=[0,1,2],height=raw_rband,width=.2,brush='r')
		xdict = dict(enumerate(['Input 1','Input 2','Input 3']))
		axis = self.resp_plot.getAxis("bottom")
		axis.setTicks([xdict.items()])
		self.resp_plot.addItem(self.rect1)

		#Update Displays
		if current_bpm == 0:
			current_bpm = "--"
		self.bpm_display.display(current_bpm)
		
		sigma=0
		count=1
		for chan in current_breathing_rate:
			if chan!=0:
				sigma+=chan
				count+=1
		average_breathing_rate = sigma/count

		if average_breathing_rate == 0:
			average_breathing_rate = "--"
		self.breathspermin_display.display(average_breathing_rate)
		


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
		self.respiratory_analysis1 = Analysis()
		self.respiratory_analysis2 = Analysis()
		self.respiratory_analysis3 = Analysis()
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


			self.respiratory_analysis1.respiratory_analysis(self.rband_buf1)
			self.respiratory_analysis2.respiratory_analysis(self.rband_buf2)
			self.respiratory_analysis3.respiratory_analysis(self.rband_buf3)

			current_breathpermin = [
								self.respiratory_analysis1.current_breathpermin,
								self.respiratory_analysis2.current_breathpermin,
								self.respiratory_analysis3.current_breathpermin
			]

			breathing_rate_array = [
								self.respiratory_analysis1.breathing_rate_array,
								self.respiratory_analysis2.breathing_rate_array,
								self.respiratory_analysis3.breathing_rate_array
			]

			#pack data into dictionary
			data_to_plot = {
				'ecg_data' : ecg_display,
				'ibi_array' : self.analysis.ibi_display,
				'heart_rate_array' : self.analysis.heart_rate_array,
				'current_bpm' : self.analysis.current_bpm,
				'breathing_rate_array' : breathing_rate_array,
				'current_breathing_rate': current_breathpermin,
				'raw_rband' : raw_rband
			}
			self.new_data.emit(data_to_plot)

class Analysis:
	def __init__(self):
		self.last_beat = 0
		self.last_breath = 0
		self.number_of_beats = 15
		self.number_of_breaths = 7
		self.beat_buffer = deque([0]*self.number_of_beats)
		self.breath_buffer = deque([0]*self.number_of_breaths)
		self.ibi_array = deque([0]*500)
		self.ibi_display = deque([0]*15000)
		self.heart_rate_array = deque([0]*15000)
		self.breathing_rate_array = deque([0]*15000)
		self.current_bpm = 0
		self.current_breathpermin = 0
		self.BREATH = False



	def peak_detect(self,data_buf):
		peak_data = self.pan_tompkins(data_buf)
		self.peak_data = peak_data
		current_time = time.time()
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

		self.heart_rate_array.popleft()
		self.heart_rate_array.append(self.current_bpm)


		self.ibi_display.popleft()
		self.ibi_display.append(self.ibi_array[-1])


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
		return self.current_bpm

	def respiratory_analysis(self,resp_buf):
		resp_diff = np.diff(resp_buf)
		current_time = time.time()
		if (not self.BREATH and (resp_buf[-150] - resp_buf[-1]) < -10):
			self.last_breath = current_time
			self.breaths_per_minute()
			self.BREATH = True
		elif (self.BREATH and (resp_buf[-150] - resp_buf[-1]) > 10):
			self.BREATH = False
		self.breathing_rate_array.popleft()
		self.breathing_rate_array.append(self.current_breathpermin)


	def breaths_per_minute(self):
		self.breath_buffer.popleft()
		self.breath_buffer.append(self.last_breath)
		total_time = self.breath_buffer[-1] - self.breath_buffer[-2]
		bpm = (60/total_time)*2
		self.current_breathpermin = int(bpm)

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