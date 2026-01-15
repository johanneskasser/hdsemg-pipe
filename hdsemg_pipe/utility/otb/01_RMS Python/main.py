import OTBiolabInterface as otb
import OTBiolabClasses as otbClasses
import numpy as np

''' DESCRIPTION 
This processing executes the Root Mean Squared of the signal.
It is a epoched processing, this means that a time window is provided
and the RMS is estimated for each window of the signal.
The epoch is a parameter of the algorithm
'''

''' CATEGORY
Amplitude
'''

############################################## PARAMETERS #########################################################

epoch = 0.5

###################################################################################################################


############################################# LOADING DATA ########################################################

# Use one function from otb library to load data from main software
tracks = otb.LoadDataFromPythonFolder()


###################################################################################################################


############################################## ALGORITHM ##########################################################
# Develope your code here

def RMS_estimation(samples):
    # Samples elaboration
    array = np.array(samples)
    rms = np.sqrt(np.mean(array ** 2))
    return rms


# Main Code - Example code to show how elaborate tracks and save them. Change the elaboration with your own code
result_tracks = []
for track in tracks:
    result_sections = []
    number_of_channels = 0

    for section in track.sections:
        result_channels = []
        for channel in section.channels:
            RMS = []
            epoch_start = section.start
            epoch_end = section.start + epoch

            #RMS calculation for each epoch
            while epoch_end <= section.end:
                RMS_samples = [sample for sampleIndex, sample in enumerate(channel.data) if
                    (sampleIndex / track.frequency) >= epoch_start and (sampleIndex / track.frequency) < epoch_end]
                RMS.append(RMS_estimation(RMS_samples))
                epoch_start = epoch_end
                epoch_end += epoch
            
            result_channels.append(otbClasses.Channel(RMS))

        number_of_channels = len(result_channels)
        result_sections.append(otbClasses.Section(section.start, section.end, result_channels))

    result_tracks.append(otbClasses.Track(result_sections, 1 / epoch, number_of_channels, time_shift=epoch/2.0, unit_of_measure=track.unit_of_measure, title='RMS - ' + track.title))

###################################################################################################################


############################################ WRITE DATA ###########################################################

# Use one function from otb library to plot data to main software or to continue the processing chain
otb.WriteDataInPythonFolder(result_tracks)

###################################################################################################################
