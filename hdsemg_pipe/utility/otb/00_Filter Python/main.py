import OTBiolabInterface as otb
import OTBiolabClasses as otbClasses
from scipy.signal import butter, sosfilt


''' DESCRIPTION 
This processing is used to filter your signals. Different
possibilities are available: lowpass filter, highpass filter,
bandpass filter and bandstop filtering.
The parameters are:
filter_type -> string to specify filtering type, below the 
available values: lowpass, highpass, bandpass and bandstop.
f1 -> double value which represents cut off frequency, for 
low pass, high pass and notch filtering.
f2 -> double value which represents the second cut off frequency,
it is used together with f1 in band pass and band stop filtering.
order -> int value which represent the filter order.

'''

''' CATEGORY
Amplitude
'''



############################################## PARAMETERS #########################################################

filter_type = 'highpass'     #Available values: lowpass, highpass, bandpass, bandstop and notch
f1 = 0.1                    #Expressed in Hz
f2 = 20                    #Expressed in Hz
order = 2

###################################################################################################################


############################################# LOADING DATA ########################################################

tracks=otb.LoadDataFromPythonFolder()

###################################################################################################################



############################################## ALGORITHM ##########################################################
#Filters definitions
def butter_lowpass(cutoff, fs, order=5):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    sos = butter(order, normal_cutoff, btype='low', analog=False, output='sos')
    return sos

def butter_highpass(cutoff, fs, order=5):
    nyquist = 0.5 * fs
    normal_cutoff = cutoff / nyquist
    sos = butter(order, normal_cutoff, btype='high', analog=False, output='sos')
    return sos

def butter_bandpass(lowcut, highcut, fs, order=5):
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    sos = butter(order, [low, high], btype='band', analog=False, output='sos')
    return sos

def butter_bandstop(lowcut, highcut, fs, order=5):
    nyquist = 0.5 * fs
    low = lowcut / nyquist
    high = highcut / nyquist
    sos = butter(order, [low, high], btype='bandstop', analog=False, output='sos')
    return sos




def GetFilter(filter_type,fs,f1,f2,order):
    if(filter_type=='lowpass'):
        return butter_lowpass(f1,fs,order)
    elif(filter_type=='highpass'):
        return butter_highpass(f1,fs,order)
    elif(filter_type=='bandpass'):
        return butter_bandpass(f1,f2,fs,order)
    elif(filter_type=='bandstop'):
        return butter_bandstop(f1,f2,fs,order)
    return

#Develope your code here
result_tracks=[]
for track in tracks:
    result_sections=[]
    number_of_channels=0
    filter=GetFilter(filter_type, track.frequency, f1, f2, order)
    
    for section in track.sections:
        result_channels=[]
        for channel in section.channels:
            filtered_data=sosfilt(filter,channel.data)
            result_channels.append(otbClasses.Channel(filtered_data))
        
        number_of_channels=len(result_channels)
        result_sections.append(otbClasses.Section(section.start, section.end, result_channels))
    
    result_tracks.append(otbClasses.Track(result_sections, track.frequency, number_of_channels, unit_of_measure=track.unit_of_measure, title='Filter - '+track.title))
    

###################################################################################################################


############################################ WRITE DATA ###########################################################

#Use one function from otb library to plot data to main software or to continue the processing chain
otb.WriteDataInPythonFolder(result_tracks)
###################################################################################################################
