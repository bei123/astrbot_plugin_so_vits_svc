"""
只支持MP3,flac,wav格式
1人声1伴奏，不要多填，也不要去掉“input\\”这个前缀
                            -----by C_Zim(Chai🍊)
"""


class Setting:
    def __init__(self):
        self.voc_path = r"input/vocal.wav"
        self.inst_path = r"input/inst.wav"
        self.sample_rate = 44100
        self.headroom = -8
        self.voc_input = -4
        self.revb_gain = 0
