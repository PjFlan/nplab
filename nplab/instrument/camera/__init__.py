# -*- coding: utf-8 -*-
"""
Created on Wed Jun 11 12:28:18 2014

@author: Richard Bowman
"""


import traits
from traits.api import HasTraits, Property, Instance, Float, String, Button, Bool, on_trait_change
import traitsui
from traitsui.api import View, Item, HGroup, VGroup
from traitsui.table_column import ObjectColumn
import chaco
from chaco.api import ArrayPlotData, Plot
from enable.component_editor import ComponentEditor
import threading
import numpy as np
import enable
import traceback
import os
import datetime
from PyQt4 import QtGui
from PIL import Image

from nplab.instrument import Instrument

class CameraParameter(HasTraits):
    value = Property(Float(np.NaN))
    name = String()

    def __init__(self,parent,name):
        self.parent = parent
        self.name=name

    def _get_value(self):
        """get the value of this parameter"""
        pass
    
    def _set_value(self, value):
        """get the value of this parameter"""
        pass
    
    def default_traits_view(self):
        return View(Item(name="value", label=self.name),kind="live")


class ImageClickTool(enable.api.BaseTool):
    """This handles clicks on the image and relays them to a callback function"""
    def __init__(self,plot):
        super(ImageClickTool, self).__init__()
        self.plot = plot
        
    def normal_left_up(self, event):
        """Handle a regular click on the image.
        
        This calls the callback function with two numbers between 0 and 1,
        corresponding to X and Y on the image.  Multiply by image size to get
        pixel coordinates."""
        if hasattr(self, "callback"):
            self.callback(1.-self.plot.y_axis.mapper.map_data(event.y),
                          self.plot.x_axis.mapper.map_data(event.x),)
        else:
            print "Clicked on image:", \
            self.plot.y_axis.mapper.map_data(event.y),\
            self.plot.x_axis.mapper.map_data(event.x)
          
          
class Camera(Instrument, HasTraits):
    latest_frame = traits.trait_numeric.Array(dtype=np.uint8,shape=(None, None, 3))
    image_plot = Instance(Plot)
    take_snapshot = Button
    save_jpg_snapshot = Button
    save_snapshot = Button
    edit_camera_properties = Button
    live_view = Bool
    parameters = traits.trait_types.List(trait=Instance(CameraParameter))
    filter_function = None
    
    old_traits_view = View(VGroup(
                    Item(name="image_plot",editor=ComponentEditor(),show_label=False,springy=True),
                    HGroup(
                        VGroup(
                            Item(name="take_snapshot",show_label=False),
                            Item(name="save_snapshot",show_label=False),
                            HGroup(Item(name="live_view")), #the hgroup is a trick to make the column narrower
                        springy=False),
                        Item(name="parameters",show_label=False,springy=True,
                             editor=traitsui.api.TableEditor(columns=
                                 [ObjectColumn(name="name", editable=False),
                                  ObjectColumn(name="value")])),
                    springy=True),
                layout="split"), kind="live",resizable=True,width=500,height=600,title="Camera")
                
    traits_view = View(VGroup(
                    Item(name="image_plot",editor=ComponentEditor(),show_label=False,springy=True),
                    VGroup(
                        HGroup(
                            Item(name="live_view"),
                            Item(name="take_snapshot",show_label=False),
                            Item(name="edit_camera_properties",show_label=False),
                        ),
                        HGroup(
                            Item(name="description"),
                            Item(name="save_snapshot",show_label=False),
                            Item(name="save_jpg_snapshot",show_label=False),
                        ), 
                        springy=False,
                    ),
                    layout="split"), kind="live",resizable=True,width=500,height=600,title="Camera")
                
    properties_view = View(VGroup( #used to edit camera properties
                        Item(name="parameters",show_label=False,springy=True,
                         editor=traitsui.api.TableEditor(columns=
                             [ObjectColumn(name="name", editable=False),
                              ObjectColumn(name="value")])),
                        ),
                        kind="live",resizable=True,width=500,height=600,title="Camera Properties"
                    )
                    
    def __init__(self):
        super(Camera,self).__init__()
        self._setup_plot()
        self.initialise_parameters()
        self.acquisition_lock = threading.Lock()        
        
    def __del__(self):
        self.close()
#        super(Camera,self).__del__() #apparently not...?
    def close(self):
        """Stop communication with the camera and allow it to be re-used.
        
        override in subclass if you want to shut down hardware."""
        self.live_view = False
        
    def _take_snapshot_fired(self): self.update_latest_frame()
    def update_latest_frame(self, frame=None):
        """Take a new frame and store it as the "latest frame".
        
        Returns the image as displayed, including filters, etc."""
        if frame is None: 
            frame = self.color_image()
        if frame is not None:
            if self.filter_function is not None:
                self.latest_frame=self.filter_function(frame)
            else:
                self.latest_frame=frame
            return self.latest_frame
        else:
            print "Failed to get an image from the camera"
    def _save_snapshot_fired(self):
        d=self.create_dataset('snapshot', data=self.update_latest_frame(), attrs=self.get_metadata())
        d.attrs.create('description',self.description)
        
    def _save_jpg_snapshot_fired(self):
        cur_img = self.update_latest_frame()
        fname = QtGui.QFileDialog.getSaveFileName(
                                caption = "Select Data File",
                                directory = os.path.join(os.getcwd(),datetime.date.today().strftime("%Y-%m-%d.jpg")),
                                filter = "Images (*.jpg *.jpeg)",
                            )
        j = Image.fromarray(cur_img)
        j.save(fname)
        
    def get_metadata(self):
        """Return a dictionary of camera settings."""
        ret = dict()
        for p in self.parameters:
            try:
                ret[p.name]=p.value
            except:
                pass #if there was a problem getting metadata, ignore it.
        return ret
    
    def _edit_camera_properties_fired(self):
        self.edit_traits(view="properties_view")
        
    def raw_snapshot(self):
        """Take a snapshot and return it.  No filtering or conversion."""
        return True, np.zeros((640,480,3),dtype=np.uint8)
    def color_image(self):
        """Get a colour image (bypass filtering, etc.)"""
        ret, frame = self.raw_snapshot()
        try:
            assert frame.shape[2]==3
            return frame
        except:
            try:
                assert len(frame.shape)==2
                return np.vstack((frame,)*3) #turn gray into color by duplicating!
            except:
                return None
    def gray_image(self):
        """Get a colour image (bypass filtering, etc.)"""
        ret, frame = self.raw_snapshot()
        try:
            assert len(frame.shape)==2
            return frame
        except:
            try:
                assert frame.shape[2]==3
                return np.mean(frame, axis=2, dtype=frame.dtype)
            except:
                return None
                
    def parameter_names(self):
        """Return a list of names of parameters that may be set."""
        return ['exposure','gain']
    
    def _latest_frame_changed(self):
        """Update the Chaco plot with the latest image."""
        try:
            self._image_plot_data.set_data("latest_frame",self.latest_frame)
            self.image_plot.aspect_ratio = float(self.latest_frame.shape[1])/float(self.latest_frame.shape[0])
        except Exception as e:
            print "Warning: exception occurred when updating the image graph:", e
            print "=========== Traceback ============"
            traceback.print_exc()
            print "============== End ==============="
    
    def initialise_parameters(self):
        """populate the list of camera settings that can be adjusted."""
        self.parameters = [CameraParameter(self, n) for n in self.parameter_names()]
        
    def _setup_plot(self):
        """Construct the Chaco plot used for displaying the image"""
        self._image_plot_data = ArrayPlotData(latest_frame=self.latest_frame,
                                              across=[0,1],middle=[0.5,0.5])
        self.image_plot = Plot(self._image_plot_data)
        self.image_plot.img_plot("latest_frame",origin="top left")
        self.image_plot.plot(("across","middle"),color="yellow") #crosshair
        self.image_plot.plot(("middle","across"),color="yellow")
        
        #remove the axes... there ought to be a neater way to do this!
        self.image_plot.underlays = [u for u in self.image_plot.underlays \
                                    if not isinstance(u, chaco.axis.PlotAxis)]
        self.image_plot.padding = 0 #fill the plot region with the image
        self.image_plot_tool = ImageClickTool(self.image_plot)
        self.image_plot.tools.append(self.image_plot_tool)

    def _live_view_changed(self):
        """Turn live view on and off"""
        if self.live_view==True:
            print "starting live view thread"
            try:
                self._live_view_stop_event = threading.Event()
                self._live_view_thread = threading.Thread(target=self._live_view_function)
                self._live_view_thread.start()
            except AttributeError as e: #if any of the attributes aren't there
                print "Error:", e
        else:
            print "stopping live view thread"
            try:
                self._live_view_stop_event.set()
                self._live_view_thread.join()
                del(self._live_view_stop_event, self._live_view_thread)
            except AttributeError:
                raise Exception("Tried to stop live view but it doesn't appear to be running!")
    def _live_view_function(self):
        """this function should only EVER be executed by _live_view_changed."""
        while not self._live_view_stop_event.wait(timeout=0.1):
            self.update_latest_frame()
        
