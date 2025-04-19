import numpy as np
import pedalboard
from pedalboard import (
    Compressor,
    Gain,
    HighpassFilter,
    LowpassFilter,
    Reverb,
    Limiter,
    NoiseGate,
    Phaser,
    Chorus,
    Distortion,
    HighShelfFilter,
    LowShelfFilter,
    PeakFilter,
)
from pedalboard.io import AudioFile
from .config import Setting
from .base_time import TimeCalculator


'''
Developed by: C_Zim
Date: 25/2/26
Version: 0.3
Description:
    此项目仅供娱乐，不得用于商业用途
    这只是个模板，请根据自己的需求进行修改
    请确保你有一定的混音知识和经验，否则只会越改越差
'''

def load(path):
    with AudioFile(path).resampled_to(setting.sample_rate) as audio:       
        data = audio.read(audio.frames)
    return data

def vocal(release=300,fb=180):
    bv = pedalboard.Pedalboard([
        Gain(setting.voc_input),
        HighpassFilter(230),
        PeakFilter(2700,-2,1),
        HighShelfFilter(20000,-2,1.8),
        Gain(1),
        PeakFilter(1400,3,1.15),
        PeakFilter(8500,2.5,1),
        Gain(-1),
        pedalboard.Mix([
            Gain(0),
            pedalboard.Pedalboard([
                pedalboard.Invert(),
                Compressor(-30,3.2,40,fb),
                Gain(-40)
            ])
        ]),
        Compressor(-18,2.5,19,release),
        Gain(0)
    ])

    return bv

def reverb(s=5,m=25,l=50,d=200):
    delay = pedalboard.Pedalboard([
        Gain(-20),
        pedalboard.Delay(d/8,0,1),
        Gain(-12),
    ])

    short = pedalboard.Pedalboard([
        Gain(-20),
        pedalboard.Delay(s/1000,0,1),
        Reverb(0.2,0.35,1,0,1,0),
        Gain(-12),
    ])

    medium = pedalboard.Pedalboard([
        Gain(-16),
        pedalboard.Delay(m/1000,0.3,1),
        Reverb(0.45,0.55,1,0,1,0),
        Gain(-19),
    ])

    long = pedalboard.Pedalboard([
        Gain(-12),
        pedalboard.Delay(l/1000,0.6,1),
        Reverb(0.6,0.7,1,0,1,0),
        Gain(-23)
    ])

    br = pedalboard.Pedalboard([
        pedalboard.Mix([
            short,
            medium,
            long,
            delay,
        ]),
        PeakFilter(1450,-4,1.83),
        PeakFilter(2300,5,0.51),
        Gain(setting.revb_gain),
    ])

    return br

def instrument():
    inst = pedalboard.Pedalboard([Gain(setting.headroom)])
    return inst

def master(comp_rel=500,lim_rel=400):
    mast = pedalboard.Pedalboard([
        Compressor(-10,1.6,10,comp_rel),
        Limiter(-3,lim_rel),
        Gain(-0.5)
    ])

    return mast

def combine(vocal,revb,inst):
    min_length = min(vocal.shape[1],inst.shape[1])
    voc_new = vocal[:, :min_length]
    revb_new = revb[:, :min_length]
    inst_new = inst[:, :min_length]
    combined = voc_new + inst_new + revb_new
    return combined

def out_put(path,audio):
     with AudioFile(
            path,
            'w',
            setting.sample_rate,
            audio.shape[0],
            bit_depth= 16
        ) as final:
            final.write(audio)



setting = Setting()
ts = TimeCalculator(setting.voc_path).times
predelay = ts["pre_delay"]
release = ts["release"]

voc = load(setting.voc_path)       
inst = load(setting.inst_path)

fx_voc = vocal(release[1],release[0])
fx_revb = reverb(predelay[0],predelay[2],predelay[3],predelay[1])
fx_inst = instrument()
fx_master = master(release[3],release[2])
eff_voc = fx_voc(voc,setting.sample_rate)
stereo = np.tile(eff_voc,(2, 1))

revb = fx_revb(stereo,setting.sample_rate)
eff_inst = fx_inst(inst,setting.sample_rate)
combined = combine(eff_voc,revb,eff_inst)
output = fx_master(combined,setting.sample_rate)
out_put("output/mixdown.flac",output)
