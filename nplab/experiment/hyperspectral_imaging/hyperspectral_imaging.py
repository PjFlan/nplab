__author__ = 'alansanders'

from nplab.experiment import Experiment
from nplab.experiment.gridscanner import GridScannerQT as GridScanner, GridScannerUI
from nplab.instrument.stage import Stage
from nplab.instrument.spectrometer import Spectrometer, Spectrometers
from nplab.instrument.light_sources import LightSource
import h5py
from nplab.datafile import DataFile
from nplab.utils.gui import *
from PyQt4 import uic
from nplab.ui.ui_tools import UiTools
import numpy as np
import matplotlib

matplotlib.use('Qt4Agg')
# from matplotlib.backends.backend_qt4agg import FigureCanvasQTAgg as FigureCanvas
from nplab.ui.mpl_gui import FigureCanvasWithDeferredDraw as FigureCanvas
from matplotlib.figure import Figure
from time import sleep
from functools import partial
from types import MethodType
import inspect
import nplab.datafile as datafile
from threading import RLock
from nplab.ui.hdf5_browser import HDF5Browser

# TODO: hyperspectral image renderer


class HyperspectralScanner(Experiment, GridScanner):
    view_layer_updated = QtCore.pyqtSignal(int)

    def __init__(self):
        super(HyperspectralScanner, self).__init__()
        self.spectrometer = None
        self.light_source = None
        self.num_spectrometers = 1
        self.estimated_step_time = 30e-3
        self.safe_exit = False
        self.delay = 0.

        self.f = datafile.current()
        self.scan = None
        self.data = None
        self.description = None

        self.fig = Figure()
        self.view_wavelength = 600
        self.view_layer = 0
        self.override_view_layer = False  # used to manually show a specific layer instead of current one scanning

        self.lock = RLock()
        self.request_data = False
        self.request_complete = False

    def __del__(self):
        if self.f is not None:
            self.f.close()

    @property
    def view_layer(self):
        return self._view_layer

    @view_layer.setter
    def view_layer(self, value):
        self._view_layer = value
        self.view_layer_updated.emit(value)

    def set_stage(self, stage, move_method=None, pos_method=None):
        assert isinstance(stage, Stage), 'stage must be an instance of Stage'
        self.scanner = stage
        # print self.move
        self.move = self.scanner.move
        # print self.move
        # self.scanner.configure()
        # move_method = get_move_method(self, self.scanner, self.stage_select)
        # setattr(self, move_method.__name__, MethodType(move_method, self))
        # position_method = get_position_method(self, self.scanner, self.stage_select)
        # setattr(self, position_method.__name__, MethodType(position_method, self))
        # # possibly requires third argument of self.__class__ or HyperspectralAcquisition
        self.set_init_to_current_position()

    def set_spectrometers(self, spectrometers):
        assert isinstance(spectrometers, Spectrometer) or isinstance(spectrometers, Spectrometers), \
            'spectrometer must be an instance of either Spectrometer or Spectrometers'
        self.spectrometer = spectrometers
        if hasattr(spectrometers, '__len__'):
            self.num_spectrometers = len(spectrometers)
        else:
            self.num_spectrometers = 1

    def set_light_source(self, light_source):
        assert isinstance(light_source, LightSource), 'light_source must be an instance of LightSource'
        self.light_source = light_source

    def open_scan(self):
        super(HyperspectralScanner, self).open_scan()

        print self.description
        self.scan = self.f.create_group('scan_%d', attrs=dict(description=self.description))
        for axis_name, axis_values in zip(self.axes_names, self.scan_axes):
            self.scan.create_dataset(axis_name, data=axis_values)
        self.wavelength = self.scan.create_dataset('wavelength', data=self.spectrometer.wavelengths)
        self.hsimg = self.scan.create_dataset('hs_image',
                                              shape=self.grid_shape + (self.spectrometer.wavelengths.size,),
                                              dtype=np.float64,
                                              attrs={}.update(self.spectrometer.metadata))

        self.fig.clear()

    def close_scan(self):
        super(HyperspectralScanner, self).close_scan()
        self.set_latest_view(self.spectrometer, 0)
        self.request_complete = True
        #self.f.close()
        sleep(0.1)
        if self.safe_exit:
            self.light_source.power = 0
            # self.scanner.close()

    def scan_function(self, *indices):
        sleep(self.delay)
        if self.num_spectrometers == 1:
            raw_spectrum = self.spectrometer.read_spectrum()
            spectrum = self.spectrometer.process_spectrum(raw_spectrum)
            # with self.lock:
            #print 'data thread:', self.f, self.scan
            # print self.hsimg
            self.hsimg[indices] = spectrum
            if self.request_data:
                self.set_latest_view(self.spectrometer, 0)
                self.request_data = False
                self.request_complete = True
        elif self.num_spectrometers > 1:
            pass

    def set_latest_view(self, spectrometer, data_id):
        w = abs(spectrometer.wavelengths - self.view_wavelength).argmin()
        suffix = str(data_id + 1) if data_id != 0 else ''
        # with self.lock:
        #print 'display thread:', self.f, self.scan
        data = self.scan['hs_image' + suffix]
        if self.num_axes == 2:
            latest_view = data[:, :, w]
        elif self.num_axes == 3:
            if self.override_view_layer:
                k = self.view_layer
            else:
                k = self.indices[-1]
                if self.view_layer != k:
                    self.view_layer = k
            latest_view = data[:, :, k, w]
        data = latest_view.transpose()
        self.set_latest_data(data)
        return data

    def update_axis_image(self, ax, spectrometer, data_id):
        if not self.request_complete:
            self.request_data = True
            return
        self.request_complete = False
        data = self.check_for_data()
        #data = self.set_latest_view(spectrometer, data_id)
        if data:
            data, = data
            if not np.any(np.isfinite(data)):
                return
            if not ax.collections:
                mult = 1. / self._unit_conversion[self.size_unit]
                ax.pcolormesh(mult * self.scan_axes[0], mult * self.scan_axes[1], data,
                              cmap=matplotlib.cm.afmhot)
                cid = self.fig.canvas.mpl_connect('button_press_event', self.onclick)
                cid = self.fig.canvas.mpl_connect('pick_event', self.onpick4)
            else:
                img, = ax.collections
                img.set_array(data[:-1, :-1].ravel())
                img_min = data[np.isfinite(data)].min()
                img_max = data[np.isfinite(data)].max()
                img.set_clim(img_min, img_max)
                ax.relim()
                ax.draw_artist(ax.patch)
                ax.draw_artist(img)
            return True
        else:
            return False

    def update(self):
        if self.fig.canvas is None:
            return
        if self.num_spectrometers == 1:
            if not self.fig.axes:
                self.ax = self.fig.add_subplot(111)
                self.ax.set_aspect('equal')
                mult = 1. / self._unit_conversion[self.size_unit]
                x, y = (mult * self.scan_axes[0], mult * self.scan_axes[1])
                self.ax.set_xlim(x.min(), x.max())
                self.ax.set_ylim(y.min(), y.max())
                self.fig.canvas.draw()
            if not self.update_axis_image(self.ax, self.spectrometer, 0):
                return
        elif self.num_spectrometers > 1:
            n = len(self.spectrometer)
            for i in range(n):
                if not self.fig.axes or len(self.fig.axes) != n:
                    self.ax = self.fig.add_subplot(n, 1, i + 1)
                    self.ax.set_aspect('equal')
                    mult = 1. / self._unit_conversion[self.size_unit]
                    x, y = (mult * self.scan_axes[0], mult * self.scan_axes[1])
                    self.ax.set_xlim(x.min(), x.max())
                    self.ax.set_ylim(y.min(), y.max())
                    self.fig.canvas.draw()
                if not self.update_axis_image(self.ax, self.spectrometer[i], i):
                    return

        if self.fig.canvas is not None:
            self.fig.canvas.update()
            self.fig.canvas.flush_events()
            #self.fig.canvas.draw()
            #self.fig.canvas.draw_in_main_loop()
            QtCore.QCoreApplication.processEvents()

    def get_qt_ui(self):
        return HyperspectralScannerUI(self)

    def start(self, rate=1./30.):
        super(HyperspectralScanner, self).start(rate)

    def onclick(self, event):
        init_scale = self._unit_conversion[self.size_unit] / self._unit_conversion[self.init_unit]
        self.init[:2] = (event.xdata * init_scale, event.ydata * init_scale)
        self.init_updated.emit(self.init)

    def onpick4(self, event):
        artist = event.artist
        if isinstance(artist, matplotlib.image.AxesImage):
            im = artist
            A = im.get_array()
            print 'onpick4 image', A.shape

    def update_estimated_step_time(self):
        max_exposure = 1e-3 * max([s.integration_time for s in self.spectrometers.spectrometers])
        max_travel = 100e-3
        self.estimated_step_time = max_exposure + max_travel


class HyperspectralScannerUI(QtGui.QWidget, UiTools):
    def __init__(self, grid_scanner, parent=None):
        assert isinstance(grid_scanner, HyperspectralScanner), \
            'scanner must be an instance of HyperspectralScanner'
        super(HyperspectralScannerUI, self).__init__()
        self.grid_scanner = grid_scanner
        uic.loadUi(os.path.join(os.path.dirname(__file__), 'hyperspectral_imaging.ui'), self)
        self.gridscanner_widget = self.replace_widget(self.main_layout, self.gridscanner_widget,
                                                      GridScannerUI(self.grid_scanner))
        self.figure_widget = self.replace_widget(self.main_layout, self.figure_widget,
                                                 FigureCanvas(self.grid_scanner.fig))
        self.init_stage_select()
        self.init_view_wavelength_controls()
        self.init_view_select()

        self.scan_description.textChanged.connect(self.update_param)

        self.config_stage.clicked.connect(self.on_click)
        self.config_spectrometers.clicked.connect(self.on_click)
        self.config_light_source.clicked.connect(self.on_click)
        self.open_browser.clicked.connect(self.on_click)

    def init_stage_select(self):
        self.stage_select.addItems(['PI', 'SmarAct'])
        self.stage_select.activated[str].connect(self.select_stage)

    def init_view_wavelength_controls(self):
        self.view_wavelength.setValidator(QtGui.QIntValidator())
        # self.view_wavelength.textChanged.connect(self.check_state)
        self.view_wavelength.returnPressed.connect(self.on_view_wavelength_change)

        self.wavelength_range.setRange(400, 1100)
        self.wavelength_range.setFocusPolicy(QtCore.Qt.NoFocus)
        self.wavelength_range.valueChanged[int].connect(self.on_wavelength_range_change)

        self.view_wavelength.setText(str(self.grid_scanner.view_wavelength))
        self.wavelength_range.setValue(self.grid_scanner.view_wavelength)

    def init_view_select(self):
        self.view_layer.setValidator(QtGui.QIntValidator())
        self.view_layer.textChanged.connect(
            self.on_view_layer_change)  # (partial(setattr, self.grid_scanner, 'view_layer'))
        self.grid_scanner.view_layer_updated.connect(self.on_gs_view_layer_change)

        self.override_view_layer.stateChanged.connect(self.on_override_view_layer)

    def update_param(self, *args, **kwargs):
        sender = self.sender()
        if sender == self.scan_description:
            self.grid_scanner.description = self.scan_description.toPlainText().encode('utf8')

    def select_stage(self, name):
        print name

    def on_click(self):
        sender = self.sender()
        if sender == self.config_stage:
            self.scanner_ui = self.grid_scanner.scanner.get_qt_ui()
            self.scanner_ui.show()
        elif sender == self.config_spectrometers:
            self.spectrometers_ui = self.grid_scanner.spectrometer.get_qt_ui()
            self.spectrometers_ui.show()
        elif sender == self.config_light_source:
            #self.light_source_ui = self.grid_scanner.light_source.get_qt_ui()
            #self.light_source_ui.show()
            pass
        elif sender == self.open_browser:
            if self.grid_scanner.f is not None:
                print self.grid_scanner.f
                self.browser = HDF5Browser(self.grid_scanner.f)
                self.browser.show()

    def on_view_wavelength_change(self, *args, **kwargs):
        """
        This function is called by the power text box.
        :param args:
        :param kwargs:
        :return:
        """
        print self.view_wavelength.text()
        value = int(self.view_wavelength.text())
        # self.wavelength_range.valueChanged[int].emit(value)
        self.wavelength_range.setValue(value)

    def on_wavelength_range_change(self, value):
        """
        This function is called by the power slider.
        :param value:
        :return:
        """
        self.grid_scanner.view_wavelength = value
        self.view_wavelength.setText('%d' % value)

    def on_view_layer_change(self, *args, **kwargs):
        self.grid_scanner.view_layer = int(self.view_layer.text())

    def on_gs_view_layer_change(self, value):
        self.view_layer.setText(str(value))

    def on_override_view_layer(self, state):
        if state == QtCore.Qt.Checked:
            self.grid_scanner.override_view_layer = True
        else:
            self.grid_scanner.override_view_layer = False


if __name__ == '__main__':
    import sys
    from nplab.instrument.stage import DummyStage
    from nplab.instrument.spectrometer import DummySpectrometer

    f = datafile.DataFile('/Users/alansanders/Desktop/hsi_test.h5', 'w')
    f.make_current()

    stage = DummyStage()
    stage.axis_names = ('x', 'y', 'z')

    gs = HyperspectralScanner()
    gs.set_stage(stage)
    gs.set_spectrometers(DummySpectrometer())
    app = get_qt_app()
    gui = gs.get_qt_ui()
    gui.show()
    sys.exit(app.exec_())