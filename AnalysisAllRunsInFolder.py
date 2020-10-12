#!/usr/bin/env python
import numpy as np
from struct import unpack
import time, os, sys
from optparse import OptionParser
import ipdb
import cPickle as pickle
from Utils import *
from Settings_Caen import Settings_Caen
from Converter_Caen import Converter_Caen
import subprocess as subp
from AnalysisCaenCCD import AnalysisCaenCCD
import ROOT as ro

fit_method = ('Minuit2', 'Migrad', )

class AnalysisAllRunsInFolder:
	def __init__(self, runsdir='', config='', configinput='', overwrite=False):
		self.time0 = time.time()
		self.runsdir = Correct_Path(runsdir)
		self.config = Correct_Path(config)
		self.configInput = Correct_Path(configinput) if configinput != '' else ''
		self.overwrite = overwrite
		self.are_cal_runs = False if self.configInput == '' else True # this is only true for signal calibration runs
		runstemp = glob.glob('{d}/*'.format(d=self.runsdir))
		if len(runstemp) < 1:
			ExitMessage('The directory does not have any runs', os.EX_USAGE)
		# self.num_cores = 1
		self.runs = [runi for runi in runstemp if os.path.isdir(runi)]
		if self.are_cal_runs:
			self.runs.sort(key=lambda x: float(x.split('_')[-1].split('mV')[0].split('V')[0]))
		else:
			self.runs.sort(key=lambda x: float(x.split('_Pos_')[-1].split('V')[0]) if 'Pos' in x else -1*float(x.split('_Neg_')[-1].split('V')[0]))
		self.num_runs = len(self.runs)
		if self.num_runs < 1: ExitMessage('There is not even the required data to convert one run', os.EX_DATAERR)
		self.voltages = []
		self.diaVoltages = {}
		self.diaVoltagesSigma = {}
		self.signalOut = {}
		self.signalOutSigma = {}
		self.signalOutVcal = {}
		self.signalOutVcalSigma = {}
		self.signalOutCharge = {}
		self.signalOutChargeSigma = {}
		self.signalOutCF = {}
		self.signalOutSigmaCF = {}
		self.signalOutVcalCF = {}
		self.signalOutVcalSigmaCF = {}
		self.signalOutChargeCF = {}
		self.signalOutChargeSigmaCF = {}
		self.signalIn = {}
		self.signalInSigma = {}
		self.signalPeakTime = {}
		self.signalPeakTimeSigma = {}
		self.signalPeakTimeCF = {}
		self.signalPeakTimeSigmaCF = {}
		self.caen_ch = 3
		self.graph = ro.TGraphErrors()
		self.graphVcal = ro.TGraphErrors()
		self.graphCharge = ro.TGraphErrors()
		self.graphPeakTime = ro.TGraphErrors()
		self.graphCF = ro.TGraphErrors()
		self.graphVcalCF = ro.TGraphErrors()
		self.graphChargeCF = ro.TGraphErrors()
		self.graphPeakTimeCF = ro.TGraphErrors()
		self.canvas = None
		self.canvasVcal = None
		self.canvasCharge = None
		self.canvasPeakTime = None
		self.canvasCF = None
		self.canvasVcalCF = None
		self.canvasChargeCF = None
		self.canvasPeakTimeCF = None
		self.fit = None
		self.cal_pickle = None
		self.LoadPickle()

	def LoadPickle(self):
		cal_files = glob.glob('{d}/signal_*.cal'.format(d=self.runsdir))
		if len(cal_files) > 0:
			self.cal_pickle = pickle.load(open(cal_files[0], 'rb'))
			self.voltages = self.cal_pickle['voltages']
			self.signalIn = self.cal_pickle['signal_in']
			self.signalInSigma = self.cal_pickle['signal_in_sigma']
			self.signalOut = self.cal_pickle['signal_out']
			self.signalOutSigma = self.cal_pickle['signal_out_sigma']
			self.caen_ch = self.cal_pickle['caen_ch']
			nameVcal = ''
			nameCharge = ''
			namePeakTime = ''
			if 'signal_out_vcal' in self.cal_pickle.keys():
				self.signalOutVcal = self.cal_pickle['signal_out_vcal']
				self.signalOutVcalSigma = self.cal_pickle['signal_out_vcal_sigma']
				nameVcal = '' if self.are_cal_runs else 'SignalVcal_vs_HV'
			if 'signal_out_charge' in self.cal_pickle.keys():
				self.signalOutCharge = self.cal_pickle['signal_out_charge']
				self.signalOutChargeSigma = self.cal_pickle['signal_out_charge_sigma']
				nameCharge = '' if self.are_cal_runs else 'SignalCharge_vs_HV'
			if 'signal_peak_time' in self.cal_pickle.keys():
				self.signalPeakTime = self.cal_pickle['signal_peak_time']
				self.signalPeakTimeSigma = self.cal_pickle['signal_peak_time_sigma']
				namePeakTime = 'SignalPeakTime_vs_Signal_ch_' + str(self.caen_ch) if self.are_cal_runs else ''
			name = 'Signal_vs_CalStep_ch_' + str(self.caen_ch) if self.are_cal_runs else 'Signal_vs_HV'
			xpoints = np.array([self.signalIn[volt] for volt in self.voltages], 'f8') if len(self.signalIn.keys()) >= 1 else np.array(self.voltages, 'f8')
			xpointserrs = np.array([self.signalInSigma[volt] for volt in self.voltages], 'f8') if len(self.signalInSigma.keys()) >= 1 else np.zeros(len(self.voltages), 'f8')
			self.graph = ro.TGraphErrors(len(self.voltages), xpoints, np.array([self.signalOut[volt] for volt in self.voltages], 'f8'), xpointserrs, np.array([self.signalOutSigma[volt] for volt in self.voltages], 'f8'))
			self.graph.SetNameTitle(name, name)
			self.graph.GetXaxis().SetTitle('vcal step [mV]' if self.are_cal_runs else 'HV [V]')
			self.graph.GetYaxis().SetTitle('signal [mV]')
			self.graph.SetMarkerStyle(7)
			self.graph.SetMarkerColor(ro.kBlack)
			self.graph.SetLineColor(ro.kBlack)
			if self.are_cal_runs:
				self.fit = ro.TF1('fit_' + name, 'pol1', -1000, 1000)
				self.fit.SetLineColor(ro.kRed)
				self.fit.SetNpx(10000)
				self.fit.SetParameters(np.array([self.cal_pickle['fit_p0'], self.cal_pickle['fit_p1']], 'f8'))
				self.fit.SetParErrors(np.array([self.cal_pickle['fit_p0_error'], self.cal_pickle['fit_p1_error']], 'f8'))
				self.fit.SetNDF(self.cal_pickle['fit_ndf'])
				self.fit.SetChisquare(self.cal_pickle['fit_chi2'])
				if namePeakTime != '':
					self.graphPeakTime = ro.TGraphErrors(len(self.signalPeakTime.values()), np.array([self.signalOut[volt] for volt in self.voltages], 'f8'), np.array([self.signalPeakTime[volt] for volt in self.voltages], 'f8'), np.array([self.signalOutSigma[volt] for volt in self.voltages], 'f8'), np.array([self.signalPeakTimeSigma[volt] for volt in self.voltages], 'f8'))
					self.graphPeakTime.SetNameTitle(namePeakTime, namePeakTime)
					self.graphPeakTime.GetXaxis().SetTitle('signal [mV]')
					self.graphPeakTime.GetYaxis().SetTitle('Peak Time [us]')
					self.graphPeakTime.SetMarkerStyle(7)
					self.graphPeakTime.SetMarkerColor(ro.kBlack)
					self.graphPeakTime.SetLineColor(ro.kBlack)
			else:
				if nameVcal != '':
					self.graphVcal = ro.TGraphErrors(len(self.voltages), xpoints, np.array([self.signalOutVcal[volt] for volt in self.voltages], 'f8'), xpointserrs, np.array([self.signalOutVcalSigma[volt] for volt in self.voltages], 'f8'))
					self.graphVcal.SetNameTitle(nameVcal, nameVcal)
					self.graphVcal.GetXaxis().SetTitle('HV [V]')
					self.graphVcal.GetYaxis().SetTitle('signalVcal [mV]')
					self.graphVcal.SetMarkerStyle(7)
					self.graphVcal.SetMarkerColor(ro.kBlack)
					self.graphVcal.SetLineColor(ro.kBlack)
				if nameCharge != '':
					self.graphCharge = ro.TGraphErrors(len(self.voltages), xpoints, np.array([self.signalOutCharge[volt] for volt in self.voltages], 'f8'), xpointserrs, np.array([self.signalOutChargeSigma[volt] for volt in self.voltages], 'f8'))
					self.graphCharge.SetNameTitle(nameVcal, nameVcal)
					self.graphCharge.GetXaxis().SetTitle('HV [V]')
					self.graphCharge.GetYaxis().SetTitle('signalCharge [e]')
					self.graphCharge.SetMarkerStyle(7)
					self.graphCharge.SetMarkerColor(ro.kBlack)
					self.graphCharge.SetLineColor(ro.kBlack)
				self.fit = None
			print 'Loaded pickle', cal_files[0]
			return
		print 'There is no pickle to load yet (or it is not a calibration run)'

	def PlotFromPickle(self):
		if self.cal_pickle:
			if self.graph:
				self.canvas = ro.TCanvas('c_' + self.graph.GetName(), 'c_' + self.graph.GetName(), 1)
				self.graph.Draw('AP')
			if self.fit:
				self.fit.Draw('same')
			if self.graphVcal:
				self.canvasVcal = ro.TCanvas('c_' + self.graphVcal.GetName(), 'c_' + self.graphVcal.GetName(), 1)
				self.graphVcal.Draw('AP')
			if self.graphCharge:
				self.canvasCharge = ro.TCanvas('c_' + self.graphCharge.GetName(), 'c_' + self.graphCharge.GetName(), 1)
				self.graphCharge.Draw('AP')

	def DoAll(self, updateHistos=False):
		self.time0 = time.time()
		if not self.cal_pickle or self.overwrite or updateHistos:
			self.LoopRuns()
		self.PlotSignals()
		if self.are_cal_runs:
			self.FitLine()
			self.FillPickle()
			self.SavePickle()
			self.PlotPeakTimes()
		self.SaveCanvas()
		print 'Finished in', time.time() - self.time0, 'seconds'

	def LoopRuns(self):
		# ro.gROOT.SetBatch(True)
		for run in self.runs:
			print 'Analysing run:', run
			if os.path.isdir(run):
				root_files = glob.glob('{d}/*.root'.format(d=run))
				if len(root_files) > 0:
					configfile = self.config if not self.are_cal_runs or '_out_' in run else self.configInput
					print 'Using config file:', configfile
					print 'Overwriting analysis tree if it exists' if self.overwrite else 'Not overwriting analysis tree if it exists'
					anaRun = AnalysisCaenCCD(run, configfile, overw=self.overwrite)
					anaRun.AnalysisWaves()
					anaRun.AddVcalFriend(self.overwrite, False)
					anaRun.AddVcalFriend(self.overwrite, True)
					anaRun.AddChargeFriend(self.overwrite, False)
					anaRun.AddChargeFriend(self.overwrite, True)
					self.voltages.append(anaRun.bias)
					self.caen_ch = anaRun.ch_caen_signal if self.caen_ch != anaRun.ch_caen_signal else self.caen_ch
					anaRun.PlotPedestal('Pedestal', cuts=anaRun.cut0.GetTitle(), branch='pedestal')
					anaRun.PlotPedestal('PedestalCF', cuts=anaRun.cut0CF.GetTitle(), branch='pedestalCF')
					if not anaRun.is_cal_run:
						anaRun.PlotPedestal('PedestalVcal', cuts=anaRun.cut0.GetTitle(), branch='pedestalVcal')
						anaRun.PlotPedestal('PedestalVcalCF', cuts=anaRun.cut0CF.GetTitle(), branch='pedestalVcalCF')
						anaRun.PlotPedestal('PedestalCharge', cuts=anaRun.cut0.GetTitle(), branch='pedestalCharge')
						anaRun.PlotPedestal('PedestalChargeCF', cuts=anaRun.cut0CF.GetTitle(), branch='pedestalChargeCF')
					anaRun.PlotWaveforms('SelectedWaveforms', 'signal', cuts=anaRun.cut0.GetTitle(), do_logz=True, do_cf=False)
					anaRun.PlotWaveforms('SelectedWaveformsCF', 'signal', cuts=anaRun.cut0CF.GetTitle(), do_logz=True, do_cf=True)
					# if 'SelectedWaveforms' in anaRun.canvas.keys():
					# 	anaRun.canvas['SelectedWaveforms'].SetLogz()
					anaRun.PlotWaveforms('SelectedWaveformsPedCor', 'signal_ped_corrected', cuts=anaRun.cut0.GetTitle(), do_logz=True, do_cf=False)
					anaRun.PlotWaveforms('SelectedWaveformsPedCorCF', 'signal_ped_corrected', cuts=anaRun.cut0CF.GetTitle(), do_logz=True, do_cf=True)
					# if 'SelectedWaveformsPedCor' in anaRun.canvas.keys():
					# 	anaRun.canvas['SelectedWaveformsPedCor'].SetLogz()
					anaRun.PlotSignal('PH', cuts=anaRun.cut0.GetTitle(), branch='signal')
					anaRun.PlotSignal('PH_CF', cuts=anaRun.cut0CF.GetTitle(), branch='signalCF')
					if not anaRun.is_cal_run:
						anaRun.FitLanGaus('PH')
						anaRun.FitLanGaus('PH_CF')
						anaRun.PlotSignal('PHvcal', cuts=anaRun.cut0.GetTitle(), branch='signalVcal')
						anaRun.PlotSignal('PHvcal_CF', cuts=anaRun.cut0CF.GetTitle(), branch='signalVcalCF')
						anaRun.FitLanGaus('PHvcal')
						anaRun.FitLanGaus('PHvcal_CF')
						anaRun.PlotSignal('PHcharge', cuts=anaRun.cut0.GetTitle(), branch='signalCharge')
						anaRun.PlotSignal('PHcharge_CF', cuts=anaRun.cut0CF.GetTitle(), branch='signalChargeCF')
						anaRun.FitLanGaus('PHcharge')
						anaRun.FitLanGaus('PHcharge_CF')
						phPpos, phGsigma = max(anaRun.histo['PH'].GetBinLowEdge(anaRun.histo['PH'].GetMaximumBin()), anaRun.langaus['PH'].fit.GetMaximumX()), anaRun.langaus['PH'].fit.GetParameter(3)
						if phPpos > 10:
							minx, maxx = -10, max(max(TruncateFloat(phPpos / 4., 10), 40), phPpos - 3.5 * phGsigma)
							binsx = RoundInt((maxx - minx) / 2.)
							anaRun.PlotSignal('PHPedestal', binsx, cuts=anaRun.cut0.GetTitle(), branch='signal', minx=minx, maxx=maxx, optimizeBinning=False)
							histocName = anaRun.RemovePedestalFromSignal('PH', 'PHPedestal', anaRun.pedestal_sigma, xmax=max(TruncateFloat(phPpos / 4., 10), TruncateFloat(phPpos - 3.5 * phGsigma, 10)))
							anaRun.FitLanGaus(histocName)
						phvcalPpos, phvcalGsigma = max(anaRun.histo['PHvcal'].GetBinLowEdge(anaRun.histo['PHvcal'].GetMaximumBin()), anaRun.langaus['PHvcal'].fit.GetMaximumX()), anaRun.langaus['PHvcal'].fit.GetParameter(3)
						if phvcalPpos > 10:
							minx, maxx = -10, max(max(TruncateFloat(phvcalPpos / 4., 10), 40), phvcalPpos - 3.5 * phvcalGsigma)
							binsx = RoundInt((maxx - minx) / 2.)
							anaRun.PlotSignal('PHvcalPedestal', binsx, cuts=anaRun.cut0.GetTitle(), branch='signalVcal', minx=minx, maxx=maxx, optimizeBinning=False)
							histocName = anaRun.RemovePedestalFromSignal('PHvcal', 'PHvcalPedestal', anaRun.pedestal_vcal_sigma, xmax=max(TruncateFloat(phvcalPpos / 4., 10), TruncateFloat(phvcalPpos - 3.5 * phvcalGsigma, 10)))
							anaRun.FitLanGaus(histocName)
						phchPpos, phchGsigma = max(anaRun.histo['PHcharge'].GetBinLowEdge(anaRun.histo['PHcharge'].GetMaximumBin()), anaRun.langaus['PHcharge'].fit.GetMaximumX()), anaRun.langaus['PHcharge'].fit.GetParameter(3)
						if phchPpos > 1200:
							minx, maxx = -10, max(max(TruncateFloat(phvcalPpos / 4., 10), 40), phvcalPpos - 3.5 * phvcalGsigma)
							binsx = RoundInt((maxx - minx) / 2.)
							anaRun.PlotSignal('PHchargePedestal', binsx, cuts=anaRun.cut0.GetTitle(), branch='signalCharge', minx=minx, maxx=maxx, optimizeBinning=False)
							histocName = anaRun.RemovePedestalFromSignal('PHcharge', 'PHchargePedestal', anaRun.pedestal_charge_sigma, xmax=max(TruncateFloat(phchPpos / 4., 1000), TruncateFloat(phchPpos - 3.5 * phchGsigma, 1000)))
							anaRun.FitLanGaus(histocName)

						phPpos, phGsigma = max(anaRun.histo['PH_CF'].GetBinLowEdge(anaRun.histo['PH_CF'].GetMaximumBin()), anaRun.langaus['PH_CF'].fit.GetMaximumX()), anaRun.langaus['PH_CF'].fit.GetParameter(3)
						if phPpos > 10:
							minx, maxx = -10, max(max(TruncateFloat(phPpos / 4., 10), 40), phPpos - 3.5 * phGsigma)
							binsx = RoundInt((maxx - minx) / 2.)
							anaRun.PlotSignal('PHPedestal_CF', binsx, cuts=anaRun.cut0CF.GetTitle(), branch='signalCF', minx=minx, maxx=maxx, optimizeBinning=False)
							histocName = anaRun.RemovePedestalFromSignal('PH_CF', 'PHPedestal_CF', anaRun.pedestal_sigmaCF, xmax=max(TruncateFloat(phPpos / 4., 10), TruncateFloat(phPpos - 3.5 * phGsigma, 10)))
							anaRun.FitLanGaus(histocName)
						phvcalPpos, phvcalGsigma = max(anaRun.histo['PHvcal_CF'].GetBinLowEdge(anaRun.histo['PHvcal_CF'].GetMaximumBin()), anaRun.langaus['PHvcal_CF'].fit.GetMaximumX()), anaRun.langaus['PHvcal_CF'].fit.GetParameter(3)
						if phvcalPpos > 10:
							minx, maxx = -10, max(max(TruncateFloat(phvcalPpos / 4., 10), 40), phvcalPpos - 3.5 * phvcalGsigma)
							binsx = RoundInt((maxx - minx) / 2.)
							anaRun.PlotSignal('PHvcalPedestal_CF', binsx, cuts=anaRun.cut0CF.GetTitle(), branch='signalVcalCF', minx=minx, maxx=maxx, optimizeBinning=False)
							histocName = anaRun.RemovePedestalFromSignal('PHvcal_CF', 'PHvcalPedestal_CF', anaRun.pedestal_vcal_sigmaCF, xmax=max(TruncateFloat(phvcalPpos / 4., 10), TruncateFloat(phvcalPpos - 3.5 * phvcalGsigma, 10)))
							anaRun.FitLanGaus(histocName)
						phchPpos, phchGsigma = max(anaRun.histo['PHcharge_CF'].GetBinLowEdge(anaRun.histo['PHcharge_CF'].GetMaximumBin()), anaRun.langaus['PHcharge_CF'].fit.GetMaximumX()), anaRun.langaus['PHcharge_CF'].fit.GetParameter(3)
						if phchPpos > 1200:
							minx, maxx = -10, max(max(TruncateFloat(phvcalPpos / 4., 10), 40), phvcalPpos - 3.5 * phvcalGsigma)
							binsx = RoundInt((maxx - minx) / 2.)
							anaRun.PlotSignal('PHchargePedestal_CF', binsx, cuts=anaRun.cut0CF.GetTitle(), branch='signalChargeCF', minx=minx, maxx=maxx, optimizeBinning=False)
							histocName = anaRun.RemovePedestalFromSignal('PHcharge_CF', 'PHchargePedestal_CF', anaRun.pedestal_charge_sigmaCF, xmax=max(TruncateFloat(phchPpos / 4., 1000), TruncateFloat(phchPpos - 3.5 * phchGsigma, 1000)))
							anaRun.FitLanGaus(histocName)
						anaRun.PlotHVCurrents('HVCurrents', '', 5)
						anaRun.PlotDiaVoltage('DUTVoltage', '', 5)
					else:
						anaRun.FitConvolutedGaussians('PH')
						anaRun.FitConvolutedGaussians('PH_CF')
					anaRun.SaveAllCanvas()

					signalRun = 0
					signalSigmaRun = 0
					signalRunCF = 0
					signalSigmaRunCF = 0
					if 'PH' in anaRun.histo.keys():
						signalRun = np.double(anaRun.langaus['PH'].GetParameter(1)) if self.are_cal_runs else np.double(anaRun.histo['PH'].GetMean())
						signalSigmaRun = np.double(anaRun.langaus['PH'] .GetParameter(2)) if self.are_cal_runs else np.sqrt(np.power(anaRun.histo['PH'].GetRMS(), 2, dtype='f8') - np.power(anaRun.pedestal_sigma, 2, dtype='f8'), dtype='f8') if anaRun.histo['PH'].GetRMS() > anaRun.pedestal_sigma else anaRun.histo['PH'].GetRMS()
						signalRunCF = np.double(anaRun.langaus['PH_CF'].GetParameter(1)) if self.are_cal_runs else np.double(anaRun.histo['PH_CF'].GetMean())
						signalSigmaRunCF = np.double(anaRun.langaus['PH_CF'] .GetParameter(2)) if self.are_cal_runs else np.sqrt(np.power(anaRun.histo['PH_CF'].GetRMS(), 2, dtype='f8') - np.power(anaRun.pedestal_sigma, 2, dtype='f8'), dtype='f8') if anaRun.histo['PH_CF'].GetRMS() > anaRun.pedestal_sigma else anaRun.histo['PH_CF'].GetRMS()

					peakTime = 0
					peakTimeSigma = 0
					peakTimeCF = 0
					peakTimeSigmaCF = 0
					if self.are_cal_runs and '_out_' in run:
						if 'peakPosDist' in anaRun.histo.keys():
							peakTime = np.double(anaRun.peakTime * 1e6)
							peakTimeSigma = np.double(anaRun.histo['peakPosDist'].GetRMS())
						if 'peakPosDistCF' in anaRun.histo.keys():
							peakTimeCF = np.double(anaRun.peakTimeCF * 1e6)
							peakTimeSigmaCF = np.double(anaRun.histo['peakPosDistCF'].GetRMS())

					self.diaVoltages[anaRun.bias] = anaRun.voltageDiaMean
					self.diaVoltagesSigma[anaRun.bias] = anaRun.voltageDiaSpread
					if not anaRun.is_cal_run:
						signalRunVcal = 0
						signalSigmaRunVcal = 0
						signalRunCharge = 0
						signalSigmaRunCharge = 0
						signalRunVcalCF = 0
						signalSigmaRunVcalCF = 0
						signalRunChargeCF = 0
						signalSigmaRunChargeCF = 0
						if 'PHvcal' in anaRun.histo.keys():
							signalRunVcal = np.double(anaRun.histo['PHvcal'].GetMean())
							signalSigmaRunVcal = np.sqrt(np.power(anaRun.histo['PHvcal'].GetRMS(), 2, dtype='f8') - np.power(anaRun.pedestal_vcal_sigma, 2, dtype='f8'), dtype='f8') if anaRun.histo['PHvcal'].GetRMS() > anaRun.pedestal_vcal_sigma else anaRun.histo['PHvcal'].GetRMS()
						if 'PHcharge' in anaRun.histo.keys():
							signalRunCharge = np.double(anaRun.histo['PHcharge'].GetMean())
							signalSigmaRunCharge = np.sqrt(np.power(anaRun.histo['PHcharge'].GetRMS(), 2, dtype='f8') - np.power(anaRun.pedestal_charge_sigma, 2, dtype='f8'), dtype='f8')  if anaRun.histo['PHcharge'].GetRMS() > anaRun.pedestal_charge_sigma else anaRun.histo['PHcharge'].GetRMS()
						if 'PHvcal_CF' in anaRun.histo.keys():
							signalRunVcalCF = np.double(anaRun.histo['PHvcal_CF'].GetMean())
							signalSigmaRunVcalCF = np.sqrt(np.power(anaRun.histo['PHvcal_CF'].GetRMS(), 2, dtype='f8') - np.power(anaRun.pedestal_vcal_sigma, 2, dtype='f8'), dtype='f8') if anaRun.histo['PHvcal_CF'].GetRMS() > anaRun.pedestal_vcal_sigma else anaRun.histo['PHvcal_CF'].GetRMS()
						if 'PHcharge_CF' in anaRun.histo.keys():
							signalRunChargeCF = np.double(anaRun.histo['PHcharge_CF'].GetMean())
							signalSigmaRunChargeCF = np.sqrt(np.power(anaRun.histo['PHcharge_CF'].GetRMS(), 2, dtype='f8') - np.power(anaRun.pedestal_charge_sigma, 2, dtype='f8'), dtype='f8')  if anaRun.histo['PHcharge_CF'].GetRMS() > anaRun.pedestal_charge_sigma else anaRun.histo['PHcharge_CF'].GetRMS()
					if not self.are_cal_runs or '_out_' in run:
						self.signalOut[anaRun.bias] = signalRun if anaRun.bias < 0 else -signalRun
						self.signalOutSigma[anaRun.bias] = signalSigmaRun
						self.signalOutCF[anaRun.bias] = signalRunCF if anaRun.bias < 0 else -signalRunCF
						self.signalOutSigmaCF[anaRun.bias] = signalSigmaRunCF
						if not self.are_cal_runs:
							self.signalOutVcal[anaRun.bias] = -signalRunVcal if anaRun.bias < 0 else signalRunVcal
							self.signalOutVcalSigma[anaRun.bias] = signalSigmaRunVcal
							self.signalOutCharge[anaRun.bias] = -signalRunCharge if anaRun.bias < 0 else signalRunCharge
							self.signalOutChargeSigma[anaRun.bias] = signalSigmaRunCharge
							self.signalOutVcalCF[anaRun.bias] = -signalRunVcalCF if anaRun.bias < 0 else signalRunVcalCF
							self.signalOutVcalSigmaCF[anaRun.bias] = signalSigmaRunVcalCF
							self.signalOutChargeCF[anaRun.bias] = -signalRunChargeCF if anaRun.bias < 0 else signalRunChargeCF
							self.signalOutChargeSigmaCF[anaRun.bias] = signalSigmaRunChargeCF
						if '_out_' in run:
							self.signalPeakTime[anaRun.bias] = peakTime
							self.signalPeakTimeSigma[anaRun.bias] = peakTimeSigma
							self.signalPeakTimeCF[anaRun.bias] = peakTimeCF
							self.signalPeakTimeSigmaCF[anaRun.bias] = peakTimeSigmaCF
					else:
						self.signalIn[anaRun.bias] = -signalRun if anaRun.bias < 0 else signalRun
						self.signalInSigma[anaRun.bias] = signalSigmaRun
					del anaRun
		self.voltages = sorted(set(self.voltages))
		# ro.gROOT.SetBatch(False)

	def PlotSignals(self):
		if len(self.voltages) > 0:
			if self.are_cal_runs:
				voltages2 = []
				for volt in self.voltages:
					if volt in self.signalOut.keys() and volt in self.signalIn.keys():
						voltages2.append(volt)
				self.voltages = voltages2
				stepsIn = np.array([self.signalIn[volt] for volt in self.voltages], dtype='f8')
				stepsInErrs = np.array([self.signalInSigma[volt] for volt in self.voltages], dtype='f8')
				signalO = np.array([self.signalOut[volt] for volt in self.voltages], dtype='f8')
				signalOutErrs = np.array([self.signalOutSigma[volt] for volt in self.voltages], dtype='f8')
				signalOCF = np.array([self.signalOutCF[volt] for volt in self.voltages], dtype='f8')
				signalOutErrsCF = np.array([self.signalOutSigmaCF[volt] for volt in self.voltages], dtype='f8')
				self.graph = ro.TGraphErrors(len(self.voltages), stepsIn, signalO, stepsInErrs, signalOutErrs)
				self.graph.SetNameTitle('Signal_vs_CalStep_ch_' + str(self.caen_ch), 'Signal_vs_CalStep_ch_' + str(self.caen_ch))
				self.graph.GetXaxis().SetTitle('vcal step [mV]')
				self.graph.GetYaxis().SetTitle('signal [mV]')
				self.graphCF = ro.TGraphErrors(len(self.voltages), stepsIn, signalOCF, stepsInErrs, signalOutErrsCF)
				self.graphCF.SetNameTitle('Signal_CF_vs_CalStep_ch_' + str(self.caen_ch), 'Signal_CF_vs_CalStep_ch_' + str(self.caen_ch))
				self.graphCF.GetXaxis().SetTitle('vcal step [mV]')
				self.graphCF.GetYaxis().SetTitle('signal_CF [mV]')
			else:
				signalO = np.array([self.signalOut[volt] for volt in self.voltages], dtype='f8')
				signalOutErrs = np.array([self.signalOutSigma[volt] for volt in self.voltages], dtype='f8')
				signalOVcal = np.array([self.signalOutVcal[volt] for volt in self.voltages], dtype='f8')
				signalOutVcalErrs = np.array([self.signalOutVcalSigma[volt] for volt in self.voltages], dtype='f8')
				signalOCharge = np.array([self.signalOutCharge[volt] for volt in self.voltages], dtype='f8')
				signalOutChargeErrs = np.array([self.signalOutChargeSigma[volt] for volt in self.voltages], dtype='f8')
				signalOCF = np.array([self.signalOutCF[volt] for volt in self.voltages], dtype='f8')
				signalOutErrsCF = np.array([self.signalOutSigmaCF[volt] for volt in self.voltages], dtype='f8')
				signalOVcalCF = np.array([self.signalOutVcalCF[volt] for volt in self.voltages], dtype='f8')
				signalOutVcalErrsCF = np.array([self.signalOutVcalSigmaCF[volt] for volt in self.voltages], dtype='f8')
				signalOChargeCF = np.array([self.signalOutChargeCF[volt] for volt in self.voltages], dtype='f8')
				signalOutChargeErrsCF = np.array([self.signalOutChargeSigmaCF[volt] for volt in self.voltages], dtype='f8')
				diaVoltages = np.array([self.diaVoltages[volt] for volt in self.voltages], dtype='f8')
				diaVoltagesSigma = np.array([self.diaVoltagesSigma[volt] for volt in self.voltages], dtype='f8')
				self.graph = ro.TGraphErrors(len(self.voltages), diaVoltages, signalO, diaVoltagesSigma, signalOutErrs)
				self.graph.SetNameTitle('Signal_vs_HV', 'Signal_vs_HV')
				self.graph.GetXaxis().SetTitle('HV [V]')
				self.graph.GetYaxis().SetTitle('signal [mV]')
				self.graphCF = ro.TGraphErrors(len(self.voltages), diaVoltages, signalOCF, diaVoltagesSigma, signalOutErrsCF)
				self.graphCF.SetNameTitle('Signal_CF_vs_HV', 'Signal_CF_vs_HV')
				self.graphCF.GetXaxis().SetTitle('HV [V]')
				self.graphCF.GetYaxis().SetTitle('signal_CF [mV]')

				self.graphVcal = ro.TGraphErrors(len(self.voltages), diaVoltages, signalOVcal, diaVoltagesSigma, signalOutVcalErrs)
				self.graphVcal.SetNameTitle('SignalVcal_vs_HV', 'SignalVcal_vs_HV')
				self.graphVcal.GetXaxis().SetTitle('HV [V]')
				self.graphVcal.GetYaxis().SetTitle('signalVcal [mV]')
				self.graphVcalCF = ro.TGraphErrors(len(self.voltages), diaVoltages, signalOVcalCF, diaVoltagesSigma, signalOutVcalErrsCF)
				self.graphVcalCF.SetNameTitle('SignalVcal_CF_vs_HV', 'SignalVcal_CF_vs_HV')
				self.graphVcalCF.GetXaxis().SetTitle('HV [V]')
				self.graphVcalCF.GetYaxis().SetTitle('signalVcal_CF [mV]')

				self.graphCharge = ro.TGraphErrors(len(self.voltages), diaVoltages, signalOCharge, diaVoltagesSigma, signalOutChargeErrs)
				self.graphCharge.SetNameTitle('SignalCharge_vs_HV', 'SignalCharge_vs_HV')
				self.graphCharge.GetXaxis().SetTitle('HV [V]')
				self.graphCharge.GetYaxis().SetTitle('signalCharge [e]')
				self.graphChargeCF = ro.TGraphErrors(len(self.voltages), diaVoltages, signalOChargeCF, diaVoltagesSigma, signalOutChargeErrsCF)
				self.graphChargeCF.SetNameTitle('SignalCharge_CF_vs_HV', 'SignalCharge_CF_vs_HV')
				self.graphChargeCF.GetXaxis().SetTitle('HV [V]')
				self.graphChargeCF.GetYaxis().SetTitle('signalCharge_CF [e]')

			self.graph.SetMarkerStyle(7)
			self.graph.SetMarkerColor(ro.kBlack)
			self.graph.SetLineColor(ro.kBlack)
			self.graphCF.SetMarkerStyle(7)
			self.graphCF.SetMarkerColor(ro.kBlack)
			self.graphCF.SetLineColor(ro.kBlack)

			self.canvas = ro.TCanvas('c_' + self.graph.GetName(), 'c_' + self.graph.GetName(), 1)
			self.graph.Draw('AP')
			self.canvas.SetGridx()
			self.canvas.SetGridy()
			self.canvasCF = ro.TCanvas('c_' + self.graphCF.GetName(), 'c_' + self.graphCF.GetName(), 1)
			self.graphCF.Draw('AP')
			self.canvasCF.SetGridx()
			self.canvasCF.SetGridy()

			if not self.are_cal_runs:
				self.graphVcal.SetMarkerStyle(7)
				self.graphVcal.SetMarkerColor(ro.kBlack)
				self.graphVcal.SetLineColor(ro.kBlack)
				self.graphVcalCF.SetMarkerStyle(7)
				self.graphVcalCF.SetMarkerColor(ro.kBlack)
				self.graphVcalCF.SetLineColor(ro.kBlack)

				self.canvasVcal = ro.TCanvas('c_' + self.graphVcal.GetName(), 'c_' + self.graphVcal.GetName(), 1)
				self.graphVcal.Draw('AP')
				self.canvasVcal.SetGridx()
				self.canvasVcal.SetGridy()
				self.canvasVcalCF = ro.TCanvas('c_' + self.graphVcalCF.GetName(), 'c_' + self.graphVcalCF.GetName(), 1)
				self.graphVcalCF.Draw('AP')
				self.canvasVcalCF.SetGridx()
				self.canvasVcalCF.SetGridy()

				self.graphCharge.SetMarkerStyle(7)
				self.graphCharge.SetMarkerColor(ro.kBlack)
				self.graphCharge.SetLineColor(ro.kBlack)
				self.graphChargeCF.SetMarkerStyle(7)
				self.graphChargeCF.SetMarkerColor(ro.kBlack)
				self.graphChargeCF.SetLineColor(ro.kBlack)

				self.canvasCharge = ro.TCanvas('c_' + self.graphCharge.GetName(), 'c_' + self.graphCharge.GetName(), 1)
				self.graphCharge.Draw('AP')
				self.canvasCharge.SetGridx()
				self.canvasCharge.SetGridy()
				self.canvasChargeCF = ro.TCanvas('c_' + self.graphChargeCF.GetName(), 'c_' + self.graphChargeCF.GetName(), 1)
				self.graphChargeCF.Draw('AP')
				self.canvasChargeCF.SetGridx()
				self.canvasChargeCF.SetGridy()

	def PlotPeakTimes(self):
		if len(self.voltages) > 0:
			if self.are_cal_runs:
				if len(self.signalPeakTime.values()) < 1:
					for run in self.runs:
						print 'Analysing run:', run
						if os.path.isdir(run):
							root_files = glob.glob('{d}/*.root'.format(d=run))
							if len(root_files) > 0:
								if '_out_' in run:
									configfile = self.config
									print 'Using config file:', configfile
									print 'Loading analysis tree if it exists'
									anaRun = AnalysisCaenCCD(run, configfile, overw=False)
									anaRun.AnalysisWaves()
									peakTime = 0
									peakTimeSigma = 0
									if 'peakPosDist' in anaRun.histo.keys():
										peakTime = np.double(anaRun.peakTime * 1e6)
										peakTimeSigma = np.double(anaRun.histo['peakPosDist'].GetRMS())
									self.signalPeakTime[anaRun.bias] = peakTime
									self.signalPeakTimeSigma[anaRun.bias] = peakTimeSigma

				signalO = np.array([self.signalOut[volt] for volt in self.voltages], dtype='f8')
				signalOutErrs = np.array([self.signalOutSigma[volt] for volt in self.voltages], dtype='f8')
				signalPeaks = np.array([self.signalPeakTime[volt] for volt in self.voltages], 'f8')
				signalPeaksSigma = np.array([self.signalPeakTimeSigma[volt] for volt in self.voltages], 'f8')
				self.graphPeakTime = ro.TGraphErrors(len(self.voltages), signalO, signalPeaks, signalOutErrs, signalPeaksSigma)
				self.graphPeakTime.SetNameTitle('SignalPeakTime_vs_Signal_ch_' + str(self.caen_ch), 'SignalPeakTime_vs_Signal_ch_' + str(self.caen_ch))
				self.graphPeakTime.GetXaxis().SetTitle('signal [mV]')
				self.graphPeakTime.GetYaxis().SetTitle('Peak Time [us]')
				self.graphPeakTime.SetMarkerStyle(7)
				self.graphPeakTime.SetMarkerColor(ro.kBlack)
				self.graphPeakTime.SetLineColor(ro.kBlack)

				self.canvasPeakTime = ro.TCanvas('c_' + self.graphPeakTime.GetName(), 'c_' + self.graphPeakTime.GetName(), 1)
				self.graphPeakTime.Draw('AP')
				self.canvasPeakTime.SetGridx()
				self.canvasPeakTime.SetGridy()

	def FitLine(self):
		ro.Math.MinimizerOptions.SetDefaultMinimizer(*fit_method)
		ro.Math.MinimizerOptions.SetDefaultMaxFunctionCalls(1000000)
		ro.Math.MinimizerOptions.SetDefaultTolerance(0.00001)
		ro.gStyle.SetOptFit(1111)
		func = ro.TF1('fit_' + self.graph.GetName(), 'pol1', -1000, 1000)
		func.SetLineColor(ro.kRed)
		func.SetNpx(10000)
		tfit = self.graph.Fit('fit_' + self.graph.GetName(), 'QM0S', '', -1000, 1000)
		if tfit.Prob() < 0.9:
			tfit = self.graph.Fit('fit_' + self.graph.GetName(), 'QM0S', '', -1000, 1000)
		if tfit.Prob() < 0.9:
			tfit = self.graph.Fit('fit_' + self.graph.GetName(), 'QM0S', '', -1000, 1000)
		# func.SetParameters(np.array([tfit.Parameter(0), tfit.Parameter(1)], 'f8'))
		# func.SetChisquare(tfit.Chi2())
		# func.SetNDF(tfit.Ndf())
		func = tfit.FittedFunction().GetFunction()
		self.fit = func.Clone()
		self.canvas.cd()
		self.fit.Draw('same')
		self.canvas.Modified()
		ro.gPad.Update()

	def FillPickle(self):
		self.cal_pickle = {'voltages': self.voltages,
						   'signal_in': self.signalIn,
						   'signal_in_sigma': self.signalInSigma,
						   'signal_out': self.signalOut,
						   'signal_out_sigma': self.signalOutSigma,
						   'signal_out_vcal': self.signalOutVcal,
						   'signal_out_vcal_sigma': self.signalOutVcalSigma,
						   'signal_out_charge': self.signalOutCharge,
						   'signal_out_charge_sigma': self.signalOutChargeSigma,
		                   'signal_peak_time': self.signalPeakTime,
		                   'signal_peak_time_sigma': self.signalPeakTimeSigma,
						   'caen_ch': self.caen_ch,
						   'fit_p0': self.fit.GetParameter(0) if self.fit else 0,
						   'fit_p0_error': self.fit.GetParError(0) if self.fit else 0,
						   'fit_p1': self.fit.GetParameter(1) if self.fit else 0,
						   'fit_p1_error': self.fit.GetParError(1) if self.fit else 0,
						   'fit_prob': self.fit.GetProb() if self.fit else 0,
						   'fit_chi2': self.fit.GetChisquare() if self.fit else 0,
						   'fit_ndf': self.fit.GetNDF() if self.fit else 0
						   }

	def SavePickle(self, overWritePickle=False):
		pickleName = 'signal_cal_{c}.cal'.format(c=self.caen_ch) if self.are_cal_runs else 'signal_{c}.cal'.format(c=self.caen_ch)
		if not self.cal_pickle:
			self.FillPickle()
		if os.path.isfile('{d}/{f}'.format(d=self.runsdir, f=pickleName)):
			if not self.overwrite and not overWritePickle:
				print 'The file', pickleName, 'already exists in', self.runsdir, '. Not saving!'
				return
		with open('{d}/{f}'.format(d=self.runsdir, f=pickleName), 'wb') as fpickle:
			pickle.dump(self.cal_pickle, fpickle, pickle.HIGHEST_PROTOCOL)
		print 'Saved pickle', pickleName, 'in', self.runsdir

	def SaveCanvas(self):
		self.canvas.SaveAs('{d}/{n}.png'.format(d=self.runsdir, n=self.graph.GetName()))
		self.canvas.SaveAs('{d}/{n}.root'.format(d=self.runsdir, n=self.graph.GetName()))
		if self.canvasVcal:
			self.canvasVcal.SaveAs('{d}/{n}.png'.format(d=self.runsdir, n=self.graphVcal.GetName()))
			self.canvasVcal.SaveAs('{d}/{n}.root'.format(d=self.runsdir, n=self.graphVcal.GetName()))
		if self.canvasCharge:
			self.canvasCharge.SaveAs('{d}/{n}.png'.format(d=self.runsdir, n=self.graphCharge.GetName()))
			self.canvasCharge.SaveAs('{d}/{n}.root'.format(d=self.runsdir, n=self.graphCharge.GetName()))
		if self.canvasPeakTime:
			self.canvasPeakTime.SaveAs('{d}/{n}.png'.format(d=self.runsdir, n=self.graphPeakTime.GetName()))
			self.canvasPeakTime.SaveAs('{d}/{n}.root'.format(d=self.runsdir, n=self.graphPeakTime.GetName()))


def main():
	parser = OptionParser()
	parser.add_option('-d', '--runsdir', dest='runsdir', type='str', default='', help='path to folder containing all the run folders to modify')
	parser.add_option('-c', '--config', dest='config', type='str', default='', help='path to analysis config file used for all runs inside the folder')
	parser.add_option('-o', '--overwrite', dest='overwrite', default=False, action='store_true', help='Sets overwrite of analysis tree for the run if it exists')
	parser.add_option('--configinput', dest='configinput', type='str', default='', help='path to analysis config file used for all runs inside the folder that are of calibration type "in". Only necessary when doing signal calibration')
	(options, args) = parser.parse_args()
	runsdir = str(options.runsdir)
	config = str(options.config)
	configinput = str(options.configinput)
	overwrite = bool(options.overwrite)
	arif = AnalysisAllRunsInFolder(runsdir, config, configinput, overwrite)
	return arif

if __name__ == '__main__':
	arif = main()
