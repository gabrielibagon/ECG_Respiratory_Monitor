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
np.set_printoptions(threshold=np.inf)


class GUI():
	def __init__(self, data_buffer, db, parent=None):
		self.app = QtGui.QApplication([])  		# new instance of QApplication
		super(self.__class__,self).__init__()

		self.streamer = lambda: streamer(buffer)
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
			
			main_widget = QtGui.QWidget(self)

			self.setCentralWidget(main_widget)

			layout = QtGui.QGridLayout()
			self.start_button = QtGui.QPushButton("Start Streaming")
			self.start_button.clicked.connect(db.run)
			layout.addWidget(self.start_button,0,0)
			



			self.ecg_scroll = pg.PlotWidget(title="ECG")
			self.ecg_scroll_time_axis = np.linspace(-5,0,824)							# the y axis of the scroll plot
			last_data_window = []												# saves last data for smoothing() function			
			self.ecg_scroll.setXRange(-5,-1, padding=.0001)
			self.ecg_scroll.setYRange(-200,200)
			# self.scroll.getAxis('left').setWidth(())
			self.ecg_scroll.setLabel('bottom','Time','Seconds')
			self.ecg_curve = self.ecg_scroll.plot()

			layout.addWidget(self.ecg_scroll,1,0,1,2)

			self.bpm_display = QtGui.QLCDNumber(self)
			layout.addWidget(self.bpm_display,2,0)

			self.hrv_scroll = pg.PlotWidget(title="Inter Beat Interval")
			self.hrv_scroll_time_axis = np.linspace(-5,0,10)
			self.hrv_scroll.setXRange(-5,-1,padding=0.0001)
			self.hrv_scroll.setYRange(0,1)
			self.hrv_curve = self.hrv_scroll.plot()
			layout.addWidget(self.hrv_scroll,2,1)

			main_widget.setLayout(layout)

		# SCROLL PLOT

		

	@pyqtSlot('PyQt_PyObject')
	def update_plot(self,data_to_plot,hrv_array,bpm):
		# print(data_to_plot[-3])
		# print(data_to_plot)
		self.window.ecg_curve.setData(x=self.window.ecg_scroll_time_axis,y=([point for point in data_to_plot[100:len(data_to_plot)-100]]))
		self.window.hrv_curve.setData(x=self.window.hrv_scroll_time_axis,y=([point for point in hrv_array]))
		self.window.bpm_display.display(bpm)
		self.app.processEvents()

class Data_Buffer(QThread):
	data_to_plot = []		
	new_data = pyqtSignal(object,object,object)


	def __init__(self, parent=None):
		QThread.__init__(self)
		self.display_size = 1024
		self.buffer_size = 1024
		self.data_buf = deque([0]*self.buffer_size)
		self.display_filters = filters.Filters(self.buffer_size,5,25)
		self.analyze_filters = filters.Filters(self.buffer_size,5,12)
		self.analysis = Analysis()
		self.count = 0
	
	'''
	Function: data_collect
	---------------------------------------------------------------
	Receives the data streaming in from the board and stores it in
	data_buffer. This buffer, once filled with new data, is sent to
	be filtered and then analyzed.
	'''
	def data_collect(self,sample):
		global new_data
		self.count+=1
		self.data_buf.popleft()
		self.data_buf.append(sample)
		if not self.count%20:
			display = self.display_filters.bandpass(self.data_buf)
			filtered = self.analyze_filters.bandpass(self.data_buf)
			analyzed = self.analysis.peak_detect(filtered)
			self.new_data.emit(display,np.array(self.analysis.hrv_array),self.analysis.current_bpm)


	def run(self):
		data_feed(self)

class Analysis:
	def __init__(self):
		self.last_beat = 0
		self.beat_buffer = deque([0])
		self.hrv_array = deque([0]*10)
		self.current_bpm = 0
		self.number_of_beats = 6

	def peak_detect(self,data_buf):
		'''
		1) 1st differential of the data_buffer (512 samples)
		2) square of that
		3) integrate -> integrate(data_buffer)
		4) take the pulse from that 
		'''
		heart = False
		order = 3
		diff = np.diff(data_buf,3)
		for i in range(order):
			diff = np.insert(diff,0,0)
		square = np.square(diff)
		window = 64
		integral = np.zeros((len(square)))
		for i in range(len(square)):
			integral[i] = np.trapz(square[i:i+window])
		print("-----------------------------------------------------")
		current_time = time.time()
		for i in range(50):
			if (current_time - self.last_beat >.300 and (integral[-(i+1)] - integral[-i]) > 10):
				print('BEEEEAAAAAATTTTTTTTTTTTT')
				time_dif = current_time - self.last_beat
				self.last_beat = current_time
				self.hrv_interval(time_dif)
				if (len(self.beat_buffer)<self.number_of_beats):
					self.beat_buffer.append(self.last_beat)
				else:
					self.beat_buffer.popleft()
					self.beat_buffer.append(self.last_beat)
					self.bpm(self.beat_buffer)
		

		# self.hrv_array.popleft()
		# self.hrv_array.append(self.hrv_array[-1])

		return integral

		
	def bpm(self,beat_buffer):
		total_time = beat_buffer[-1] - beat_buffer[0]
		bpm = (60/total_time)*self.number_of_beats
		self.current_bpm = int(bpm)
		return self.current_bpm

	def hrv_interval(self,time_dif):
		self.hrv_array.popleft()
		self.hrv_array.append(time_dif)





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
	GUI(data_feed,db)
	# data_feed(db)



if __name__ == '__main__':
	main()