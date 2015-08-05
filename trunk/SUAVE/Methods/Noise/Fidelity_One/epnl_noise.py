#-------------------------------------------------------------------------------
# Name:        module1
# Purpose:     
#
# Author:      CARIDSIL
#
# Created:     21/07/2015
# Copyright:   (c) CARIDSIL 2015
# Licence:     <your licence>
#-------------------------------------------------------------------------------

import numpy as np

def epnl_noise(PNLT):
    """This method calculates de effective perceived noise level (EPNL) based on a time history PNLT
     (Perceived Noise Level with Tone Correction).

        Inputs:
                    PNLT                     - Perceived Noise Level with Tone Correction

                Outputs: 
                    EPNL                     - Effective Perceived Noise Level in EPNdB"""
                    
                    
    #Maximum PNLT on the time history data    
    PNLT_max = np.max(PNLT)
    
    #Calculates the number of discrete points on the trajectory
    nsteps = len(PNLT)    
    
    #Exclude sources that are not being calculated or doesn't contribute for the total noise of the aircraft
    if all(PNLT==0):
        EPNL=0
        return(EPNL)

    #Finding the time duration for the noise history where PNL is higher than the maximum PNLT - 10 dB
    i=0
    while PNLT[i]<=(PNLT_max-10) and i<=nsteps:
        i=i+1
    t1=i #t1 is the first time interval
    i=i+1

    #Correction for PNLTM-10 when it falls outside the limit of the data
    if PNLT[nsteps-1]>=(PNLT_max-10):
        t2=nsteps-2
    else:
        while i<=nsteps and PNLT[i]>=(PNLT_max-10):
              i=i+1
        t2=i-1 #t2 is the last time interval
                
    #The time duration where the noise is higher than the maximum PNLT - 10 dB is:
    time_interval=(t2-t1)*0.5
    
    #Calculates the integral of the PNLT which between t1 and t2 points
    sumation=0
    for i in range (t1-1,t2+1):
        sumation=10**(PNLT[i]/10)+sumation
        
        
   #Duration Correction calculation
    duration_correction=10*np.log10(sumation)-PNLT_max-13
                
    #Final EPNL calculation
    EPNL=PNLT_max+duration_correction
    
    
    return (EPNL)    
    

