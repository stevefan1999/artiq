from artiq.experiment import *


class UrukulFreqSet(EnvExperiment):
    def build(self):
        self.urukuls = dict()
        ddb = self.get_device_db()
        for name, desc in ddb.items():
            if isinstance(desc, dict) and desc["type"] == "local":
                module, cls = desc["module"], desc["class"]
                if (module, cls) == ("artiq.coredevice.ad9910", "AD9910"):
                    self.urukuls[name] = self.get_device(name)
                elif (module, cls) == ("artiq.coredevice.ad9912", "AD9912"):
                    self.urukuls[name] = self.get_device(name)

        self.setattr_device("core")
        self.setattr_argument("chan", EnumerationValue([*self.urukuls.keys()]))
        self.setattr_argument("freq", NumberValue(ndecimals=5, step=1, unit="MHz"))

    @kernel
    def set_urukul_freq(self, channel, frequency):
        self.core.break_realtime()
        channel.cpld.init()
        channel.init()
        channel.set(frequency)
        channel.cfg_sw(True)
        channel.set_att(6.)

    def run(self):
        self.core.reset()
        if self.chan in self.urukuls:
            print(f"Setting the frequency of {self.chan} to {self.freq}")
            self.set_urukul_freq(self.urukuls[self.chan], self.freq)
        else:
            raise ValueError(f"no such channel {self.chan}")
