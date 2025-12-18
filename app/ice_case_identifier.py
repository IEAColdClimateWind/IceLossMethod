import pandas as pd
import numpy as np
import json

from pathlib import Path
import matplotlib.pyplot as plt
from datetime import datetime
import plotly.graph_objects as go
from plotly.subplots import make_subplots


DATA_DIR = Path(__file__).resolve().parent / 'app' / 'data'

class IceLossDetector(pd.DataFrame):
    
    #TODO add description of all meta data
    _metadata = ["temperatureCorrectionApplied","parameters","powerCurve","statistics"]
    
    #------------- Constructors and assosiated functions -------------------------------
    @property
    def _constructor(self):
        return IceLossDetector

    def __finalize__(self, other, method=None):
        for name in self._metadata:
            object.__setattr__(self, name, getattr(other, name, None))
        return self
    
    def __init__(self, *args, **kwargs):
        """
        These are default values for the ice detector
        Initialization neds now a default dataframe with hardcoded column titles.
        Idea is to use this internally to claulate the actual icign events and then ahve a separate method in the front
        To generate the dataframe
        
        """
        # initialize the DataFrame part
        super().__init__(*args, **kwargs)
        
        self.temperatureCorrectionApplied = False
        self.powerCurve = None
        self.parameters = {}
        self.statistics = {}
        # site specifics
        self.parameters['turbine_name'] = 'unnamed turbine'
        self.parameters['file_name'] = None
        self.parameters['rated_power'] = None #somewhere else in the code, when making the power curve check if None and replace value with max from PC
        self.parameters['hub_height'] = 80 #necessary?
        self.parameters['elevation'] = 100 #put to None? and handle it differently if not provided?
        
        # binning settings
        self.parameters['low_wind_bin'] = 0
        self.parameters['high_wind_bin']= 20
        self.parameters['wind_bin_size'] = 1
        
        # power curve limits
        self.parameters['low_quantile'] = 0.1
        self.parameters['high_quantile'] = 0.9
        
        # temperature limits
        self.parameters['temperature_filter_level'] = 3 
        self.parameters['icing_alarm_limit'] = 1
        
        # other limits
        self.parameters['alarm_time_limit'] = 3
        self.parameters['minimum_wind_speed'] = 3
        self.parameters['stop_limit'] = 100

    @classmethod
    def importFromCSV(cls, fileName):
        """
        Creates a IceLossDetector from a standard csv file generated from the import module
        
        """
        #TODO: optionnal json file for column matching
        full_data = pd.read_csv(fileName,index_col=0)
        ice_det = cls.constructFromDataFrame(full_data)
        return ice_det
    
    @classmethod
    def constructFromDataFrame(cls, df):
        
        if not np.isin(['wind_speed', 'ambient_temperature', 'output_power', #'timestamp', 
               'normal_operation', 'wind_direction', 'pressure', 'maintenance',
               'faults', 'curtailment', 'other_manual', 'icing_codes', 'ice_detection',
               'ips_status'],df.columns).all():
            raise ImportError('The provided data does not contain the required columns of the standard file')
            
        ice_det = IceLossDetector(df) 
        if not ice_det.isTenMinuteInterval():
            raise ImportError('Please provide 10-minute data')
        ice_det.retimeToTenMinute()
        return ice_det
    
    #------------- Helper methods for constructors --------------
    #TODO check if relevant to put those as helper functions
    
    def isTenMinuteInterval(self):
        if not isinstance(self.index, pd.DatetimeIndex):
            self.index = pd.to_datetime(self.index)
        diffs = self.index.to_series().diff().dropna()
        mostFreq = diffs.mode()[0]
        return mostFreq == pd.Timedelta(minutes=10)
     
    def retimeToTenMinute(self):
        step = pd.Timedelta(minutes=10) 
        first = self.index.min()
        last = self.index.max()
        binStart = first + ((self.index - first) // step) * step
        out = self.groupby(binStart).mean(numeric_only=True).sort_index()
        lastBin = first + ((last - first) // step) * step
        fullIndex = pd.date_range(start=first, end=lastBin, freq=step)
        out = out.reindex(fullIndex)
        out.index.name = self.index.name
        return out                 

    def temperatureCorrection(self):
        if not self.temperatureCorrectionApplied:
            kelvin = 273.15
            temp_std = 288.15
            # density_correction = ((line[self.temp_index]+kelvin)*p_std)/(temp_std*(p_std*((1-self.site_elevation*2.2557e-5)**5.25588)))
            density_correction = ((temp_std/(self['ambient_temperature']+kelvin))*((1-self.parameters['elevation']*2.2557e-5)**5.25588))**(1/3)
            ws_correct_noname = self['wind_speed'].mul(density_correction)
            ws_correct = ws_correct_noname.rename('wind_speed_c')
            self.loc[:,'wind_speed_c'] = ws_correct
            self.temperatureCorrectionApplied =True
        #new_data = pd.merge(left=self, right=ws_correct, left_index=True, right_index=True)
        #return new_data
        
    #------------------- Parameter handling methods -----------------------------
    def addParametersFromJSON(self, json_source):
        #TODO check for validity, adapt variable names, add missing variables to json, adapt to the change in the json for multiple turbines
        self.parameters = read_json_parameters(json_source)
            
    def saveParametersToJSON(self, json_fname):
        # Determine turbine name
        turbineName = self.parameters.get("turbine_name", "unnamed_turbine")

        # Build full JSON dictionary
        data = {
            "columns": {
                "Timestamp": "Timestamp",
                "Wind speed": "Wind speed [m/s]",
                "Ambient temperature": "Ambient temperature [C]",
                "Output Power": "output power [kW]",
                "Normal Operation": "Status"
            },
            "parameters": {
                "unit_wind_speed": None,
                "unit_power": None,
                "unit_temperature": None,
                "normal_operation_key": "OK"
            },
            "optional_columns": {
                "meteorological": {
                    "Wind direction": {"column": None, "unit": None},
                    "Pressure": {"column": None, "unit": None}
                },
                "operation": {
                    "Maintenance": {"column": None, "key": None},
                    "Faults": {"column": None, "key": None},
                    "Curtailment": {"column": None, "key": None},
                    "Other manual": {"column": None, "key": None}
                },
                "icing": {
                    "Icing codes": {"column": None, "key": None},
                    "Ice detection": {"column": None, "key": None},
                    "IPS status": {"column": None, "key": None}
                }
            },
            "turbines_info":
                {
                    "Filename": self.parameters.get("file_name", "no_file_name"),
                    "Turbine Name": turbineName,
                    "Rated Power [MW]": float(self.parameters.get("rated_power", 0) or 0),
                    "Elevation [m]": float(self.parameters.get("elevation", 100) or 100),
                    "Hub Height [m]": float(self.parameters.get("hub_height", 80) or 80)
                }
            ,
            "power_curve_options": {
                "temperature_threshold_C": float(self.parameters.get("temperature_filter_level", 0)),
                "output_path": "output/power_curve",
                "lower_limit_percent": float(self.parameters.get("low_quantile", 0)) * 100,
                "upper_limit_percent": float(self.parameters.get("high_quantile", 0)) * 100,
                "binning": {
                    "min": float(self.parameters.get("low_wind_bin", 0)),
                    "max": float(self.parameters.get("high_wind_bin", 30)),
                    "step": float(self.parameters.get("wind_bin_size", 1))
                }
            }
        }

        # Save JSON file
        with open(json_fname, "w") as file:
            json.dump(data, file, indent=4)
            
        return data  
    
    #----------------- Useful function to handle data ----------------------
    
    def selectPeriod(self,startTime,endTime,inplace=False):
        if inplace:
            self = self.loc[(self.index>=startTime)&(self.index<=endTime),:]
        else:
            newTurbine = self.copy()
            newTurbine = newTurbine.loc[(newTurbine.index>=startTime)&(newTurbine.index<=endTime),:]
            return newTurbine
        
    def flagOtherManual(self,indexList=None,startTime=None,endTime=None):
        if indexList is not None:
            #index list is either a list of index or a boolean list of all indexes where flag_other should be true
            self.loc[indexList,'other_manual'] = True
            
        if ((startTime is not None) & (endTime is not None)):
            self.loc[(self.index>=startTime)&(self.index<=endTime),'other_manual'] = True
        
    def removeOtherManual(self,indexList=None,startTime=None,endTime=None):
        if indexList is not None:
            #index list is either a list of index or a boolean list of all indexes where flag_other should be true
            self.loc[indexList,'other_manual'] = False
            
        if ((startTime is not None) & (endTime is not None)):
            self.loc[(self.index>=startTime)&(self.index<=endTime),'other_manual'] = False
        
    def resetOtherManual(self):
        #index list is either a list of index or a boolean list of all indexes where flag_other should be true
        self.loc[:,'other_manual'] = False
        
    
    #----------------- Power curve related methods -------------------------
    
    def makePowerCurve(self):
        """
        ·         Power curve used to detect icing

                        o    Includes the limits (P10, P90)

                        o    Also sample count per bin

                        o    Some kind of diagnostic of the quality of the power curve (To be implemented)

        """
        self.temperatureCorrection()
        if 'cleanedDatasetMask' not in self.columns:
            self.identifyCleanedDataset()
        reference_dataset = self.loc[self.loc[:,'cleanedDatasetMask'],:]
        # this needs to be settable
        wind_bins = pd.interval_range(start=self.parameters['low_wind_bin'], end=self.parameters['high_wind_bin'], freq=self.parameters['wind_bin_size'])
        # create binning for the dataset based on the corrected wind speed
        binning = pd.cut(reference_dataset['wind_speed_c'],bins=wind_bins)
        binning_r = binning.rename("bin")
        # add bin index for every value in the dataset
        reference_dataset_b = pd.merge(left=reference_dataset, right=binning_r, left_index=True, right_index=True)

        # group by bin, calculate bunch of statistics for each bin
        # aggregation functions are listed as ('name of result', function)
        fullPc = reference_dataset_b[["wind_speed_c","output_power","bin"]].groupby('bin',observed=False).agg([
            ('mean', 'mean'),
            ('low_quantile', lambda x: x.quantile(self.parameters['low_quantile'])),
            ('high_quantile', lambda x: x.quantile(self.parameters['high_quantile'])),
            ('std.dev','std'),
            ('max', 'max'),
            ('min', 'min'),
            ('count', 'count')
        ])
        pc = fullPc.loc[:,[('wind_speed_c','mean'),('output_power','mean'),('output_power','low_quantile'),('output_power','high_quantile')]]
        pc.columns = ['windSpeedMean','outputPowerMean','outputPowerLowQuantile','outputPowerHighQuantile']
        pc.reset_index(drop=True,inplace=True)
        # print(pc[[('wind_speed_c','mean'),('output_power','mean'),('output_power','P10'),('output_power','P90')]])
        self.powerCurve = pc
        #pc.rename(columns = {"wind_speed_c":"wind_speed"},inplace=True)
        #pc_subset = pc[[('wind_speed','mean'),('output_power','mean'),('output_power','low_quantile'),('output_power','high_quantile'),('output_power','count')]]
        
        # Flatten MultiIndex columns to make refrencing make more sense
        #pc_subset.columns = ['{}_{}'.format(col[0], col[1]) for col in pc_subset.columns]
        # print(pc_subset)
        return fullPc
    
    def addExpectedPowerToData(self):
        if self.powerCurve is None:
            AttributeError('The power curve has not been computed, please compute it using makePowerCurve()')
        pc = self.powerCurve
        self.temperatureCorrection()
        # interpoaltion cannot handle NaN
        pc_mask = ~(np.isnan(pc['windSpeedMean']))
        # piecewise linear interpolation over the power curves to get the refrence values for alarm creation
        y10 = pc[pc_mask]['outputPowerLowQuantile'].to_numpy()
        y90 = pc[pc_mask]['outputPowerHighQuantile'].to_numpy()
        w = pc[pc_mask]['windSpeedMean'].to_numpy()
        y = pc[pc_mask]['outputPowerMean'].to_numpy()
        self['low_quantile_ref'] = np.interp(self['wind_speed_c'].to_numpy(),w,y10)
        self['high_quantile_ref'] = np.interp(self['wind_speed_c'].to_numpy(),w,y90)
        self['expected_power'] = np.interp(self['wind_speed_c'].to_numpy(),w,y)
        
    def exportPowerCurveToCSV(self,fileName=None,recompute=False):
        if fileName is None:
            fileName = f"{self.parameters['turbine_name']}_pc.csv"
        if (self.powerCurve is None) | recompute:
            self.makePowerCurve()
        self.powerCurve.to_csv(fileName,index=False)
        
    def import_power_curve(self,fileName):
        newPowerCurve = pd.read_csv(fileName)
        required_cols = ['windSpeedMean','outputPowerMean','outputPowerLowQuantile','outputPowerHighQuantile']
        if not np.isin(required_cols,newPowerCurve.columns).all():
            raise ImportError('The provided power curve does not match the column names of the standard file')
        self.powerCurve = newPowerCurve

    def powerCurveDiagnostic(self):
        #TODO write this function, to identify faulty power curves, define metrics
        print('TBD')
    
    #----------------- Icing period identification methods ---------------------------
        
    def identifyCleanedDataset(self):
        # these can probaably be hardcoded, esp. if ¨"other_manual" can be set from UI.
        reference_dataset_mask = (self["normal_operation"] == True) &\
                                (self["faults"] == False) & \
                                (self["curtailment"] == False) & \
                                (self["other_manual"] == False) & \
                                (self["ambient_temperature"] >= self.parameters['temperature_filter_level'])
        #TODO add option to remove ice detection and icing code from dataset
        #(self["icing_codes"] == False) & \
        #(self["ice_detection"] == False) & \
        self.loc[:,'cleanedDatasetMask'] = reference_dataset_mask

    def identifyIceLossPeriods(self):
        if 'low_quantile_ref' not in self.columns:
            AttributeError('The low quantile reference power is not computed, please compute it using addExpectedPowerToData()')
        # Alarm limit need to conver this to (1,0) instead of booleans for the length filter to work.
        self['iceLossMask'] = 1.0*((self['output_power'] < self['low_quantile_ref']) & \
                                    (self['ambient_temperature'] < self.parameters['icing_alarm_limit']) & \
                                    (self['wind_speed'] >= self.parameters['minimum_wind_speed']) & \
                                    (self["normal_operation"] == True) & \
                                    (self["faults"] == False) & \
                                    #(dataset["icing_codes"] == False) & \
                                    (self["curtailment"] == False) & \
                                    #(dataset["ice_detection"] == False) & \
                                    (self["other_manual"] == False)
                                    ) #TODO change name of column to specify that it is a mask
        
        # Identify changes in the 'alarm' column to segment sequences
        mask = self['iceLossMask'] != self['iceLossMask'].shift()
        # want group these by event length for length-based filtering
        group = mask.cumsum()

        # Apply transformation only to groups where 'alarm' == 1
        # mask detects where the value changes (from 0 to 1 or vice versa).
        # group assigns a unique group ID to each sequence.
        # groupby(group) groups consecutive values.
        # transform replaces each 1 in a group with the length of that group only if the group starts with 1.
        self['ice_alarm_duration'] = self.groupby(group)['iceLossMask'].transform(lambda x: len(x) if x.iloc[0] == 1 else x)
        # time filter, require at least 3 consequtive alarms
        self['ice_alarm_duration'] = self['ice_alarm_duration'].where(self['ice_alarm_duration'] >= self.parameters['alarm_time_limit'], 0)
        self['iceLossMask'] = self['iceLossMask'].where(self['ice_alarm_duration'] >= self.parameters['alarm_time_limit'], 0)
        self.computeIcingLosses()
        #Dataframe with the original input data with additional columns
        #    o    Ice detection, different event classes as separate columns
        #    o    Reference power
        #    o    Ice alarm duration?
        #    o    Icing losses at each timestamp
        
        # ToDo:
        # fix the return column names and datatypes, needs to be boolean
        # check what happens with nan values
        self.identifyIceLossOperational()
        self.identifyIceLossStandstill()


    def identifyIceLossStandstill(self):
        if 'iceLossMask' not in self.columns:
            AttributeError('The low quantile reference power is not computed, please compute it using identifyIceLossPeriods()')
        # separate the points when the turbine has stopped from the other icing alarms
        # Stops are events where we have an icing alarm, but the power is below a certain limit. 
        #TODO: add a check on RPM?
        #standstill = idle or completely stopped
        stop_mask = ((self['iceLossMask'] == 1.0) & (self['output_power'] <= self.parameters['stop_limit']) &\
                    (self['wind_speed'] >= self.parameters['minimum_wind_speed']))
        self['iceLossStandstillMask'] = 1.0*stop_mask 

    def identifyIceLossOperational(self):
        if 'iceLossMask' not in self.columns:
            AttributeError('The low quantile reference power is not computed, please compute it using identifyIceLossPeriods()')
        # separate the points when the turbine has stopped from the other icing alarms
        # Stops are events where we have an icing alarm, but the power is below a certain limit. 
        running_mask = ((self['iceLossMask'] == 1.0) & ((self['output_power'] > self.parameters['stop_limit']) |\
                    (self['wind_speed'] < self.parameters['minimum_wind_speed'])))
        self['iceLossOperationalMask'] = 1.0*running_mask 
        
    def identifyIceLossOverProduction(self):
        #TODO write this function
        print('TBD')
        
    #----------------- Icing computation methods ---------------------------

    def computeIcingLosses(self):
        if np.isin(['iceLossMask','expected_power'],self.columns).all():
            AttributeError('The icing periods or the expected power are not computed, please compute it using identifyIceLossPeriods() or addExpectedPowerToData()')
        #self['power_deficit'] = (self['expected_power'] - self['output_power'])
        self['production_loss'] = (self['expected_power'] - self['output_power']) * 10/60 # loss in kw * duration of loss (10 minutes) loss in kWh
        self['icingLosses'] = self['iceLossMask'] * (self['expected_power']-self['output_power']) * 10 / 60 #in kWh at each timestamp

    def computeProducedEnergy(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'output_power']*10/60).sum(),0))
        else:
            return float(np.round((self['output_power']/6).sum(),0))

    def computeTotalIcingLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'icingLosses']).sum(),0))
        else:
            return float(np.round((self['icingLosses']).sum(),0))
        
    def computeTotalLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'production_loss']).sum(),0))
        else:
            return float(np.round((self['production_loss']).sum(),0))
    
    def computeTotalIcingReducedProductionLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round(
                (self['icingLosses']*self['iceLossOperationalMask'])
                 .loc[(self.index>=periodStart)&(self.index<=periodEnd),:].sum(),0))
        else:
            return float(np.round((self['icingLosses']*self['iceLossOperationalMask']).sum(),0))
        
    def computeTotalIcingStandstillLosses(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round(
                (self['icingLosses']*self['iceLossStandstillMask'])
                 .loc[(self.index>=periodStart)&(self.index<=periodEnd),:].sum(),0))
        else:
            return float(np.round((self['icingLosses']*self['iceLossStandstillMask']).sum(),0))

    def computeExpectedEnergy(self,periodStart=None,periodEnd=None):
        if (periodStart is not None) and (periodEnd is not None):
            return float(np.round((self.loc[(self.index>=periodStart)&(self.index<=periodEnd),'expected_power']*10/60).sum(),0))
        else:
            return float(np.round((self['expected_power']/6).sum(),0))

    def computeNumberOfIcingEvents(self,periodStart=None,periodEnd=None):
        #TODO write this function, it is currently in computeIcingStatistics, find a way that fimple values are not computed many times
        print('TBD')

    def computeAverageEventDuration(self,periodStart=None,periodEnd=None):
        #TODO write this function, it is currently in computeIcingStatistics, find a way that fimple values are not computed many times
        print('TBD')

    #TODO add as many functions as there are statistics to be computed
    
    def computeIcingStatistics(self, periodStarts=None, periodEnds=None, frequency=None):
        """
        Statistics of production:
          o    Icing hours / icing as % of year
                 §  Total and per class
          o    Icing losses
                 §  Total and per icing class
          o    Statistics on availability, data coverage etc.
          o    Total energy produced, expected and loss (icing, faults/maintenance, during icing detection, during IPS activation)
          o    Time in each category (icing, faults/maintenance, during icing detection, during IPS activation)
          o    Same but in Dollars or euros (To be implemented)
          o    Number of icing events
        """
        
        #TODO: add per year calculation or per period
        #statistics could be a dataframe with start time as index
        
        if 'iceLossMask' not in self.columns:
            self.identifyIceLossPeriods()
        
        if frequency is not None:
            if frequency not in ['yearly', 'monthly']:
                raise AttributeError("frequency must be either 'yearly' or 'monthly'")
    
            tMin = self.index.min()
            tMax = self.index.max()
    
            if frequency == 'yearly':
                edges = pd.date_range(start=tMin.normalize(), end=tMax, freq='YS')
            else:
                edges = pd.date_range(start=tMin.normalize(), end=tMax, freq='MS')
                
            if edges[0] > tMin:
                edges = edges.insert(0, tMin)
            if edges[-1] < tMax:
                edges = edges.append(pd.DatetimeIndex([tMax]))
    
            periodStarts = list(edges[:-1])
            periodEnds = list(edges[1:])
        
        if periodStarts is None:
            periodStarts = [self.index.min()]
        if periodEnds is None:
            periodEnds = [self.index.max()]
        if (type(periodStarts)!=list) | (type(periodEnds)!=list):
            raise AttributeError('Period starts and ends must be a list of datetime')
        if len(periodEnds) != len(periodStarts):
            raise AttributeError('Length of the list of period start does not equal to the one of the period length')
        
        #create empty DF
        statistics = pd.DataFrame(columns=['total_data_hours', 'total_icing_duration', 'reduced_production_duration', 
                                           'icing_stop_duration', 'total_icing_share', 'reduced_production_share', 'icing_stop_share', 
                                           'total_production', 'total_expected_production', 'total_losses', 'total_icing_loss', 
                                           'reduced_production_loss', 'icing_stop_loss', 'reduced_producion_share', 'maintenance_hours', 
                                           'faults_hours', 'curtailment_hours', 'other_manual_hours', 'icing_codes_hours', 
                                           'ice_detection_hours', 'ips_status_hours', 'reference_hours'])
        
        for periodStart, periodEnd in zip(periodStarts,periodEnds):
            periodDF = self.selectPeriod(periodStart, periodEnd).copy()
            # separate the icing events
            reduced_prod_events = periodDF[periodDF['iceLossMask'] == 1]
            stops_events = periodDF[periodDF['iceLossStandstillMask'] == 1]
            icing_events = pd.concat((reduced_prod_events, stops_events))
            
            # total dataset length in hours§
            statistics.loc[periodStart,"total_data_hours"]            = float(np.round((periodDF.index.max() - periodDF.index.min()).total_seconds() /60 /60 ,0))
            
            # these are not continuous cant count from timestamps
            statistics.loc[periodStart,"total_icing_duration"]        = float(np.round((1/6)*len(icing_events),0)) # number of lines * 10 minutes / 60 minutes = total hours
            statistics.loc[periodStart,"reduced_production_duration"] = float(np.round((1/6)*len(reduced_prod_events),0))
            statistics.loc[periodStart,"icing_stop_duration"]         = float(np.round((1/6)*len(stops_events),0))
            #icing share is often interesting since its in the ice class.
            statistics.loc[periodStart,"total_icing_share"]           = float(np.round(len(icing_events) / len(periodDF.index) * 100,2))
            statistics.loc[periodStart,"reduced_production_share"]    = float(np.round(len(reduced_prod_events) / len(periodDF.index) * 100, 2))
            statistics.loc[periodStart,"icing_stop_share"]            = float(np.round(len(stops_events) / len(periodDF.index) * 100, 2))
            # energy in kWh
            statistics.loc[periodStart,"total_production"]          = periodDF.computeProducedEnergy()         #float(np.round((periodDF['output_power']/6).sum(),0))
            statistics.loc[periodStart,"total_expected_production"] = periodDF.computeExpectedEnergy()         #float(np.round((periodDF['expected_power']/6).sum(),0))
            statistics.loc[periodStart,"total_losses"]              = periodDF.computeTotalLosses()            #float(np.round(periodDF['production_loss'].sum(),0))
            statistics.loc[periodStart,"total_icing_loss"]          = periodDF.computeTotalIcingLosses()       #float(np.round(icing_events["production_loss"].sum(),0))
            statistics.loc[periodStart,"reduced_production_loss"]   = periodDF.computeTotalIcingReducedProductionLosses() #float(np.round(reduced_prod_events["production_loss"].sum(),0))
            statistics.loc[periodStart,"icing_stop_loss"]           = periodDF.computeTotalIcingStandstillLosses() #float(np.round(stops_events["production_loss"].sum(),0))
            # losses in % of total production not neccessarily AEP
            statistics.loc[periodStart,"total_icing_share"]         = float(np.round(statistics.loc[periodStart,"total_icing_loss"] / 
                                                                          statistics.loc[periodStart,"total_expected_production"],2))
            statistics.loc[periodStart,"reduced_producion_share"]   = float(np.round(statistics.loc[periodStart,"reduced_production_loss"] / 
                                                                          statistics.loc[periodStart,"total_expected_production"],2))
            statistics.loc[periodStart,"icing_stop_share"]          = float(np.round(statistics.loc[periodStart,"icing_stop_loss"] /
                                                                          statistics.loc[periodStart,"total_expected_production"],2))
            
            # other status variables again, cant count form timestamps so number of hours is number of lines * 1/6:
            # maintenance	faults	curtailment	other_manual	icing_codes	ice_detection	ips_status	cleanedDatasetMask
            statistics.loc[periodStart,"maintenance_hours"]   = float(np.round((1/6)*len(periodDF[periodDF["maintenance"]       ==True]),0))
            statistics.loc[periodStart,"faults_hours"]        = float(np.round((1/6)*len(periodDF[periodDF["faults"]            ==True]),0))
            statistics.loc[periodStart,"curtailment_hours"]   = float(np.round((1/6)*len(periodDF[periodDF["curtailment"]       ==True]),0))
            statistics.loc[periodStart,"other_manual_hours"]  = float(np.round((1/6)*len(periodDF[periodDF["other_manual"]      ==True]),0))
            statistics.loc[periodStart,"icing_codes_hours"]   = float(np.round((1/6)*len(periodDF[periodDF["icing_codes"]       ==True]),0))
            statistics.loc[periodStart,"ice_detection_hours"] = float(np.round((1/6)*len(periodDF[periodDF["ice_detection"]     ==True]),0))
            statistics.loc[periodStart,"ips_status_hours"]    = float(np.round((1/6)*len(periodDF[periodDF["ips_status"]        ==True]),0))
            statistics.loc[periodStart,"reference_hours"]     = float(np.round((1/6)*len(periodDF[periodDF["cleanedDatasetMask"]==True]),0))
            
        self.statistics = statistics
        
    def exportStatistics(self,fileName=None,recompute=False):
        if fileName is None:
            fileName = ice_det.parameters['turbine_name']+'_statistics.csv'
        if (len(self.statistics) == 0) | recompute:
            self.computeIcingStatistics()
        pd.Series(self.statistics).to_csv(fileName)
        
    #---------------- Full flow computation methods --------------------------

    def computeFullChain(self):
        """
        run the correct sequence of functions and return the dataframe with icign events
        """
        self.temperatureCorrection()
        self.identifyCleanedDataset()
        self.makePowerCurve() #TODO find a way to manually add a power curve, you can skip this step if you have reference power low and high quantile
        self.addExpectedPowerToData()
        self.identifyIceLossPeriods()
        self.computeIcingLosses()

        self.computeIcingStatistics()
        #return icing_data
        
    @classmethod
    def iceLossAnalysis(cls, fileNameData, fileNameConfig, fileNameOutput, computePowerCurve=True):
        ice_det = cls.importFromCSV(fileNameData)
        ice_det.addParametersFromJSON(fileNameConfig)
        if computePowerCurve:
            ice_det.identifyCleanedDataset()
            ice_det.makePowerCurve()
            ice_det.addExpectedPowerToData()
        ice_det.identifyIceLossPeriods()
        ice_det.computeIcingLosses()
        ice_det.to_csv(fileNameOutput)
        if computePowerCurve:
            ice_det.plotPowerCurve() #optional
        ice_det.plotTimeseries()
        
    #------------------------------ Plotting methods --------------------------------------
    
    def plotPowerCurve(self): #TODO add option to add IPS activation and ice detection, add garnish to this function, print to file?
        if self.powerCurve is None:
            AttributeError('The power curve has not been computed, please compute it using makePowerCurve()')
        pc = self.powerCurve
        pc.plot(x='windSpeedMean', y=['outputPowerMean','outputPowerLowQuantile','outputPowerHighQuantile'],label=['mean','low_quantile','high_quantile'])
        ax2 = plt.gca()
        self.plot.scatter(x="wind_speed_c",y='output_power',color='gray',alpha=0.1, ax=ax2,label='All points')
        self[self['iceLossMask'] == 1].plot.scatter(x="wind_speed_c",y='output_power',color='red',alpha=0.1, ax=ax2, label='Icing losses')
        ax2.set_title(f"Power curve: {self.parameters['turbine_name']}")
        plt.tight_layout()
        plt.show()




    def plot_plotly_power_curves(self):
        if self.powerCurve is None:
            raise AttributeError(
                "The power curve has not been computed. Call makePowerCurve() first."
            )

        pc = self.powerCurve

        fig = go.Figure()

        # ---- Power curve lines ----
        fig.add_trace(
            go.Scatter(
                x=pc['windSpeedMean'],
                y=pc['outputPowerMean'],
                mode="lines",
                name="Mean power curve",
            )
        )

        fig.add_trace(
            go.Scatter(
                x=pc['windSpeedMean'],
                y=pc['outputPowerLowQuantile'],
                mode="lines",
                name="Low quantile",
                line=dict(dash="dash"),
            )
        )

        fig.add_trace(
            go.Scatter(
                x=pc['windSpeedMean'],
                y=pc['outputPowerHighQuantile'],
                mode="lines",
                name="High quantile",
                line=dict(dash="dash"),
            )
        )

        # ---- All points ----
        fig.add_trace(
            go.Scatter(
                x=self["wind_speed_c"],
                y=self["output_power"],
                mode="markers",
                name="All points",
                marker=dict(color="gray", opacity=0.1),
            )
        )

        # ---- Icing losses ----
        icing_mask = self["iceLossMask"] == 1
        fig.add_trace(
            go.Scatter(
                x=self.loc[icing_mask, "wind_speed_c"],
                y=self.loc[icing_mask, "output_power"],
                mode="markers",
                name="Icing losses",
                marker=dict(color="red", opacity=0.3),
            )
        )

        fig.update_layout(
            title=f"Power curve: {self.parameters['turbine_name']}",
            xaxis_title="Wind speed (corrected)",
            yaxis_title="Power output",
            legend_title="Legend",
            template="plotly_white",
        )

        return fig

        
    def plotTimeseries(self): #TODO add option to add IPS activation and ice detection, add garnish to this function, print to file?
        fig, ax = plt.subplots(nrows=3,ncols=1,sharex=True,figsize=[12,8])
        self.plot.line(y=['output_power','low_quantile_ref','high_quantile_ref','expected_power'],ax=ax[0]) #x=index
        self.plot.line(y=['iceLossOperationalMask','iceLossStandstillMask'],ax=ax[1])
        self.plot.line(y='wind_speed', ax=ax[2])
        self.plot.line(y='ambient_temperature', ax=ax[2], secondary_y=True)
        ax[0].set_title(f"Timeseries: {self.parameters['turbine_name']}")
        plt.tight_layout()
        plt.show()
        

	#TODO: event length histogram



    def plot_plotly_time_series(self):
        fig = make_subplots(
            rows=3,
            cols=1,
            shared_xaxes=True,
            vertical_spacing=0.05,
            specs=[
                [{}],
                [{}],
                [{"secondary_y": True}],
            ],
        )

        # ---- Power-related signals ----
        for col in [
            "output_power",
            "low_quantile_ref",
            "high_quantile_ref",
            "expected_power",
        ]:
            fig.add_trace(
                go.Scatter(
                    x=self.index,
                    y=self[col],
                    mode="lines",
                    name=col,
                ),
                row=1,
                col=1,
            )

        # ---- Ice loss masks ----
        for col in [
            "iceLossOperationalMask",
            "iceLossStandstillMask",
        ]:
            fig.add_trace(
                go.Scatter(
                    x=self.index,
                    y=self[col],
                    mode="lines",
                    name=col,
                ),
                row=2,
                col=1,
            )

        # ---- Wind speed ----
        fig.add_trace(
            go.Scatter(
                x=self.index,
                y=self["wind_speed"],
                mode="lines",
                name="wind_speed",
            ),
            row=3,
            col=1,
            secondary_y=False,
        )

        # ---- Temperature (secondary axis) ----
        fig.add_trace(
            go.Scatter(
                x=self.index,
                y=self["ambient_temperature"],
                mode="lines",
                name="ambient_temperature",
            ),
            row=3,
            col=1,
            secondary_y=True,
        )

        fig.update_layout(
            title=f"Timeseries: {self.parameters['turbine_name']}",
            template="plotly_white",
            height=800,
            legend_title="Signals",
        )

        fig.update_yaxes(title_text="Power", row=1, col=1)
        fig.update_yaxes(title_text="Ice loss mask", row=2, col=1)
        fig.update_yaxes(title_text="Wind speed", row=3, col=1, secondary_y=False)
        fig.update_yaxes(
            title_text="Temperature", row=3, col=1, secondary_y=True
        )

        fig.show()

    #------------------ Static Methods -----------------------

    @staticmethod
    def compute_wind_farm(windFarmCsv, json_source=None, customColNamesDict=None):
        """
        Generates the icing statistics from a standard json file that imports csv files generated from the import module
        
        """
        #TODO: handle single csv with ID column
        farm_statistics_dict = {}
        # TODO: better handle parent directory that has all the CSV
       
        if json_source is None:
            # if no json file is provided, create a standard one
            json_source = 'defaultParameters.json'
            parameters = IceLossDetector.create_default_json_parameter_file(json_source)
            
        read_json_parameters(json_source)
        windFarmDF = readWindFarmDFFromCSV(windFarmCsv,customColNamesDict=customColNamesDict)
        
        #Handle 2 cases, 1- A single csv with all the turbine and a ID column, 2- A csv file per turbine
        if (len(windFarmDF.file_name.unique()) == 1) & (len(windFarmDF)!=1):
            fullDF = IceLossDetector.importFromCSV(Path('app') / 'data' / windFarmDF.file_name[0])
            if 'ID' not in fullDF.columns:
                raise ImportError('Single data csv file in import list, the file does not include the ID column necessary for multiple turbines')
            uniqueTurbines = fullDF.ID.unique()
            for uniqueTurbine in uniqueTurbines:
                ice_det = fullDF.loc[fullDF.ID==uniqueTurbine,:]
                ice_det.addParametersFromJSON(json_source)
                ice_det.parameters.update(windFarmDF.loc[windFarmDF.turbine_name==uniqueTurbine,:].squeeze(axis=0).to_dict())
                ice_det.computeFullChain()
                farm_statistics_dict[uniqueTurbine] = ice_det.statistics
        else:
            for row in windFarmDF.itertuples(index=False):
                turbine_name = row.turbine_name
                csv_fname = row.file_name
                ice_det = IceLossDetector.importFromCSV(DATA_DIR / csv_fname)
                ice_det.addParametersFromJSON(json_source)
                ice_det.parameters.update(row._asdict())
                ice_det.computeFullChain()
    
                farm_statistics_dict[turbine_name] = ice_det.statistics

        return farm_statistics_dict

    @staticmethod
    def load_wind_farm(windFarmCsv, json_source=None, customColNamesDict=None):
        """
        Creates a dictionnary of IceLossDetector objects from a standard json file that imports csv files generated from the import module
        
        """

        farm_dict = {}
        if json_source is None:
            #if no json file is provided, create a standard one
            json_source = 'defaultParameters.json'
            parameters = IceLossDetector.create_default_json_parameter_file(json_source)
            
        read_json_parameters(json_source)
        windFarmDF = readWindFarmDFFromCSV(windFarmCsv,customColNamesDict=customColNamesDict)
        
        #Handle 2 cases, 1- A single csv with all the turbine and a ID column, 2- A csv file per turbine
        if (len(windFarmDF.file_name.unique()) == 1) & (len(windFarmDF)!=1):
            fullDF = IceLossDetector.importFromCSV(Path('app') / 'data' / windFarmDF.file_name[0])
            if 'ID' not in fullDF.columns:
                raise ImportError('Single data csv file in import list, the file does not include the ID column necessary for multiple turbines')
            uniqueTurbines = fullDF.ID.unique()
            for uniqueTurbine in uniqueTurbines:
                ice_det = fullDF.loc[fullDF.ID==uniqueTurbine,:]
                ice_det.addParametersFromJSON(json_source)
                ice_det.parameters.update(windFarmDF.loc[windFarmDF.turbine_name==uniqueTurbine,:].squeeze(axis=0).to_dict())
                farm_dict[uniqueTurbine] = ice_det
        else:
            for row in windFarmDF.itertuples(index=False):
                turbine_name = row.turbine_name
                csv_fname = row.file_name
                ice_det = IceLossDetector.importFromCSV(DATA_DIR / csv_fname)
                ice_det.addParametersFromJSON(json_source)
                ice_det.parameters.update(row._asdict())
                #ice_det.computeFullChain()
    
                farm_dict[turbine_name] = ice_det

        return farm_dict

    @staticmethod      
    def create_default_json_parameter_file(json_fname):
        #create empty object to get default values
        defaultParameters = IceLossDetector().saveParametersToJSON(json_fname)
        return defaultParameters


#--------- Utility functions that can only be called from the class --------------

def readWindFarmDFFromCSV(windFarmCsv,customColNamesDict=None):
    windFarmDF = pd.read_csv(windFarmCsv)
    if customColNamesDict is not None:
        windFarmDF.rename(inplace=True,mapper=customColNamesDict)
    if not np.isin(['file_name', 'turbine_name', 'rated_power','hub_height', 'elevation'],windFarmDF.columns).all():
        raise ImportError('The wind farm csv does not contain the required columns of the standard format')
    return windFarmDF



def read_json_parameters(json_source):
    """
    Read turbine parameters from either:
    1) a JSON file path (str or Path)
    2) a dict already loaded via json.load(...)
    """

    # ---------- Load JSON ----------
    if isinstance(json_source, dict):
        data = json_source

    elif isinstance(json_source, (str, Path)):
        json_path = Path(json_source)

        try:
            with json_path.open("r", encoding="utf-8") as file:
                data = json.load(file)

        except FileNotFoundError:
            raise FileNotFoundError(
                f"Error: The file {json_path} was not found."
            )
        except json.JSONDecodeError as e:
            raise ValueError(
                f"Error: Could not decode JSON from {json_path}. Invalid JSON syntax."
            ) from e

    else:
        raise TypeError(
            "json_source must be either a dict (already loaded JSON) "
            "or a file path (str or pathlib.Path)."
        )

    # ---------- Parse Parameters ----------
    try:
        parameters = {}
        turbine_info = data.get("turbines_info", [])

        #Might be changed with micheal change of the json format
        parameters['turbine_name'] = turbine_info.get("turbine_name","unnamed_turbine")
        parameters['file_name'] = turbine_info.get('file_name','no_file_name')
        parameters['rated_power'] = pd.to_numeric(turbine_info.get('rated_power',None),errors='coerce')
        parameters['hub_height'] = pd.to_numeric(turbine_info.get('hub_height',80),errors='coerce')
        parameters['elevation'] = pd.to_numeric(turbine_info.get('elevation',100),errors='coerce')

        # Power curve binning
        binning = data["power_curve_options"]["binning"]
        parameters["low_wind_bin"] = binning["min"]
        parameters["high_wind_bin"] = binning["max"]
        parameters["wind_bin_size"] = binning["step"]

        # Power curve limits
        pc_opts = data["power_curve_options"]
        parameters["low_quantile"] = pc_opts["lower_limit_percent"] / 100
        parameters["high_quantile"] = pc_opts["upper_limit_percent"] / 100

        # Temperature / icing
        parameters["temperature_filter_level"] = pc_opts["temperature_threshold_C"]
        parameters["icing_alarm_limit"] = 1  # TODO

        # Other limits
        parameters["alarm_time_limit"] = 3     # TODO
        parameters["minimum_wind_speed"] = 3   # TODO
        parameters["stop_limit"] = 100          # TODO

        return parameters

    except KeyError as e:
        raise KeyError(
            f"Missing expected key in JSON structure: {e}"
        ) from e
    except Exception as e:
        raise ImportError(
            f"Issue while importing turbine parameters: {e}"
        ) from e



#--------------- Main functions -----------------------------
        
if __name__ == '__main__2':

    json_path_name = DATA_DIR / 'settings_new_format.json'
    farm_stats = IceLossDetector.compute_wind_farm(DATA_DIR / 'windFarmImport.csv', jsonFileName=json_path_name)
    print(farm_stats)



if __name__ == '__main__':
    #possible to add a loop here from the new values of the json file to do an entire wind farm
    #make a constructor for dataframes
    #TODO option to make it year by year, it can be for power curve generation, but also for results (add option to have an annual thing), add option for calendar year or winters (flexible parameter, Jul, Jan, Aug, Sept)
    json_path_name = Path('app') / 'data'  / 'settings_new_format.json'
    ice_det = IceLossDetector.importFromCSV(DATA_DIR / "cleaned_file_fake_data2 (other_col_names).csv") #have a constructor that does the whole thing
    ice_det.addParametersFromJSON(json_path_name)
    ice_det.identifyCleanedDataset() #options to activate those functions or not
    ice_det.makePowerCurve()
    ice_det.addExpectedPowerToData()
    ice_det.identifyIceLossPeriods()
    ice_det.computeIcingLosses()
    # can be formatted into a dictionnary
    ice_det.to_csv('output.csv')
    ice_det.plotPowerCurve() #optional
    ice_det.plotTimeseries()
    ice_det.exportPowerCurveToCSV()
    
    ice_det.computeIcingStatistics()
    print(ice_det.statistics)
