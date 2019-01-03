import numpy as np 
import matplotlib.pyplot as plt 
import scipy.signal

#Perform phase correlation alignment
def get_window(N, window_type ="hamming"):
	if window_type == "hamming":
		#Symmetric window for filter design? But doing spectral analysis
		return scipy.signal.hamming(N,sym=False)
	elif window_type == "hann":
		return scipy.signal.hann(N,sym=False)

def correlation_align(signal_0,signal_1,upsampling=1.0):
	#Returns the shift (integer) which signal_1 must be moved to 
	#Align it with signal_0. Upsampling used to provide higher resolution.
	N = signal_0.shape[0]
	assert(signal_0.shape==signal_1.shape)

	if upsampling > 1.0:
		signal_0 = scipy.signal.resample(signal_0,int(np.round(N*upsampling)))
		signal_1 = scipy.signal.resample(signal_1,int(np.round(N*upsampling)))
		N = int(np.round(N*upsampling))

	xcorr = scipy.signal.correlate(signal_0,signal_1,mode="same", method="fft")
	full_precision_shift = shift = int(np.round(N/2.0))-np.argmax(xcorr)
	integer_shift = int(np.round(shift/float(upsampling)))
	return integer_shift,xcorr


def demo():
	N = 1014
	signal0 = np.zeros(N)
	signal0[300:500] = 1
	signal1 = np.zeros(N)
	signal1[350:550] = 1

	signal0 = signal0 + np.random.normal(0,0.1,N)
	signal1 = signal1 + np.random.normal(0,0.1,N)
	

	fig, axarr = plt.subplots(2)
	up = 4.0
	shift, xcorr = correlation_align(signal0,signal1,upsampling=up)
	
	xs = np.array(range(0,N))
	axarr[0].plot(xs,signal0,label="signal0")
	axarr[0].plot(xs,signal1,label="signal1")
	axarr[0].plot(xs-shift,signal1,label="signal1_shifted")
	axarr[0].legend()
	axarr[1].plot(xcorr)
	plt.show()

if __name__ == "__main__": 
	demo()
	

