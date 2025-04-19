import warnings
import librosa


warnings.filterwarnings("ignore")

class TimeCalculator:

    def __init__(self,inst_path):
        y,sr = librosa.load(inst_path)
        tempo,_ = librosa.beat.beat_track(y=y, sr=sr)
        bpm = round(int(tempo),0)
        if bpm >= 100:
            bpm = bpm / 2
        self.basic_time = 60000 / bpm
        self.times = {
            "pre_delay":self.reverb_pre_delay(),
            "release":self.compressor_release(),
        }

    def _calculate_time(self,times):
        stop = 0
        for time in times:
            half_time = time / 2
            times.append(half_time)
            stop += 1
            if stop >= 15:
                break
        syns = times[:]
        return syns

    def _select_time(
            self,
            time_lists,
            standard_value,
            standard_range,
            double_mode=False
    ):
        if min(time_lists) >= standard_range:
            if double_mode:
                return standard_value * 2
            else:
                return standard_value
        else:
            min_num = float("inf")
            for time_list in time_lists:
                diff = abs(time_list - standard_value)
                if diff < min_num:
                    min_num = diff
                    closest_num = time_list
            if double_mode:
                return closest_num * 2
            else:
                return closest_num

    def _note(self,rate,mode):
        if mode == 0:
            note = self.basic_time * rate
            dot = note * 1.5
            trip = note * 2 / 3
            bases = [note,dot,trip]
            fulls = self._calculate_time(bases)
        elif mode == 1:
            note = self.basic_time / rate
            dot = note * 1.5
            trip = note * 2 / 3
            bases = [note,dot,trip]
            fulls = self._calculate_time(bases)
        sorted_times = sorted(fulls)
        return sorted_times

    def reverb_pre_delay(self):
        pre_delay_raws = self._note(8,1)
        pre_delays = [
            round(pre_delay,2) for pre_delay in pre_delay_raws
        ]
        roomER = self._select_time(pre_delays,0.6,1,True)
        roomLR = self._select_time(pre_delays,2,4,True)
        plate = self._select_time(pre_delays,10,20,True)
        hall = self._select_time(pre_delays,20,40,True)
        return (
            roomER,
            roomLR,
            plate,
            hall,
        )

    def compressor_release(self):
        release_raws = self._note(2,0)
        releases = [
            round(release,1) for release in release_raws
        ]
        fast = self._select_time(releases,100,200)
        medium = self._select_time(releases,350,500)
        slow = self._select_time(releases,500,1000)
        limiter = self._select_time(releases,450,800)
        return (
            fast,
            medium,
            slow,
            limiter,
        )
