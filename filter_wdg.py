# -*- coding: utf-8 -*-

"""
/***************************************************************************
Name			 	 : GEM Modellers Toolkit plugin (GEM-MT)
Description          : Analysing and Processing Earthquake Catalogue Data
Date                 : Jun 18, 2012 
copyright            : (C) 2012 by Giuseppe Sucameli (Faunalia)
email                : brush.tyler@gmail.com

 ***************************************************************************/

/***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 2 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""

from PyQt4.QtCore import *
from PyQt4.QtGui import *

from qgis.core import *
from qgis.gui import *

from utils import Utils

class FilterDock(QDockWidget):
	def __init__(self, iface, vl, parent=None):
		QDockWidget.__init__(self, parent)

		self.mainWidget = FilterWdg(iface, vl, self)
		self.setupUi()

	def deleteLater(self, *args):
		self.mainWidget.deleteLater()
		return QDockWidget.deleteLater(self, *args)

	def closeEvent(self, event):
		self.mainWidget.onClosing()
		self.emit( SIGNAL( "closed" ), self )
		return QDockWidget.closeEvent(self, event)

	def setupUi(self):
		self.setWindowTitle( "Filter/Plot panel" )
		self.setObjectName( "gem_mt_filter_dockwidget" )
		self.setWidget( self.mainWidget )


from ui.filterWdg_ui import Ui_FilterWdg
from MapTools import PolygonDrawer

class FilterWdg(QWidget, Ui_FilterWdg):

	PLOT_HIST, PLOT_HIST_LOG, PLOT_SCATTER = range(3)

	def __init__(self, iface, vl, parent=None):
		QWidget.__init__(self, parent)
		self.setupUi(self)

		# store the passed vars
		self.iface = iface
		self.vl = vl

		self.canvas = self.iface.mapCanvas()
		self._prevMapTool = None

		# setup the magnitude, depth and range filters
		self.setupFilters()

		# create the maptool to draw polygons
		self.polygonDrawer = PolygonDrawer( self.canvas, {'color':QColor("black"), 'enableSnap':False, 'keepAfterEnd':True} )
		self.polygonDrawer.setAction( self.drawPolygonBtn )
		self.connect(self.polygonDrawer, SIGNAL("geometryEmitted"), self.polygonCreated)

		# populate plot type combo
		self.plotTypeCombo.addItem( "Histogram", self.PLOT_HIST )
		self.plotTypeCombo.addItem( "Histogram (log10)", self.PLOT_HIST_LOG )
		self.plotTypeCombo.addItem( "Scatter plot", self.PLOT_SCATTER )
		self.updateAxesCombos()

		# populate both axis combos with field names
		for index, fld in self.vl.dataProvider().fields().iteritems():
			self.xAxisCombo.addItem( fld.name(), QVariant(index) )
			self.yAxisCombo.addItem( fld.name(), QVariant(index) )

		# connect actions to the widgets
		self.connect(self.drawPolygonBtn, SIGNAL("clicked()"), self.drawPolygon)
		self.connect(self.clearPolygonBtn, SIGNAL("clicked()"), self.clearPolygon)
		self.connect(self.plotBtn, SIGNAL("clicked()"), self.createPlot)
		self.connect(self.plotTypeCombo, SIGNAL("currentIndexChanged(int)"), self.updateAxesCombos)


	def storePrevMapTool(self):
		prevMapTool = self.canvas.mapTool()
		if prevMapTool not in (self.polygonDrawer,):
			self._prevMapTool = prevMapTool

	def restorePrevMapTool(self):
		self.polygonDrawer.stopCapture()
		if self._prevMapTool: 
			self.canvas.setMapTool(self._prevMapTool)


	def showEvent(self, event):
		self.showRubberBands(True)
		return QWidget.showEvent(self, event)

	def onClosing(self):
		self.showRubberBands(False)
		self.restorePrevMapTool()


	def deleteLater(self, *args):
		#print "deleting", self
		self.clearPolygon()

		# restore the previous maptool
		self.restorePrevMapTool()

		# delete the polygon drawer maptool
		self.polygonDrawer.deleteLater()
		self.polygonDrawer = None

		QWidget.deleteLater(self, *args)


	def _filterForKey(self, key):
		if key == 'magnitude': return self.magnitudeRangeFilter
		if key == 'depth': return self.depthRangeFilter
		if key == 'date': return self.dateRangeFilter
		return None

	def _hasPlotYField(self, plotType):
		return plotType not in (self.PLOT_HIST, self.PLOT_HIST_LOG)

	def _getPlotType(self):
		return self.plotTypeCombo.itemData( self.plotTypeCombo.currentIndex() )

	def updateAxesCombos(self):
		self.yAxisCombo.setEnabled( self._hasPlotYField( self._getPlotType() ) )


	def setupFilters(self):
		# setup the magnitude, depth and range filters
		self.magnitudeRangeFilter.setEnabled(False)
		self.magnitudeRangeFilter.setOrientation( Qt.Horizontal )
		self.magnitudeRangeFilter.setDecimals( 1 )
		self.magnitudeRangeFilter.setMinimum( 0 )
		self.magnitudeRangeFilter.setMaximum( 10 )

		self.depthRangeFilter.setEnabled(False)
		self.depthRangeFilter.setOrientation( Qt.Horizontal )
		self.depthRangeFilter.setMinimum( 0 )
		self.depthRangeFilter.setMaximum( 1000 )

		self.dateRangeFilter.setEnabled(False)
		self.dateRangeFilter.setOrientation( Qt.Horizontal )

		# take min/max values index from the data provider
		# let's reset the subset string to get real min/max
		pr = self.vl.dataProvider()
		pr.setSubsetString("")

		key2indexFieldMap = Utils.key2indexFieldMap( pr.fields() )
		for key, index in key2indexFieldMap.iteritems():
			filterWdg = self._filterForKey( key )
			if not filterWdg:
				continue

			minVal = pr.minimumValue( index )
			maxVal = pr.maximumValue( index )

			if minVal.isValid() and maxVal.isValid():
				# check for empty strings (the provider could be unable to retrieve values)
				if minVal.type() == QVariant.String and minVal.toString().isEmpty():
					minVal = None
				if maxVal.type() == QVariant.String and maxVal.toString().isEmpty():
					maxVal = None

				if minVal is None or maxVal is None:
					# let's search the real min/max values
					self.vl.select([index], QgsRectangle(), False)
					f = QgsFeature()
					while self.vl.nextFeature( f ):
						fval = f.attributeMap()[index]
						if not minVal or fval.toString() < minVal.toString():
							minVal = fval
						if not maxVal or fval.toString() > maxVal.toString():
							maxVal = fval

				# setup filter min/max range
				try:
					filterWdg.setMinimum( minVal )
					filterWdg.setLowValue( minVal )
					filterWdg.setMaximum( maxVal )
					filterWdg.setHighValue( maxVal )
				except:
					# unable to set min/max, skip the filter
					continue

				filterWdg.setEnabled(True)
				self.connect(filterWdg, SIGNAL("changeFinished"), self.updateMap)

		# filter default ranges
		self.magnitudeRangeFilter.setLowValue( 3.5 )
		self.magnitudeRangeFilter.setHighValue( 10 )
		self.depthRangeFilter.setLowValue( 0 )
		self.depthRangeFilter.setHighValue( 250 )

		self.updateMap()


	def updateMap(self, *args):
		pr = self.vl.dataProvider()
		key2indexFieldMap = Utils.key2indexFieldMap( pr.fields() )

		# convert filters to subset string
		subsets = []
		for key, index in key2indexFieldMap.iteritems():
			filterWdg = self._filterForKey( key )
			if not filterWdg or not filterWdg.isActive():
				continue

			name = pr.fields()[index].name()

			# define a new subset string when the low value is greather then the minimum value
			if filterWdg.lowValue() > filterWdg.minimum():
				minVal = QVariant(filterWdg.lowValue())
				if minVal.type() in (QVariant.Date, QVariant.DateTime):
					dataFormat = "yyyy/MM/dd" if self.vl.providerType() == 'ogr' else "yyyy-MM-dd"
					minVal = u"'%s'" % minVal.toDate().toString(dataFormat)
				else:
					minVal = minVal.toString()
				subsets.append( u"\"%s\" >= %s" % (name.replace('"', '""'), minVal) )

			# define a new subset string when the high value is less then the maximum value
			if filterWdg.highValue() < filterWdg.maximum():
				maxVal = QVariant(filterWdg.highValue())
				if maxVal.type() in (QVariant.Date, QVariant.DateTime):
					dataFormat = "yyyy/MM/dd" if self.vl.providerType() == 'ogr' else "yyyy-MM-dd"
					maxVal = u"'%s'" % maxVal.toDate().toString(dataFormat)
				else:
					maxVal = maxVal.toString()
				subsets.append( u"\"%s\" <= %s" % (name.replace('"', '""'), maxVal) )

		# set the subset string, then update the layer
		if self.vl.setSubsetString( u" AND ".join(subsets) ):
			self.vl.triggerRepaint()


	def showRubberBands(self, show=True):
		""" show/hide all the rubberbands """
		if self.polygonDrawer.isEmittingPoints:
			self.polygonDrawer.reset()
		else:
			self.polygonDrawer.rubberBand.show() if show else self.polygonDrawer.rubberBand.hide()

	def drawPolygon(self):
		# store the previous maptool
		self.storePrevMapTool()

		# set the polygon drawer as current maptool
		self.polygonDrawer.startCapture()

	def clearPolygon(self):
		# remove the displayed polygon
		self.polygonDrawer.reset()

	def polygonCreated(self, polygon):
		# restore the previous maptool
		self.restorePrevMapTool()

	def createPlot(self):
		QApplication.setOverrideCursor(QCursor(Qt.WaitCursor))
		try:
			dlg = self._createPlotDlg()
		finally:
			QApplication.restoreOverrideCursor()

		dlg.show()
		dlg.exec_()


	def _createPlotDlg(self):
		plotType = self._getPlotType()
		hasYField = self._hasPlotYField( plotType )

		# spatial filter
		spatialFilter = self.polygonDrawer.geometry()
		if not spatialFilter:
			extent = QgsRectangle()
		else:
			extent = spatialFilter.boundingBox()

		# get the indexes of fields selected in the combos
		xIndex = self.xAxisCombo.itemData( self.xAxisCombo.currentIndex() ).toInt()[0]
		yIndex = self.yAxisCombo.itemData( self.yAxisCombo.currentIndex() ).toInt()[0]

		pr = self.vl.dataProvider()
		index2keyFieldMap = Utils.index2keyFieldMap( pr.fields() )

		indexes = []
		for index, fld in pr.fields().iteritems():
			if index == xIndex:
				indexes.append( xIndex )
				continue

			if index == yIndex and hasYField:
				indexes.append( yIndex )
				continue

			filterWdg = self._filterForKey( Utils.fieldName2key( fld.name() ) )
			if filterWdg and filterWdg.isActive():
				indexes.append( index )


		# the following lists will contain x and y values
		x, y = ([], [])

		# fetch and loop through the features
		pr.select( indexes, extent, True )

		f = QgsFeature()
		while pr.nextFeature( f ):
			# filter features by spatial filter
			if spatialFilter and not spatialFilter.intersects( f.geometry() ):
				continue

			# filter features by attribute values
			attrs = f.attributeMap()

			ok = True
			for index, val in attrs.iteritems():
				if not index2keyFieldMap.has_key( index ):
					continue	# unused field

				filterWdg = self._filterForKey( index2keyFieldMap[ index ] )
				if not filterWdg:
					continue	# the field has no associated filter widget

				if filterWdg.isActive() and not filterWdg.checkValue( val ):
					ok = False
					break

			if not ok:	# the feature was filtered out
				continue

			# append feature values to the lists
			x.append( attrs[ xIndex ] )
			if hasYField: y.append( attrs[ yIndex ] )


		if len(x) <= 0:
			QMessageBox.information(self, "Plot", "No features in the result")
			return

		from plot_wdg import HistogramPlotDlg, ScatterPlotDlg
		if plotType == self.PLOT_HIST:
			dlg = HistogramPlotDlg([x], [self.xAxisCombo.currentText(), "Frequency"], self.titleEdit.text())
		elif plotType == self.PLOT_HIST_LOG:
			dlg = HistogramPlotDlg([x], [self.xAxisCombo.currentText(), "log10(Frequency)"], self.titleEdit.text(), {'yscale':'log'})
		elif plotType == self.PLOT_SCATTER:
			dlg = ScatterPlotDlg([x, y], [self.xAxisCombo.currentText(), self.yAxisCombo.currentText()], self.titleEdit.text())
		else:
			return

		#dlg.setParent(self.iface.mainWindow())
		return dlg

