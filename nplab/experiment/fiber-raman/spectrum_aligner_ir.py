import numpy as np 
from scipy.interpolate import interp1d
import matplotlib.pyplot as plt 


def least_squares(xs,ys):
	xs_augmented = np.transpose([xs,np.ones(len(xs))])
	m,_,_,_ = np.linalg.lstsq(xs_augmented,ys)
	return m

def single_position_fit(spectra,calibration_wavelengths,center_wavelength = None,debug =0):
	'''
	spectra: spectra taken at same position (center wavelength) but with different incident laser wavelengths
	calibration_wavelengths - the wavelengths of the laser
	'''
	
	xs = peak_positions = [np.argmax(s) for s in spectra]
	ys = calibration_wavelengths

	#assuming that this is linear in the give pixel range
	[gradient, offset] = least_squares(xs,ys)
	if debug > 0:
		fig, ax = plt.subplots(1)
		ax.plot(xs,ys,'x',label="data")
		ax.plot(xs,gradient*np.array(xs) + offset,label="linear fit")
		ax.set_xlabel("Pixel index")
		ax.set_ylabel("Wavelength [nm]")
		ax.set_title("Pixel position vs Wavelength\n Center wavelength: {0}".format(center_wavelength))

		plt.show()
	return gradient, offset


def scan_fit(dataset,debug = 0):

	center_wls = []
	offsets = []
	gradients = []
	for (center_wavelength,spectra,calibration_wavelengths) in dataset:
		print center_wavelength,len(spectra),len(calibration_wavelengths)
		gradient, offset = single_position_fit(spectra,calibration_wavelengths,debug=debug,center_wavelength=center_wavelength)

		center_wls = center_wls + [center_wavelength]
		offsets = offsets + [offset]
		gradients = gradients + [gradient]

	if debug > 0:
		print "len(offsets)", len(offsets)
		print "len(gradients)", len(gradients)
		fig, [ax1,ax2] = plt.subplots(2)
		ax1.plot(center_wls,offsets,'x-')
		ax1.set_title("scan_fit: center wavelength vs wavelength offset (=$\lambda$ at pixel_index=0)")
		ax2.plot(center_wls,gradients,'x-')
		ax1.set_xlabel("Center wavelength [nm]")
		ax1.set_ylabel("Pixel 0 wavelength (offset) [nm]")
		ax2.set_title("scan_fit: center wavelength vs wavelength gradient (for determining wavelength for pixel_index > 0)")
		ax2.set_xlabel("Center wavelength [nm]")
		ax2.set_ylabel("Wavelength increment (gradient) [nm/pixel]")
		
		plt.show()

	def mapper(center_wavelength,pixel_index):
		wavelength_offset = interp1d(center_wls,offsets,kind='linear')
		wavelength_gradient = interp1d(center_wls,gradients,kind='linear')
		return wavelength_offset + wavelength_gradient*pixel_index

	return mapper


def test(debug):
	if debug:
		print "---TESTING---"

	pixels = np.arange(0,1014)
	def make_test_spectrum(mu,sigma=30.0):
		return np.exp(-(pixels-mu)**2/float(2*sigma**2))
	
	center_wavelengths=700
	calibration_wavelengths=[704,726,744]
	centers = [300,600,800]
	spectra = [make_test_spectrum(p) for p in centers]
	dset0 = [center_wavelengths,spectra,calibration_wavelengths]

	center_wavelengths=740
	calibration_wavelengths=[744,766,784]
	centers = [200,500,900]
	spectra = [make_test_spectrum(p) for p in centers]
	dset1 = [center_wavelengths,spectra,calibration_wavelengths]


	fig, ax = plt.subplots(1)
	for s in spectra:
		plt.plot(pixels,s)
	plt.show()

	dataset = [dset0,dset1]
	scan_fit(dataset,debug=1)

if __name__ == "__main__":
	test(debug=1)
	print "pass"