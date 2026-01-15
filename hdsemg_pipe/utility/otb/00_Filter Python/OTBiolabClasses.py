# -*- coding: utf-8 -*-
"""
Created on Thu Oct  5 16:07:47 2023

Library which contains the classes to manage 
OTBiolab objects

@author: PC-Fabio
"""

import os
import struct
import matplotlib.pyplot as plt
import numpy as np


class Channel:
    
    data = []
    
    def __init__(self, data):
        self.data=data
    

class Section:
    start=0
    end=0
    channels=[]
    
    def __init__(self,start,end,channels):
        self.channels=channels
        self.start=start
        self.end=end
    
    


class Track:
    title=""
    unit_of_measurement=""
    sections=[]
    frequency=2000 #Expressed in Hz
    number_of_channels=0
    device=""
    time_shift=0
    
    def __init__(self,sections,frequency, number_of_channels,time_shift=0,unit_of_measure="",title="", device=""):
        self.title=title
        self.unit_of_measure=unit_of_measure
        self.sections=sections
        self.frequency=frequency
        self.number_of_channels=number_of_channels
        self.device=device
        self.time_shift=time_shift
        
    
    def SaveData(self, path,track_index):
        str_track_index=str(track_index)
        if(track_index<10):
            str_track_index='0'+str_track_index
            
        file_name=os.path.join(path,str_track_index+'_'+ self.title+ '.data')
        with open(file_name, 'wb') as writer:
            # Per ogni traccia salvo la frequenza di campionamento
            writer.write(struct.pack('i', len(self.title)))
            writer.write(self.title.encode('utf-8'))
            writer.write(struct.pack('d', self.frequency))
            writer.write(struct.pack('d', self.time_shift))
            writer.write(struct.pack('i', self.number_of_channels))
            writer.write(struct.pack('i', len(self.unit_of_measure)))
            writer.write(self.unit_of_measure.encode('utf-8'))

    
            # Scrive l'intestazione con frequenza e titolo della traccia
            for section in self.sections:
                # Salva i tempi di selezione
                writer.write(struct.pack('d', section.start))
                writer.write(struct.pack('d', section.end))
        
                for channel in section.channels:
                    # Per ogni lista di double, scrivi la dimensione della lista, seguita dai valori
                    writer.write(struct.pack('i', len(channel.data)))
                    writer.write(struct.pack(f'{len(channel.data)}d', *channel.data))
    
    def SaveChart(self,path, track_index, max_x_value, x_label, y_label):
        str_track_index=str(track_index)
        if(track_index<10):
            str_track_index='0'+str_track_index

        file_name=os.path.join(path,str_track_index+'_'+ self.title+ '.chart')
        with open(file_name,'wb') as writer:
            #Chart info saving
            writer.write(struct.pack('i', len(self.title)))
            writer.write(self.title.encode('utf-8'))
            writer.write(struct.pack('i', self.number_of_channels))
            writer.write(struct.pack('i', len(x_label)))
            writer.write(x_label.encode('utf-8'))
            writer.write(struct.pack('i', len(y_label)))
            writer.write(y_label.encode('utf-8'))

            #Save the section
            for section in self.sections:
                #Save the times
                writer.write(struct.pack('d', section.start))
                writer.write(struct.pack('d', section.end))
                
                #Create the x values
                n_samples=len(section.channels[0].data)
                delta_x=max_x_value/(n_samples-1)
                x_values=np.append(np.arange(0,max_x_value,delta_x),max_x_value)
                
                #Save the x values
                writer.write(struct.pack('i', len(x_values)))
                writer.write(struct.pack(f'{len(x_values)}d', *x_values))
                
                #Save all the y values
                for channel in section.channels:
                    writer.write(struct.pack(f'{len(channel.data)}d', *channel.data))
        
    def SaveText(self, path, track_index, channel_title=""):
        str_track_index=str(track_index)
        if(track_index<10):
            str_track_index='0'+str_track_index
            
        file_name=os.path.join(path,str_track_index+'_'+ self.title+ '.text')
        with open(file_name, 'wb') as writer:
            title_uom=self.title+' ('+self.unit_of_measure+')'
            writer.write(struct.pack('i', len(title_uom)))
            writer.write(title_uom.encode('utf-8'))
            writer.write(struct.pack('i', self.number_of_channels))
            
            for section in self.sections:
                writer.write(struct.pack('d', section.start))
                writer.write(struct.pack('d', section.end))                
                for channel_index,channel in enumerate(section.channels):
                    #Check if data is iterable
                    if not(hasattr(channel.data, '__iter__')):
                        channel.data = [channel.data]
                    
                    #Save the data as string
                    channel_content=', '.join(map(str, channel.data))
                    full_channel_content='Channel '+str(channel_index)+channel_title+': '+'('+channel_content+')'
                    writer.write(struct.pack('i', len(full_channel_content)))
                    writer.write(full_channel_content.encode('utf-8'))
                    
    def GetDataFromSections(self,section_index):
        if section_index<len(self.sections):
            involved_section=self.sections[section_index]
            data=[];
            for channel in involved_section.channels:
                data.append(channel.data);
            
        return np.reshape(data,(self.number_of_channels,-1));
    def Plot(self):
        for section in self.sections:
            offset = 0

            plt.figure()
            plt.title('Plot '+self.title+': '+str(section.start)+' - '+str(section.end))
            
            for channel in section.channels:
                plt.plot(channel.data + offset)
                offset_update = np.max(channel.data) - np.min(channel.data)
                
                if offset_update == 0:
                    offset_update = 100

                offset += offset_update
                
            plt.show();
            
            
            

                    
                    
            
